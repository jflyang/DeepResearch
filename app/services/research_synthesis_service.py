"""研究合成服务 - 编排归一化、去重、LLM 合成，生成最终研究文档对象。

职责：
- 读取 task 下已抓取成功的 ExtractedDocument
- 单篇内容归一化 → 跨来源去重 → LLM 合成
- 返回 SynthesizedResearchDocument
- 不写 Markdown、不写 Obsidian、不修改数据库
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from app.ai.schemas import ResearchSynthesisOutput
from app.services.content_normalization_service import ContentNormalizationService
from app.services.cross_source_deduplication_service import CrossSourceDeduplicationService
from app.tracing.models import TracePhase
from models.enums import ClaimConfidence
from models.schemas import (
    DeduplicatedClaimGroup,
    NormalizedDocumentAnalysis,
    SynthesizedResearchDocument,
)

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway
    from app.tracing.recorder import TraceRecorder

logger = logging.getLogger(__name__)

# 最小正文长度（低于此值的文档跳过归一化）
_MIN_CONTENT_CHARS = 200


# === Repository Protocols ===


class TaskRepository(Protocol):
    def get_task(self, task_id: str) -> Any: ...


class DocumentRepository(Protocol):
    def get_by_source(self, source_id: str) -> Any: ...


class SourceRepository(Protocol):
    def get_by_task(self, task_id: str) -> list[Any]: ...


# === 服务 ===


class ResearchSynthesisService:
    """编排归一化 → 去重 → 合成，生成 SynthesizedResearchDocument。"""

    def __init__(
        self,
        content_normalization_service: ContentNormalizationService,
        deduplication_service: CrossSourceDeduplicationService,
        ai_gateway: "AIGateway | None" = None,
        task_repository: TaskRepository | None = None,
        document_repository: DocumentRepository | None = None,
        source_repository: SourceRepository | None = None,
        trace_recorder: "TraceRecorder | None" = None,
    ) -> None:
        self._normalization = content_normalization_service
        self._deduplication = deduplication_service
        self._ai_gateway = ai_gateway
        self._task_repo = task_repository
        self._doc_repo = document_repository
        self._source_repo = source_repository
        self._trace = trace_recorder

    async def synthesize_task(
        self,
        task_id: str,
        output_language: str = "zh",
    ) -> SynthesizedResearchDocument:
        """生成研究文档对象。

        Args:
            task_id: 研究任务 ID
            output_language: 输出语言

        Returns:
            SynthesizedResearchDocument
        """
        start_time = time.perf_counter()
        self._trace_started(task_id)

        # 1. 读取 ResearchTask
        task_row = self._load_task(task_id)
        topic = getattr(task_row, "topic", "") if task_row else ""
        canonical_topic = getattr(task_row, "canonical_topic", None) if task_row else None
        mode = getattr(task_row, "mode", "auto") if task_row else "auto"

        # 2. 读取 task 下已抓取成功的 ExtractedDocument
        sources = self._load_sources(task_id)
        documents = self._load_extracted_documents(sources)

        # 3. 过滤不适合合成的文档
        eligible_docs = self._filter_eligible_documents(documents, sources)

        # 如果没有足够文档 → 返回资料不足
        if not eligible_docs:
            result = self._insufficient_data_result(task_id, topic, canonical_topic)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._trace_finished(task_id, metrics={
                "document_count": len(documents),
                "normalized_count": 0,
                "skipped_count": len(documents),
                "claim_count": 0,
                "deduplicated_group_count": 0,
                "confirmed_fact_count": 0,
                "verification_needed_count": 0,
                "used_llm": False,
                "duration_ms": duration_ms,
            })
            return result

        # 4. 对每篇文档调用 ContentNormalizationService
        analyses: list[NormalizedDocumentAnalysis] = []
        skipped_count = len(documents) - len(eligible_docs)

        for source_id, doc_row in eligible_docs:
            try:
                analysis = await self._normalization.normalize_document(
                    task_id=task_id,
                    document_id=source_id,
                    output_language=output_language,
                )
                analyses.append(analysis)
            except Exception as e:
                logger.warning(
                    "normalization_skipped source_id=%s error=%s", source_id, str(e)
                )
                skipped_count += 1

        # 5. 如果归一化后没有有效 analysis → 资料不足
        if not analyses:
            result = self._insufficient_data_result(task_id, topic, canonical_topic)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._trace_finished(task_id, metrics={
                "document_count": len(documents),
                "normalized_count": 0,
                "skipped_count": skipped_count,
                "claim_count": 0,
                "deduplicated_group_count": 0,
                "confirmed_fact_count": 0,
                "verification_needed_count": 0,
                "used_llm": False,
                "duration_ms": duration_ms,
            })
            return result

        # 6. 跨来源去重
        dedup_groups = await self._deduplication.deduplicate(
            task_id=task_id,
            analyses=analyses,
        )

        # 7-8. LLM 合成
        used_llm = False
        llm_output = await self._try_llm_synthesize(dedup_groups, topic, canonical_topic, mode)

        if llm_output is not None:
            result = self._build_from_llm(llm_output, dedup_groups, task_id, topic, canonical_topic)
            used_llm = True
        else:
            # 10. 规则 fallback
            result = self._rule_based_synthesis(dedup_groups, task_id, topic, canonical_topic)

        # 9. 补充元数据
        result.task_id = task_id
        result.topic = topic
        result.canonical_topic = canonical_topic
        result.generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

        # Trace
        total_claims = sum(
            len(a.main_claims) + len(a.timeline_events) + len(a.story_points)
            + len(a.quotes) + len(a.verification_needed)
            for a in analyses
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        self._trace_finished(task_id, metrics={
            "document_count": len(documents),
            "normalized_count": len(analyses),
            "skipped_count": skipped_count,
            "claim_count": total_claims,
            "deduplicated_group_count": len(dedup_groups),
            "confirmed_fact_count": len(result.confirmed_facts),
            "verification_needed_count": len(result.verification_needed),
            "used_llm": used_llm,
            "duration_ms": duration_ms,
        })

        return result

    # === 数据加载 ===

    def _load_task(self, task_id: str) -> Any:
        """读取 ResearchTask。"""
        if self._task_repo is None:
            return None
        try:
            return self._task_repo.get_task(task_id)
        except Exception as e:
            logger.warning("load_task_failed task_id=%s error=%s", task_id, str(e))
            return None

    def _load_sources(self, task_id: str) -> list[Any]:
        """读取 task 下所有 sources。"""
        if self._source_repo is None:
            return []
        try:
            return self._source_repo.get_by_task(task_id)
        except Exception as e:
            logger.warning("load_sources_failed task_id=%s error=%s", task_id, str(e))
            return []

    def _load_extracted_documents(self, sources: list[Any]) -> list[tuple[str, Any]]:
        """读取已抓取成功的 ExtractedDocument。返回 (source_id, doc_row) 列表。"""
        if self._doc_repo is None:
            return []

        results: list[tuple[str, Any]] = []
        for source in sources:
            source_id = getattr(source, "id", "")
            download_status = getattr(source, "download_status", "")

            # 只处理已抓取成功的
            if download_status not in ("extracted", "exported"):
                continue

            try:
                doc_row = self._doc_repo.get_by_source(source_id)
                if doc_row:
                    results.append((source_id, doc_row))
            except Exception:
                continue

        return results

    def _filter_eligible_documents(
        self,
        documents: list[tuple[str, Any]],
        sources: list[Any],
    ) -> list[tuple[str, Any]]:
        """过滤不适合合成的文档。

        只允许 S/A/B 级来源参与合成，C/D 级排除。
        """
        from app.services.research_service import load_normalization_policy

        policy = load_normalization_policy()
        include_levels = policy.get("include_levels", ["S", "A", "B"])

        # 构建 source_id → source_row 映射
        source_map: dict[str, Any] = {}
        for s in sources:
            sid = getattr(s, "id", "")
            if sid:
                source_map[sid] = s

        eligible: list[tuple[str, Any]] = []
        for source_id, doc_row in documents:
            content = getattr(doc_row, "content", "") or ""

            # content_chars 太少
            if len(content.strip()) < _MIN_CONTENT_CHARS:
                continue

            # source_level 不在 include_levels 中则跳过
            source_row = source_map.get(source_id)
            if source_row:
                level = getattr(source_row, "source_level", "C")
                if level not in include_levels:
                    continue

            eligible.append((source_id, doc_row))

        return eligible

    # === LLM 合成 ===

    async def _try_llm_synthesize(
        self,
        groups: list[DeduplicatedClaimGroup],
        topic: str,
        canonical_topic: str | None,
        mode: str,
    ) -> ResearchSynthesisOutput | None:
        """尝试 LLM 合成，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        if not groups:
            return None

        # 构建 LLM 输入
        groups_for_llm = []
        for g in groups:
            groups_for_llm.append({
                "merged_claim": g.merged_claim[:300],
                "claim_type": g.claim_type,
                "confidence": g.confidence.value,
                "importance": g.importance,
                "supporting_sources": [
                    {"title": s.get("title", ""), "url": s.get("url", "")}
                    for s in g.supporting_sources[:3]
                ],
                "conflicting_sources": [
                    {"title": s.get("title", ""), "claim": s.get("claim", "")}
                    for s in g.conflicting_sources[:2]
                ],
                "needs_verification": g.needs_verification,
            })

        try:
            result = await self._ai_gateway.run_json(
                task_name="research_synthesis",
                payload={
                    "topic": topic,
                    "canonical_topic": canonical_topic or "",
                    "mode": mode,
                    "total_sources": len(set(
                        s.get("source_id", "")
                        for g in groups
                        for s in g.supporting_sources
                    )),
                    "groups": groups_for_llm,
                },
                output_schema=ResearchSynthesisOutput,
                language="zh",
            )
            return result
        except Exception as e:
            logger.warning("llm_synthesis_failed error=%s", str(e))
            return None

    def _build_from_llm(
        self,
        llm_output: ResearchSynthesisOutput,
        groups: list[DeduplicatedClaimGroup],
        task_id: str,
        topic: str,
        canonical_topic: str | None,
    ) -> SynthesizedResearchDocument:
        """从 LLM 输出构建 SynthesizedResearchDocument。"""
        # 分类 groups
        confirmed = [g for g in groups if g.confidence == ClaimConfidence.HIGH and g.supporting_sources]
        timeline = [g for g in groups if g.claim_type == "timeline_event"]
        story_points = [g for g in groups if g.claim_type == "story_point"]
        controversies = [g for g in groups if g.conflicting_sources or g.confidence == ClaimConfidence.CONFLICTING]
        verification_needed = [g for g in groups if g.needs_verification]

        # 时间线排序
        timeline.sort(key=lambda g: self._sort_key_for_dates(g.dates))

        # 构建 source_map
        source_map = self._build_source_map(groups)

        return SynthesizedResearchDocument(
            task_id=task_id,
            topic=topic,
            canonical_topic=canonical_topic,
            overview=llm_output.overview,
            executive_summary=llm_output.executive_summary,
            confirmed_facts=confirmed,
            timeline=timeline,
            key_people=llm_output.key_people,
            key_places=llm_output.key_places,
            key_concepts=llm_output.key_concepts,
            story_points=story_points,
            controversies=controversies,
            verification_needed=verification_needed,
            source_map=source_map,
            suggested_next_steps=llm_output.suggested_next_steps or llm_output.unresolved_questions,
        )

    # === 规则 Fallback ===

    def _rule_based_synthesis(
        self,
        groups: list[DeduplicatedClaimGroup],
        task_id: str,
        topic: str,
        canonical_topic: str | None,
    ) -> SynthesizedResearchDocument:
        """规则 fallback 合成。"""
        confirmed = [g for g in groups if g.confidence == ClaimConfidence.HIGH and g.supporting_sources]
        timeline = [g for g in groups if g.claim_type == "timeline_event"]
        story_points = [g for g in groups if g.claim_type == "story_point"]
        controversies = [g for g in groups if g.conflicting_sources or g.confidence == ClaimConfidence.CONFLICTING]
        verification_needed = [g for g in groups if g.needs_verification]

        # 时间线排序
        timeline.sort(key=lambda g: self._sort_key_for_dates(g.dates))

        # 生成 overview
        total_sources = len(set(
            s.get("source_id", "")
            for g in groups
            for s in g.supporting_sources
        ))
        overview = (
            f"本研究围绕「{topic}」展开，"
            f"共整理 {len(groups)} 条事实组，来自 {total_sources} 个独立来源。"
            f"其中高置信度事实 {len(confirmed)} 条，"
            f"待核验信息 {len(verification_needed)} 条。"
        )
        if controversies:
            overview += f"\n\n⚠️ 发现 {len(controversies)} 处来源冲突，已标记为待核验。"
        if not confirmed:
            overview += "\n\n⚠️ 当前没有高置信度事实，建议补充更多一手资料。"

        # executive_summary
        top_facts = sorted(confirmed, key=lambda g: g.importance, reverse=True)[:3]
        if top_facts:
            summary_parts = [g.merged_claim for g in top_facts]
            executive_summary = "；".join(summary_parts) + "。"
        else:
            executive_summary = f"关于「{topic}」的研究资料尚不充分，需要补充更多来源。"

        # source_map
        source_map = self._build_source_map(groups)

        # next_steps
        next_steps = []
        if verification_needed:
            next_steps.append("核验待确认的事实")
        if controversies:
            next_steps.append("解决来源冲突")
        if len(confirmed) < 5:
            next_steps.append("补充更多一手资料以提高事实覆盖度")
        if not next_steps:
            next_steps.append("深入研究已确认事实的细节")

        return SynthesizedResearchDocument(
            task_id=task_id,
            topic=topic,
            canonical_topic=canonical_topic,
            overview=overview,
            executive_summary=executive_summary,
            confirmed_facts=confirmed,
            timeline=timeline,
            key_people=[],
            key_places=[],
            key_concepts=[],
            story_points=story_points,
            controversies=controversies,
            verification_needed=verification_needed,
            source_map=source_map,
            suggested_next_steps=next_steps,
        )

    # === 资料不足 ===

    @staticmethod
    def _insufficient_data_result(
        task_id: str,
        topic: str,
        canonical_topic: str | None,
    ) -> SynthesizedResearchDocument:
        """没有足够文档时返回资料不足的 synthesis。"""
        return SynthesizedResearchDocument(
            task_id=task_id,
            topic=topic,
            canonical_topic=canonical_topic,
            overview=f"研究主题「{topic}」暂无已提取的正文资料可供合成。请先抓取来源正文。",
            executive_summary="资料不足，无法生成研究摘要。",
            suggested_next_steps=[
                "提取已保存来源的正文",
                "扩展搜索更多一手资料",
                "检查抓取是否成功完成",
            ],
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        )

    # === 工具方法 ===

    @staticmethod
    def _build_source_map(groups: list[DeduplicatedClaimGroup]) -> list[dict]:
        """构建来源映射（去重）。"""
        seen: set[str] = set()
        source_map: list[dict] = []
        for g in groups:
            for s in g.supporting_sources:
                sid = s.get("source_id", "")
                if sid and sid not in seen:
                    seen.add(sid)
                    source_map.append({
                        "source_id": sid,
                        "title": s.get("title", ""),
                        "url": s.get("url", ""),
                    })
        return source_map

    @staticmethod
    def _sort_key_for_dates(dates: list[str]) -> str:
        """为时间线排序生成 sort key。"""
        if not dates:
            return "9999"
        # 取最早的日期
        return min(dates)

    # === Trace ===

    def _trace_started(self, task_id: str) -> None:
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="research_synthesis_started",
            phase=TracePhase.PROCESSING,
            service="research_synthesis",
        )

    def _trace_finished(self, task_id: str, metrics: dict[str, Any]) -> None:
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="research_synthesis_finished",
            phase=TracePhase.PROCESSING,
            service="research_synthesis",
            metrics=metrics,
            duration_ms=metrics.get("duration_ms"),
        )

    def _trace_failed(self, task_id: str, error: str, duration_ms: int) -> None:
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="research_synthesis_failed",
            phase=TracePhase.PROCESSING,
            level="error",
            service="research_synthesis",
            error_message=error[:200],
            duration_ms=duration_ms,
        )
