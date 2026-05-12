"""ReportLLMAnalyzer 单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.errors import LLMFallbackRequired
from app.ai.schemas import (
    ImportedSourcePrioritizationOutput,
    ReportReferenceExtractionOutput,
    ReportUnderstandingOutput,
    ImplicitReference,
    PrioritizedReference,
    ReportClaim,
)
from app.services.report_llm_analyzer import ReportLLMAnalyzer
from models.schemas import (
    ExtractedUrlReference,
    ParsedReport,
    ReferenceCandidate,
)
from models.enums import ReferenceType, ReferenceStatus


def _make_mock_gateway(return_value=None, side_effect=None):
    """创建 mock AIGateway。"""
    gateway = AsyncMock()
    if side_effect:
        gateway.run_json = AsyncMock(side_effect=side_effect)
    elif return_value:
        gateway.run_json = AsyncMock(return_value=return_value)
    else:
        gateway.run_json = AsyncMock(return_value=ReportUnderstandingOutput())
    return gateway


class TestUnderstandReport:
    @pytest.mark.asyncio
    async def test_calls_gateway_with_report_understanding(self):
        """understand_report 调用 ai_gateway task=report_understanding。"""
        expected = ReportUnderstandingOutput(
            main_topic="Tim Cook",
            main_entities=["Tim Cook"],
            people=["Tim Cook"],
        )
        gateway = _make_mock_gateway(return_value=expected)
        analyzer = ReportLLMAnalyzer(ai_gateway=gateway)

        result = await analyzer.understand_report("报告内容", "Tim Cook")

        gateway.run_json.assert_called_once()
        call_args = gateway.run_json.call_args
        assert call_args.kwargs["task_name"] == "report_understanding"
        assert call_args.kwargs["output_schema"] == ReportUnderstandingOutput
        assert result.main_topic == "Tim Cook"

    @pytest.mark.asyncio
    async def test_gateway_none_returns_empty(self):
        """ai_gateway=None 返回空结果。"""
        analyzer = ReportLLMAnalyzer(ai_gateway=None)
        result = await analyzer.understand_report("报告", "topic")
        assert result.main_topic == ""
        assert result.main_entities == []

    @pytest.mark.asyncio
    async def test_llm_error_returns_empty(self):
        """LLM 抛错时 fallback，不抛出主流程异常。"""
        gateway = _make_mock_gateway(
            side_effect=LLMFallbackRequired(
                task="report_understanding",
                fallback="empty_report_understanding",
                reason="timeout",
            )
        )
        analyzer = ReportLLMAnalyzer(ai_gateway=gateway)
        result = await analyzer.understand_report("报告", "topic")
        assert result.main_topic == ""

    @pytest.mark.asyncio
    async def test_report_text_truncated(self):
        """report_text 超长时被截断。"""
        gateway = _make_mock_gateway(return_value=ReportUnderstandingOutput())
        analyzer = ReportLLMAnalyzer(ai_gateway=gateway)

        long_text = "A" * 50000
        await analyzer.understand_report(long_text, "topic")

        call_args = gateway.run_json.call_args
        payload = call_args.kwargs["payload"]
        assert len(payload["report_text"]) <= 12000


class TestExtractImplicitReferences:
    @pytest.mark.asyncio
    async def test_calls_gateway_with_report_reference_extraction(self):
        """extract_implicit_references 调用 task=report_reference_extraction。"""
        expected = ReportReferenceExtractionOutput(
            additional_references=[
                ImplicitReference(type="book", title="Test Book", confidence=0.8)
            ]
        )
        gateway = _make_mock_gateway(return_value=expected)
        analyzer = ReportLLMAnalyzer(ai_gateway=gateway)

        parsed = ParsedReport(urls=[ExtractedUrlReference(url="https://example.com")])
        result = await analyzer.extract_implicit_references("报告", parsed, "topic")

        gateway.run_json.assert_called_once()
        call_args = gateway.run_json.call_args
        assert call_args.kwargs["task_name"] == "report_reference_extraction"
        assert len(result.additional_references) == 1

    @pytest.mark.asyncio
    async def test_gateway_none_returns_empty(self):
        """ai_gateway=None 返回空结果。"""
        analyzer = ReportLLMAnalyzer(ai_gateway=None)
        result = await analyzer.extract_implicit_references("报告", ParsedReport(), "topic")
        assert result.additional_references == []

    @pytest.mark.asyncio
    async def test_llm_error_returns_empty(self):
        """LLM 抛错时 fallback。"""
        gateway = _make_mock_gateway(side_effect=RuntimeError("network error"))
        analyzer = ReportLLMAnalyzer(ai_gateway=gateway)
        result = await analyzer.extract_implicit_references("报告", ParsedReport(), "topic")
        assert result.additional_references == []


class TestPrioritizeReferences:
    @pytest.mark.asyncio
    async def test_calls_gateway_with_imported_source_prioritization(self):
        """prioritize_references 调用 task=imported_source_prioritization。"""
        expected = ImportedSourcePrioritizationOutput(
            items=[PrioritizedReference(type="url", value="https://example.com", priority=1)]
        )
        gateway = _make_mock_gateway(return_value=expected)
        analyzer = ReportLLMAnalyzer(ai_gateway=gateway)

        candidates = [
            ReferenceCandidate(type=ReferenceType.URL, value="https://example.com")
        ]
        result = await analyzer.prioritize_references(candidates, "topic")

        gateway.run_json.assert_called_once()
        call_args = gateway.run_json.call_args
        assert call_args.kwargs["task_name"] == "imported_source_prioritization"
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_gateway_none_returns_empty(self):
        """ai_gateway=None 返回空结果。"""
        analyzer = ReportLLMAnalyzer(ai_gateway=None)
        result = await analyzer.prioritize_references([], "topic")
        assert result.items == []

    @pytest.mark.asyncio
    async def test_report_text_truncated_in_payload(self):
        """report_text 超长时被截断。"""
        gateway = _make_mock_gateway(return_value=ImportedSourcePrioritizationOutput())
        analyzer = ReportLLMAnalyzer(ai_gateway=gateway)

        long_context = "B" * 50000
        await analyzer.prioritize_references([], "topic", report_context=long_context)

        call_args = gateway.run_json.call_args
        payload = call_args.kwargs["payload"]
        assert len(payload["report_context"]) <= 2000
