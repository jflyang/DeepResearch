"""DocumentAnalysisService 单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.errors import LLMFallbackRequired
from app.ai.schemas import DocumentAnalysisOutput
from app.ai.tasks import LLMTaskConfig, reset_config_cache
from app.services.document_analysis_service import DocumentAnalysisService, ExtractedDocument


@pytest.fixture(autouse=True)
def _reset():
    reset_config_cache()
    yield
    reset_config_cache()


@pytest.fixture
def mock_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_gateway: AsyncMock) -> DocumentAnalysisService:
    return DocumentAnalysisService(ai_gateway=mock_gateway)


@pytest.fixture
def service_no_llm() -> DocumentAnalysisService:
    return DocumentAnalysisService(ai_gateway=None)


@pytest.fixture
def sample_doc() -> ExtractedDocument:
    return ExtractedDocument(
        url="https://example.com/article",
        title="量子计算综述",
        content="量子计算是一种利用量子力学原理进行计算的技术。" * 50,
        word_count=500,
    )


# === LLM 成功 ===


class TestLLMSuccess:
    @pytest.mark.asyncio
    async def test_returns_structured_analysis(
        self, service: DocumentAnalysisService, mock_gateway: AsyncMock, sample_doc: ExtractedDocument
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="本文综述了量子计算的最新进展",
            reason_to_read="核心综述论文",
            key_points=["量子优越性", "纠错码"],
            people=["Richard Feynman"],
            places=["MIT"],
            organizations=["IBM", "Google"],
            concepts=["量子比特", "量子纠缠"],
            story_points=["2019年量子优越性实验"],
            gossip_or_unverified_claims=[],
            verification_notes=["需核实最新数据"],
        ))

        result = await service.analyze(sample_doc, topic="量子计算")

        assert isinstance(result, DocumentAnalysisOutput)
        assert result.summary == "本文综述了量子计算的最新进展"
        assert result.reason_to_read == "核心综述论文"
        assert "量子优越性" in result.key_points
        assert "Richard Feynman" in result.people
        assert "IBM" in result.organizations
        assert "量子比特" in result.concepts
        assert "2019年量子优越性实验" in result.story_points
        assert "需核实最新数据" in result.verification_notes

    @pytest.mark.asyncio
    async def test_calls_with_correct_task(
        self, service: DocumentAnalysisService, mock_gateway: AsyncMock, sample_doc: ExtractedDocument
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput())

        await service.analyze(sample_doc, topic="test")

        mock_gateway.run_json.assert_called_once()
        call_kwargs = mock_gateway.run_json.call_args[1]
        assert call_kwargs["task_name"] == "document_summary"
        assert call_kwargs["output_schema"] is DocumentAnalysisOutput
        assert "topic" in call_kwargs["payload"]
        assert "content" in call_kwargs["payload"]


# === LLM 失败 fallback ===


class TestLLMFailure:
    @pytest.mark.asyncio
    async def test_fallback_returns_empty_output(
        self, service: DocumentAnalysisService, mock_gateway: AsyncMock, sample_doc: ExtractedDocument
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=LLMFallbackRequired(
            task="document_summary", reason="parse failed"
        ))

        result = await service.analyze(sample_doc, topic="test")

        assert isinstance(result, DocumentAnalysisOutput)
        assert result.summary == ""
        assert result.key_points == []
        assert result.people == []
        assert result.concepts == []

    @pytest.mark.asyncio
    async def test_runtime_error_returns_empty(
        self, service: DocumentAnalysisService, mock_gateway: AsyncMock, sample_doc: ExtractedDocument
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=RuntimeError("connection refused"))

        result = await service.analyze(sample_doc, topic="test")
        assert result.summary == ""
        assert result.key_points == []

    @pytest.mark.asyncio
    async def test_no_gateway_returns_empty(
        self, service_no_llm: DocumentAnalysisService, sample_doc: ExtractedDocument
    ) -> None:
        result = await service_no_llm.analyze(sample_doc, topic="test")
        assert isinstance(result, DocumentAnalysisOutput)
        assert result.summary == ""


# === 超长正文截断 ===


class TestInputTruncation:
    @pytest.mark.asyncio
    async def test_long_content_truncated(
        self, service: DocumentAnalysisService, mock_gateway: AsyncMock
    ) -> None:
        long_doc = ExtractedDocument(
            url="https://example.com/long",
            title="Long Article",
            content="X" * 100_000,
            word_count=50000,
        )
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(summary="ok"))

        await service.analyze(long_doc, topic="test")

        # 验证传给 LLM 的 content 被截断
        call_kwargs = mock_gateway.run_json.call_args[1]
        content_sent = call_kwargs["payload"]["content"]
        assert len(content_sent) <= 12000  # max_input_chars from config
        assert "[...TRUNCATED...]" in content_sent

    @pytest.mark.asyncio
    async def test_short_content_not_truncated(
        self, service: DocumentAnalysisService, mock_gateway: AsyncMock
    ) -> None:
        short_doc = ExtractedDocument(
            url="https://example.com/short",
            title="Short",
            content="短文内容",
            word_count=4,
        )
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput())

        await service.analyze(short_doc, topic="test")

        call_kwargs = mock_gateway.run_json.call_args[1]
        content_sent = call_kwargs["payload"]["content"]
        assert content_sent == "短文内容"
        assert "[...TRUNCATED...]" not in content_sent
