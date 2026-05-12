"""自动抓取与导出服务 - 研究完成后自动抓取高可信来源并导出到 Obsidian。

职责：
1. 根据 research_policy.yaml 选择 A/S 级来源
2. 调用 ExtractionService 抓取正文
3. 调用 DocumentAnalysisService 分析
4. 调用 MarkdownService 导出到 Obsidian
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from app.tracing import TracePhase
from app.tracing.recorder import get_recorder
from models.enums import DownloadStatus, SourceLevel, SourceType
from models.schemas import ExtractedDocument, ResearchTask, SourceItem

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


# === Policy Loading ===


@lru_cache
def _load_research_policy() -> dict:
    """加载研究策略配置。"""
    policy_path = Path("config/research_policy.yaml")
    if not policy_path.exists():
        logger.warning("research_policy_not_found using_defaults=true")
        return _default_policy()
    with open(policy_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or _default_policy()


def _reset_policy_cache() -> None:
    """清除策略缓存（仅测试用）。"""
    _load_research_policy.cache_clear()


def _default_policy() -> dict:
    """默认策略。"""
    return {
        "auto_fetch": {
            "enabled": True,
            "min_source_level": "A",
            "include_levels": ["S", "A"],
            "max_sources_per_task": 20,
            "skip_source_types": ["reference", "low_quality"],
            "skip_categories": ["low_quality", "gossip"],
            "skip_domains": ["wikipedia.org", "en.wikipedia.org", "zh.wikipedia.org"],
            "require_downloadable": False,
            "retry_failed": False,
            "min_relevance_score": 0.3,
            "timeout_per_source_seconds": 30,
        },
        "auto_analyze": {
            "enabled": True,
            "use_llm": True,
            "output_language": "zh",
            "extract_entities": True,
            "extract_story_points": True,
        },
        "auto_export": {
            "enabled": True,
            "export_index": True,
            "export_source_notes": True,
            "export_imported_report": True,
            "export_only_fetched_sources": False,
        },
    }


# === Source Selection ===


def select_sources_for_fetch(
    sources: list[SourceItem],
    policy: dict | None = None,
) -> tuple[list[SourceItem], list[SourceItem]]:
    """
    根据策略选择需要自动抓取的来源。

    Returns:
        (selected, skipped) - 选中的和跳过的来源列表
    """
    if policy is None:
        policy = _load_research_policy()

    fetch_policy = policy.get("auto_fetch", {})

    if not fetch_policy.get("enabled", True):
        return [], sources

    include_levels = set(fetch_policy.get("include_levels", ["S", "A"]))
    max_sources = fetch_policy.get("max_sources_per_task", 20)
    skip_types = set(fetch_policy.get("skip_source_types", []))
    skip_domains = set(fetch_policy.get("skip_domains", []))
    min_relevance = fetch_policy.get("min_relevance_score", 0.3)
    retry_failed = fetch_policy.get("retry_failed", False)

    selected: list[SourceItem] = []
    skipped: list[SourceItem] = []

    for source in sources:
        # 检查等级
        if source.source_level.value not in include_levels:
            skipped.append(source)
            continue

        # 检查来源类型
        if source.source_type.value in skip_types:
            skipped.append(source)
            continue

        # 检查域名
        domain_lower = source.domain.lower()
        if any(skip_d in domain_lower for skip_d in skip_domains):
            skipped.append(source)
            continue

        # 检查相关性分数
        if source.relevance_score < min_relevance:
            skipped.append(source)
            continue

        # 检查是否已经抓取过
        if source.download_status == DownloadStatus.EXTRACTED:
            skipped.append(source)
            continue

        if source.download_status == DownloadStatus.EXPORTED:
            skipped.append(source)
            continue

        # 检查失败重试
        if source.download_status == DownloadStatus.FAILED and not retry_failed:
            skipped.append(source)
            continue

        selected.append(source)

        # 达到上限
        if len(selected) >= max_sources:
            break

    # 剩余的加入 skipped
    remaining_idx = len(selected) + len(skipped)
    if remaining_idx < len(sources):
        skipped.extend(sources[remaining_idx:])

    return selected, skipped


# === Auto Fetch & Export Service ===


class AutoFetchResult:
    """自动抓取结果摘要。"""

    def __init__(self):
        self.selected_count: int = 0
        self.fetched_count: int = 0
        self.failed_count: int = 0
        self.skipped_count: int = 0
        self.analyzed_count: int = 0
        self.exported: bool = False
        self.index_path: str = ""
        self.source_note_count: int = 0
        self.errors: list[str] = []
        self.extracted_docs: dict[str, ExtractedDocument] = {}


class AutoFetchExportService:
    """自动抓取与导出服务。"""

    def __init__(
        self,
        ai_gateway: "AIGateway | None" = None,
        extraction_service=None,
        policy: dict | None = None,
    ):
        self._ai_gateway = ai_gateway
        self._extraction_service = extraction_service
        self._policy = policy or _load_research_policy()

    async def run(
        self,
        task: ResearchTask,
        sources: list[SourceItem],
        vault_path: Path | None = None,
    ) -> AutoFetchResult:
        """
        执行自动抓取 → 分析 → 导出流程。

        Args:
            task: 研究任务
            sources: 所有来源（已评分排序）
            vault_path: Obsidian vault 路径（None 则从配置读取）

        Returns:
            AutoFetchResult 摘要
        """
        result = AutoFetchResult()
        _trace = get_recorder()

        # 1. 选择来源
        selected, skipped = select_sources_for_fetch(sources, self._policy)
        result.selected_count = len(selected)
        result.skipped_count = len(skipped)

        _trace.info(
            task.id, "auto_fetch_started", TracePhase.PROCESSING,
            message=f"Auto fetch: {len(selected)} selected, {len(skipped)} skipped",
            output_summary={
                "selected_count": len(selected),
                "skipped_count": len(skipped),
                "max_sources": self._policy.get("auto_fetch", {}).get("max_sources_per_task", 20),
            },
        )

        if not selected:
            logger.info("auto_fetch_no_sources task_id=%s", task.id)
            return result

        # 2. 抓取正文
        extracted_docs = await self._fetch_sources(task, selected, result)

        # 3. 分析正文
        if self._policy.get("auto_analyze", {}).get("enabled", True):
            await self._analyze_documents(task, extracted_docs, result)

        # 4. 导出到 Obsidian
        export_policy = self._policy.get("auto_export", {})
        if export_policy.get("enabled", True):
            await self._export_to_obsidian(task, sources, extracted_docs, vault_path, result)

        _trace.info(
            task.id, "auto_fetch_finished", TracePhase.PROCESSING,
            message=f"Auto fetch complete: fetched={result.fetched_count}, failed={result.failed_count}",
            output_summary={
                "selected_count": result.selected_count,
                "fetched_count": result.fetched_count,
                "failed_count": result.failed_count,
                "analyzed_count": result.analyzed_count,
                "exported": result.exported,
                "source_note_count": result.source_note_count,
            },
        )

        return result

    async def _fetch_sources(
        self,
        task: ResearchTask,
        selected: list[SourceItem],
        result: AutoFetchResult,
    ) -> dict[str, ExtractedDocument]:
        """抓取选中来源的正文。"""
        from services.extraction_service import ExtractionService

        extractor = self._extraction_service or ExtractionService()
        extracted_docs: dict[str, ExtractedDocument] = {}
        _trace = get_recorder()

        for source in selected:
            _trace.info(
                task.id, "auto_fetch_source_started", TracePhase.PROCESSING,
                message=f"Fetching: {source.title[:60]}",
                input_summary={"url": source.url, "level": source.source_level.value},
            )

            try:
                doc = await extractor.extract_source(source)

                if source.download_status == DownloadStatus.EXTRACTED and doc.content:
                    extracted_docs[source.id] = doc
                    result.fetched_count += 1

                    _trace.info(
                        task.id, "auto_fetch_source_finished", TracePhase.PROCESSING,
                        message=f"Fetched: {source.title[:60]} ({len(doc.content)} chars)",
                        output_summary={
                            "url": source.url,
                            "chars": len(doc.content),
                            "title": doc.title[:80],
                        },
                    )
                else:
                    result.failed_count += 1
                    _trace.record(
                        task_id=task.id,
                        step="auto_fetch_source_failed",
                        phase=TracePhase.PROCESSING,
                        level="warning",
                        message=f"Fetch failed (empty content): {source.title[:60]}",
                        input_summary={"url": source.url},
                    )

            except Exception as e:
                result.failed_count += 1
                source.download_status = DownloadStatus.FAILED
                error_msg = str(e)[:200]
                result.errors.append(f"{source.url}: {error_msg}")

                _trace.record(
                    task_id=task.id,
                    step="auto_fetch_source_failed",
                    phase=TracePhase.PROCESSING,
                    level="warning",
                    message=f"Fetch error: {source.title[:60]}",
                    input_summary={"url": source.url},
                    error_message=error_msg,
                )

                logger.warning(
                    "auto_fetch_source_failed task_id=%s url=%s error=%s",
                    task.id, source.url, error_msg,
                )

        result.extracted_docs = extracted_docs
        return extracted_docs

    async def _analyze_documents(
        self,
        task: ResearchTask,
        extracted_docs: dict[str, ExtractedDocument],
        result: AutoFetchResult,
    ) -> None:
        """对抓取的文档进行 LLM 分析。"""
        if not extracted_docs:
            return

        _trace = get_recorder()
        _trace.info(
            task.id, "auto_analysis_started", TracePhase.PROCESSING,
            message=f"Analyzing {len(extracted_docs)} documents",
        )

        analyze_policy = self._policy.get("auto_analyze", {})
        use_llm = analyze_policy.get("use_llm", True) and self._ai_gateway is not None

        if not use_llm:
            logger.info("auto_analyze_skipped task_id=%s reason=no_llm", task.id)
            return

        from app.services.document_analysis_service import (
            DocumentAnalysisService,
            ExtractedDocument as DAExtractedDocument,
        )

        analysis_service = DocumentAnalysisService(ai_gateway=self._ai_gateway)

        for source_id, doc in extracted_docs.items():
            try:
                # 转换为 DocumentAnalysisService 期望的格式
                da_doc = DAExtractedDocument(
                    url=doc.source_item_id if hasattr(doc, "source_item_id") else "",
                    title=doc.title,
                    content=doc.content,
                    word_count=len(doc.content),
                )

                analysis_result = await analysis_service.analyze(
                    document=da_doc,
                    topic=task.topic,
                )

                # 将分析结果写回 ExtractedDocument
                if analysis_result.summary:
                    doc.summary = analysis_result.summary
                if analysis_result.people:
                    doc.people = analysis_result.people
                if analysis_result.places:
                    doc.places = analysis_result.places
                if analysis_result.organizations:
                    doc.organizations = analysis_result.organizations
                if analysis_result.concepts:
                    doc.concepts = analysis_result.concepts
                if analysis_result.key_points:
                    doc.key_quotes = analysis_result.key_points
                if analysis_result.story_points:
                    doc.events = analysis_result.story_points

                result.analyzed_count += 1

            except Exception as e:
                logger.warning(
                    "auto_analyze_failed task_id=%s source_id=%s error=%s",
                    task.id, source_id, str(e)[:100],
                )

        _trace.info(
            task.id, "auto_analysis_finished", TracePhase.PROCESSING,
            message=f"Analyzed {result.analyzed_count}/{len(extracted_docs)} documents",
        )

    async def _export_to_obsidian(
        self,
        task: ResearchTask,
        all_sources: list[SourceItem],
        extracted_docs: dict[str, ExtractedDocument],
        vault_path: Path | None,
        result: AutoFetchResult,
    ) -> None:
        """导出完整研究资料包到 Obsidian vault。"""
        _trace = get_recorder()

        # 确定 vault 路径
        if vault_path is None:
            from core.config import get_settings
            settings = get_settings()
            if not settings.obsidian_configured:
                _trace.record(
                    task_id=task.id,
                    step="auto_export_failed",
                    phase=TracePhase.PROCESSING,
                    level="warning",
                    message="Obsidian vault not configured, skipping export",
                )
                logger.warning("auto_export_skipped task_id=%s reason=vault_not_configured", task.id)
                return
            vault_path = settings.obsidian_path

        if not vault_path.exists() or not vault_path.is_dir():
            _trace.record(
                task_id=task.id,
                step="auto_export_failed",
                phase=TracePhase.PROCESSING,
                level="warning",
                message=f"Vault path invalid: {vault_path}",
            )
            logger.warning("auto_export_skipped task_id=%s reason=vault_path_invalid", task.id)
            return

        _trace.info(
            task.id, "auto_export_started", TracePhase.PROCESSING,
            message=f"Exporting research package to {vault_path}",
        )

        export_policy = self._policy.get("auto_export", {})

        try:
            from services.markdown_service import (
                export_research_index,
                export_source_note,
                generate_index_synthesis,
            )

            # 1. 生成 LLM 综合分析（如果有 extracted_docs）
            synthesis = None
            if extracted_docs:
                synthesis = await generate_index_synthesis(
                    topic=task.topic,
                    mode=task.mode.value if hasattr(task.mode, 'value') else str(task.mode),
                    sources=all_sources,
                    ai_gateway=self._ai_gateway,
                    extracted_docs=extracted_docs,
                )

            # 2. 导出 source notes
            source_note_count = 0
            if export_policy.get("export_source_notes", True):
                for source_id, doc in extracted_docs.items():
                    if not doc.content:
                        continue
                    source_item = next(
                        (s for s in all_sources if s.id == source_id), None
                    )
                    if source_item is None:
                        continue

                    try:
                        export_source_note(
                            source_item=source_item,
                            extracted=doc,
                            topic=task.topic,
                            vault_path=vault_path,
                        )
                        source_note_count += 1
                    except Exception as e:
                        logger.warning(
                            "auto_export_source_note_failed source_id=%s error=%s",
                            source_id, str(e)[:100],
                        )

            result.source_note_count = source_note_count

            # 3. 导出 index.md（带 synthesis）
            if export_policy.get("export_index", True):
                index_path = export_research_index(
                    task=task,
                    sources=all_sources,
                    extracted_docs=extracted_docs,
                    vault_path=vault_path,
                    synthesis=synthesis,
                )
                result.index_path = str(index_path)

            # 4. 导出 cards/*.md（人物、地点、概念、故事点、待核验）
            if extracted_docs:
                from services.card_export_service import export_research_cards
                try:
                    card_count = export_research_cards(
                        task=task,
                        sources=all_sources,
                        extracted_docs=extracted_docs,
                        vault_path=vault_path,
                        synthesis=synthesis,
                    )
                    logger.info("cards_exported task_id=%s count=%d", task.id, card_count)
                except Exception as e:
                    logger.warning("card_export_failed task_id=%s error=%s", task.id, str(e)[:100])

            # 5. 导出 filtered_noise.md（可选）
            self._export_filtered_noise(task, all_sources, extracted_docs, vault_path)

            # 6. 导出 trace_summary.md（可选）
            self._export_trace_summary(task, result, vault_path)

            result.exported = True

            _trace.info(
                task.id, "auto_export_finished", TracePhase.PROCESSING,
                message=f"Research package exported: index + {source_note_count} source notes",
                output_summary={
                    "index_path": result.index_path,
                    "source_note_count": source_note_count,
                    "has_synthesis": synthesis is not None,
                },
            )

        except Exception as e:
            result.exported = False
            error_msg = str(e)[:200]
            result.errors.append(f"export: {error_msg}")

            _trace.record(
                task_id=task.id,
                step="auto_export_failed",
                phase=TracePhase.PROCESSING,
                level="warning",
                message=f"Export failed: {error_msg}",
                error_message=error_msg,
            )

            logger.warning(
                "auto_export_failed task_id=%s error=%s",
                task.id, error_msg,
            )

    def _export_filtered_noise(
        self,
        task: ResearchTask,
        all_sources: list[SourceItem],
        extracted_docs: dict[str, ExtractedDocument],
        vault_path: Path,
    ) -> None:
        """导出 filtered_noise.md - 被过滤的低质量/不相关来源。"""
        from utils.filesystem import ensure_dir, sanitize_filename, write_file

        research_dir = vault_path / "Research" / sanitize_filename(task.topic, max_length=80)
        ensure_dir(research_dir)
        noise_path = research_dir / "filtered_noise.md"

        # 收集被跳过的来源（B/C/D 级 + 低相关性）
        noise_sources = [
            s for s in all_sources
            if s.source_level.value in ("C", "D") or s.gossip_score >= 0.3
        ]

        if not noise_sources:
            return

        lines = [
            "---",
            f"title: {task.topic}｜被过滤噪音",
            "type: filtered_noise",
            "---",
            "",
            f"# {task.topic}｜被过滤来源",
            "",
            f"以下 {len(noise_sources)} 条来源因质量/相关性不足被排除在主要分析之外。",
            "",
        ]

        for s in noise_sources[:30]:
            lines.append(f"- [{s.title}]({s.url}) ({s.source_level.value}) — {s.reason_to_read}")

        lines.append("")
        write_file(noise_path, "\n".join(lines))

    def _export_trace_summary(
        self,
        task: ResearchTask,
        result: "AutoFetchResult",
        vault_path: Path,
    ) -> None:
        """导出 trace_summary.md - 执行过程摘要。"""
        from utils.filesystem import ensure_dir, sanitize_filename, write_file

        research_dir = vault_path / "Research" / sanitize_filename(task.topic, max_length=80)
        ensure_dir(research_dir)
        trace_path = research_dir / "trace_summary.md"

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

        lines = [
            "---",
            f"title: {task.topic}｜执行摘要",
            "type: trace_summary",
            f"generated: {now}",
            "---",
            "",
            f"# {task.topic}｜执行摘要",
            "",
            "## 自动抓取",
            "",
            f"- 选中来源数：{result.selected_count}",
            f"- 成功抓取：{result.fetched_count}",
            f"- 抓取失败：{result.failed_count}",
            f"- 跳过来源：{result.skipped_count}",
            f"- 已分析文档：{result.analyzed_count}",
            "",
            "## 导出",
            "",
            f"- 导出状态：{'✅ 成功' if result.exported else '❌ 失败'}",
            f"- Source Notes：{result.source_note_count} 篇",
            f"- Index 路径：{result.index_path or '未生成'}",
            "",
        ]

        if result.errors:
            lines.extend(["## 错误记录", ""])
            for err in result.errors[:10]:
                lines.append(f"- {err}")
            lines.append("")

        write_file(trace_path, "\n".join(lines))
