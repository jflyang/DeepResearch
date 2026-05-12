"""报告 LLM 分析器 - 基于外部报告文本做 LLM 增强分析。

职责：只做 LLM 分析，不抓网页，不搜索，不写数据库。
LLM 失败时返回空结果，不抛出导致主流程失败的异常。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.ai.errors import LLMFallbackRequired, LLMTaskFailed
from app.ai.schemas import (
    ImportedSourcePrioritizationOutput,
    ReportReferenceExtractionOutput,
    ReportUnderstandingOutput,
)

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway
    from models.schemas import ParsedReport, ReferenceCandidate

logger = logging.getLogger(__name__)

# 默认截断长度（与 llm_tasks.yaml 中 max_input_chars 对齐）
_DEFAULT_MAX_INPUT_CHARS = 12000


class ReportLLMAnalyzer:
    """报告 LLM 分析器。

    ai_gateway 为 None 时所有方法返回空结果。
    LLM 失败时返回空结果并记录 fallback。
    """

    def __init__(self, ai_gateway: "AIGateway | None") -> None:
        self._gateway = ai_gateway

    @property
    def available(self) -> bool:
        return self._gateway is not None

    async def understand_report(
        self,
        report_text: str,
        topic: str,
        output_language: str = "zh",
    ) -> ReportUnderstandingOutput:
        """理解报告，识别研究线索和待验证 claims。"""
        if not self._gateway:
            return ReportUnderstandingOutput()

        truncated = report_text[:_DEFAULT_MAX_INPUT_CHARS]
        payload = {"report_text": truncated, "topic": topic}

        try:
            return await self._gateway.run_json(
                task_name="report_understanding",
                payload=payload,
                output_schema=ReportUnderstandingOutput,
                language=output_language,
            )
        except (LLMFallbackRequired, LLMTaskFailed) as e:
            logger.warning(
                "report_understanding_fallback reason=%s", str(e)[:200]
            )
            return ReportUnderstandingOutput()
        except Exception as e:
            logger.warning(
                "report_understanding_error error=%s", str(e)[:200]
            )
            return ReportUnderstandingOutput()

    async def extract_implicit_references(
        self,
        report_text: str,
        parsed_report: "ParsedReport",
        topic: str,
        output_language: str = "zh",
    ) -> ReportReferenceExtractionOutput:
        """从报告中识别规则可能漏掉的隐性引用。"""
        if not self._gateway:
            return ReportReferenceExtractionOutput()

        truncated = report_text[:_DEFAULT_MAX_INPUT_CHARS]

        # 构建已提取引用摘要（不传完整数据）
        existing_refs = []
        for u in parsed_report.urls[:20]:
            existing_refs.append({"type": "url", "value": u.url})
        for b in parsed_report.books[:10]:
            existing_refs.append({"type": "book", "value": b.title})
        for p in parsed_report.papers[:10]:
            existing_refs.append({"type": "paper", "value": p.title})

        payload = {
            "report_text": truncated,
            "topic": topic,
            "existing_references": existing_refs,
        }

        try:
            return await self._gateway.run_json(
                task_name="report_reference_extraction",
                payload=payload,
                output_schema=ReportReferenceExtractionOutput,
                language=output_language,
            )
        except (LLMFallbackRequired, LLMTaskFailed) as e:
            logger.warning(
                "report_reference_extraction_fallback reason=%s", str(e)[:200]
            )
            return ReportReferenceExtractionOutput()
        except Exception as e:
            logger.warning(
                "report_reference_extraction_error error=%s", str(e)[:200]
            )
            return ReportReferenceExtractionOutput()

    async def prioritize_references(
        self,
        candidates: list["ReferenceCandidate"],
        topic: str,
        report_context: str | None = None,
    ) -> ImportedSourcePrioritizationOutput:
        """对引用候选进行优先级排序。"""
        if not self._gateway:
            return ImportedSourcePrioritizationOutput()

        # 构建候选摘要
        candidate_summaries = []
        for c in candidates[:50]:
            candidate_summaries.append({
                "type": c.type.value if hasattr(c.type, "value") else str(c.type),
                "value": c.value[:200],
                "title_hint": c.title_hint,
            })

        payload = {
            "candidates": candidate_summaries,
            "topic": topic,
            "report_context": (report_context or "")[:2000],
        }

        try:
            return await self._gateway.run_json(
                task_name="imported_source_prioritization",
                payload=payload,
                output_schema=ImportedSourcePrioritizationOutput,
                language="zh",
            )
        except (LLMFallbackRequired, LLMTaskFailed) as e:
            logger.warning(
                "imported_source_prioritization_fallback reason=%s", str(e)[:200]
            )
            return ImportedSourcePrioritizationOutput()
        except Exception as e:
            logger.warning(
                "imported_source_prioritization_error error=%s", str(e)[:200]
            )
            return ImportedSourcePrioritizationOutput()
