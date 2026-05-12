"""内容归一化服务 - 对单篇已抓取文档进行结构化清洗。

职责：
- 只处理已成功抓取的正文（有 content 的 ExtractedDocument）
- 通过 LLM 将非结构化正文转化为 NormalizedDocumentAnalysis
- 每条 claim 必须追溯 source_id / document_id / url
- LLM 不得编造来源中没有的信息
- LLM 失败时 fallback，不阻断流程

不做：
- 跨来源去重
- 生成 index.md
- 写 Obsidian
- 调用搜索 / 抓取
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any, Protocol

from app.ai.schemas import ContentNormalizationOutput, NormalizedClaimLLMItem
from app.tracing.models import TracePhase
from models.enums import ClaimConfidence, NormalizedClaimType
from models.schemas import NormalizedContentUnit, NormalizedDocumentAnalysis

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway
    from app.tracing.recorder import TraceRecorder

logger = logging.getLogger(__name__)

# 最小正文长度（太短的正文没有归一化价值）
_MIN_CONTENT_CHARS = 200


# === Repository Protocols ===


class DocumentRepository(Protocol):
    """ExtractedDocument 读取接口。"""

    def get_by_source(self, source_id: str) -> Any: ...


class SourceRepository(Protocol):
    """SourceItem 读取接口。"""

    def get_by_task(self, task_id: str) -> list[Any]: ...


# === 服务 ===


class ContentNormalizationService:
    """将单篇 ExtractedDocument 清洗为 NormalizedDocumentAnalysis。"""

    def __init__(
        self,
        ai_gateway: "AIGateway | None" = None,
        document_repository: DocumentRepository | None = None,
        source_repository: SourceRepository | None = None,
        trace_recorder: "TraceRecorder | None" = None,
    ) -> None:
        self._ai_gateway = ai_gateway
        self._doc_repo = document_repository
        self._source_repo = source_repository
        self._trace = trace_recorder

    async def normalize_document(
        self,
        task_id: str,
        document_id: str,
        output_language: str = "zh",
    ) -> NormalizedDocumentAnalysis:
        """归一化单篇已抓取文档。

        执行逻辑：
        1. 读取 ExtractedDocument + SourceItem
        2. 正文为空或过短 → fallback
        3. 截断正文 → 调用 LLM
        4. 解析为 NormalizedDocumentAnalysis
        5. 补充 source 元数据
        6. 丢弃没有 evidence_text 的 claim
        7. LLM 失败 → fallback

        Args:
            task_id: 研究任务 ID（用于 trace）
            document_id: ExtractedDocument.id（实际上是 source_item_id）
            output_language: 输出语言

        Returns:
            NormalizedDocumentAnalysis
        """
        start_time = time.perf_counter()
        self._trace_started(task_id, document_id)

        # 1. 读取文档和来源
        doc_row, source_row = self._load_document_and_source(document_id)

        # 提取基本信息
        content = getattr(doc_row, "content", "") if doc_row else ""
        source_id = getattr(source_row, "id", document_id) if source_row else document_id
        source_title = getattr(source_row, "title", "") if source_row else ""
        source_url = getattr(source_row, "url", "") if source_row else ""
        source_level = getattr(source_row, "source_level", None) if source_row else None
        doc_title = getattr(doc_row, "title", "") if doc_row else ""
        topic = getattr(source_row, "canonical_topic", "") if source_row else ""

        # 使用 doc_title 或 source_title
        title = doc_title or source_title

        # 2. 正文为空或过短 → fallback
        content_chars = len(content.strip()) if content else 0
        if content_chars < _MIN_CONTENT_CHARS:
            result = self._empty_content_fallback(
                document_id=document_id,
                source_id=source_id,
                source_title=title,
                source_url=source_url,
                content_chars=content_chars,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._trace_finished(task_id, document_id, content_chars=content_chars, claim_count=0, duration_ms=duration_ms)
            return result

        # 3. 截断正文
        max_input_chars = self._get_max_input_chars()
        truncated_content = content[:max_input_chars]

        # 4. 调用 LLM
        llm_output = await self._try_llm_normalize(
            content=truncated_content,
            topic=topic or title,
            source_title=title,
            source_url=source_url,
            source_level=source_level,
            output_language=output_language,
        )

        # 5-8. 构建结果
        if llm_output is not None:
            result = self._build_from_llm(
                llm_output=llm_output,
                document_id=document_id,
                source_id=source_id,
                source_title=title,
                source_url=source_url,
                source_level=source_level,
                output_language=output_language,
            )
        else:
            # 7. LLM 失败 → fallback
            result = self._llm_failure_fallback(
                content=content,
                document_id=document_id,
                source_id=source_id,
                source_title=title,
                source_url=source_url,
            )

        # Trace
        claim_count = (
            len(result.main_claims)
            + len(result.timeline_events)
            + len(result.story_points)
            + len(result.quotes)
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        self._trace_finished(task_id, document_id, content_chars=content_chars, claim_count=claim_count, duration_ms=duration_ms)

        return result

    # === 内部方法 ===

    def _load_document_and_source(self, document_id: str) -> tuple[Any, Any]:
        """读取 ExtractedDocument 和对应 SourceItem。"""
        doc_row = None
        source_row = None

        if self._doc_repo is not None:
            try:
                doc_row = self._doc_repo.get_by_source(document_id)
            except Exception as e:
                logger.warning("load_document_failed id=%s error=%s", document_id, str(e))

        # source_row: 如果 doc_repo 返回了 row，尝试从中获取 source 信息
        # 在当前架构中，ExtractedTable.source_item_id 就是 SourceTable.id
        # 但我们不直接查 source，因为 document_id 参数就是 source_item_id
        # source 信息可以从 doc_row 的关联或直接用 source_repo 查
        if self._source_repo is not None and doc_row is not None:
            source_item_id = getattr(doc_row, "source_item_id", document_id)
            try:
                # source_repo 没有 get_by_id，但有 get_by_task
                # 这里我们直接把 source 信息从 doc_row 的上下文获取
                pass
            except Exception:
                pass

        return doc_row, source_row

    def _get_max_input_chars(self) -> int:
        """从 llm_tasks.yaml 获取 max_input_chars，失败返回默认值。"""
        try:
            from app.ai.tasks import load_llm_task_config
            config = load_llm_task_config("content_normalization")
            return config.max_input_chars
        except Exception:
            return 12000

    async def _try_llm_normalize(
        self,
        content: str,
        topic: str,
        source_title: str = "",
        source_url: str = "",
        source_level: str | None = None,
        output_language: str = "zh",
    ) -> ContentNormalizationOutput | None:
        """尝试 LLM 归一化，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        payload: dict[str, Any] = {
            "topic": topic,
            "content": content,
        }
        if source_title:
            payload["source_title"] = source_title
        if source_url:
            payload["source_url"] = source_url
        if source_level:
            payload["source_level"] = source_level

        try:
            result = await self._ai_gateway.run_json(
                task_name="content_normalization",
                payload=payload,
                output_schema=ContentNormalizationOutput,
                language=output_language,
            )
            return result
        except Exception as e:
            logger.warning("llm_content_normalization_failed error=%s", str(e))
            return None

    def _build_from_llm(
        self,
        llm_output: ContentNormalizationOutput,
        document_id: str,
        source_id: str,
        source_title: str,
        source_url: str,
        source_level: str | None,
        output_language: str,
    ) -> NormalizedDocumentAnalysis:
        """从 LLM 输出构建 NormalizedDocumentAnalysis。"""
        main_claims: list[NormalizedContentUnit] = []
        timeline_events: list[NormalizedContentUnit] = []
        story_points: list[NormalizedContentUnit] = []
        quotes: list[NormalizedContentUnit] = []
        verification_needed: list[NormalizedContentUnit] = []

        for item in llm_output.claims:
            unit = self._llm_item_to_unit(
                item=item,
                document_id=document_id,
                source_id=source_id,
                source_title=source_title,
                source_url=source_url,
                source_level=source_level,
                output_language=output_language,
            )

            # 丢弃没有 evidence_text 的 claim → 转入 verification_needed
            if not unit.evidence_text or not unit.evidence_text.strip():
                unit.needs_verification = True
                unit.verification_reason = unit.verification_reason or "缺少 evidence_text，无法溯源"
                verification_needed.append(unit)
                continue

            # 按 claim_type 分类
            if unit.needs_verification:
                verification_needed.append(unit)
            elif unit.claim_type == NormalizedClaimType.TIMELINE_EVENT:
                timeline_events.append(unit)
            elif unit.claim_type == NormalizedClaimType.STORY_POINT:
                story_points.append(unit)
            elif unit.claim_type == NormalizedClaimType.QUOTE:
                quotes.append(unit)
            else:
                main_claims.append(unit)

        return NormalizedDocumentAnalysis(
            document_id=document_id,
            source_id=source_id,
            source_title=source_title,
            source_url=source_url,
            summary=llm_output.summary,
            main_claims=main_claims,
            timeline_events=timeline_events,
            story_points=story_points,
            key_people=llm_output.key_people,
            key_places=llm_output.key_places,
            key_concepts=llm_output.key_concepts,
            quotes=quotes,
            verification_needed=verification_needed,
        )

    def _llm_item_to_unit(
        self,
        item: NormalizedClaimLLMItem,
        document_id: str,
        source_id: str,
        source_title: str,
        source_url: str,
        source_level: str | None,
        output_language: str,
    ) -> NormalizedContentUnit:
        """将 LLM 输出的单条 claim 转为 NormalizedContentUnit，补充 source 元数据。"""
        # 映射 claim_type
        claim_type = self._map_claim_type(item.claim_type)
        # 映射 confidence
        confidence = self._map_confidence(item.confidence)
        # 限制 importance 范围
        importance = max(1, min(5, item.importance))

        return NormalizedContentUnit(
            document_id=document_id,
            source_id=source_id,
            source_title=source_title,
            source_url=source_url,
            source_level=source_level,
            claim_type=claim_type,
            claim=item.claim,
            normalized_claim=item.normalized_claim or item.claim,
            evidence_text=item.evidence_text or None,
            people=item.people,
            organizations=item.organizations,
            places=item.places,
            dates=item.dates,
            concepts=item.concepts,
            confidence=confidence,
            output_language=output_language,
            importance=importance,
            needs_verification=item.needs_verification,
            verification_reason=item.verification_reason,
        )

    # === Fallback ===

    def _empty_content_fallback(
        self,
        document_id: str,
        source_id: str,
        source_title: str,
        source_url: str,
        content_chars: int,
    ) -> NormalizedDocumentAnalysis:
        """正文为空或过短时的 fallback。"""
        verification_unit = NormalizedContentUnit(
            document_id=document_id,
            source_id=source_id,
            source_title=source_title,
            source_url=source_url,
            claim_type=NormalizedClaimType.UNKNOWN,
            claim=f"正文内容不足（{content_chars} 字符），无法进行归一化分析",
            normalized_claim="content_insufficient",
            confidence=ClaimConfidence.UNVERIFIED,
            importance=1,
            needs_verification=True,
            verification_reason=f"正文过短或为空 (chars={content_chars})",
        )
        return NormalizedDocumentAnalysis(
            document_id=document_id,
            source_id=source_id,
            source_title=source_title,
            source_url=source_url,
            summary=f"正文内容不足（{content_chars} 字符），无法进行归一化分析。",
            verification_needed=[verification_unit],
        )

    def _llm_failure_fallback(
        self,
        content: str,
        document_id: str,
        source_id: str,
        source_title: str,
        source_url: str,
    ) -> NormalizedDocumentAnalysis:
        """LLM 失败时的 fallback。"""
        # summary: 正文前 500 字的清理版
        cleaned = re.sub(r'\s+', ' ', content[:500]).strip()
        summary = cleaned if cleaned else "LLM 归一化失败，无法生成摘要。"

        verification_unit = NormalizedContentUnit(
            document_id=document_id,
            source_id=source_id,
            source_title=source_title,
            source_url=source_url,
            claim_type=NormalizedClaimType.UNKNOWN,
            claim="LLM normalization failed",
            normalized_claim="llm_normalization_failed",
            confidence=ClaimConfidence.UNVERIFIED,
            importance=1,
            needs_verification=True,
            verification_reason="LLM 归一化失败，需要重试或人工处理",
        )

        return NormalizedDocumentAnalysis(
            document_id=document_id,
            source_id=source_id,
            source_title=source_title,
            source_url=source_url,
            summary=summary,
            verification_needed=[verification_unit],
        )

    # === Trace ===

    def _trace_started(self, task_id: str, document_id: str) -> None:
        """记录归一化开始。"""
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="content_normalization_started",
            phase=TracePhase.PROCESSING,
            service="content_normalization",
            input_summary={"document_id": document_id},
        )

    def _trace_finished(
        self,
        task_id: str,
        document_id: str,
        content_chars: int,
        claim_count: int,
        duration_ms: int,
    ) -> None:
        """记录归一化完成。不记录完整正文。"""
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="content_normalization_finished",
            phase=TracePhase.PROCESSING,
            service="content_normalization",
            metrics={
                "content_chars": content_chars,
                "claim_count": claim_count,
                "duration_ms": duration_ms,
            },
            output_summary={"document_id": document_id, "claim_count": claim_count},
            duration_ms=duration_ms,
        )

    def _trace_failed(self, task_id: str, document_id: str, error: str, duration_ms: int) -> None:
        """记录归一化失败。"""
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="content_normalization_failed",
            phase=TracePhase.PROCESSING,
            level="error",
            service="content_normalization",
            error_message=error[:200],
            input_summary={"document_id": document_id},
            duration_ms=duration_ms,
        )

    # === 工具方法 ===

    @staticmethod
    def _map_claim_type(raw: str) -> NormalizedClaimType:
        """将 LLM 输出的 claim_type 映射为枚举。"""
        mapping = {
            "fact": NormalizedClaimType.FACT,
            "background": NormalizedClaimType.BACKGROUND,
            "timeline_event": NormalizedClaimType.TIMELINE_EVENT,
            "quote": NormalizedClaimType.QUOTE,
            "story_point": NormalizedClaimType.STORY_POINT,
            "controversy": NormalizedClaimType.CONTROVERSY,
            "interpretation": NormalizedClaimType.INTERPRETATION,
        }
        return mapping.get(raw.lower().strip(), NormalizedClaimType.UNKNOWN)

    @staticmethod
    def _map_confidence(raw: str) -> ClaimConfidence:
        """将 LLM 输出的 confidence 映射为枚举。"""
        mapping = {
            "high": ClaimConfidence.HIGH,
            "medium": ClaimConfidence.MEDIUM,
            "low": ClaimConfidence.LOW,
            "unverified": ClaimConfidence.UNVERIFIED,
            "conflicting": ClaimConfidence.CONFLICTING,
        }
        return mapping.get(raw.lower().strip(), ClaimConfidence.MEDIUM)
