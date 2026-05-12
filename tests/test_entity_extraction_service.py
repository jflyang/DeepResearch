"""EntityExtractionService 单元测试。"""

from unittest.mock import AsyncMock

import pytest

from app.ai.errors import LLMFallbackRequired
from app.ai.schemas import EntityExtractionOutput, EntityType, ExtractedEntity
from app.ai.tasks import reset_config_cache
from app.services.entity_extraction_service import EntityCandidate, EntityExtractionService


@pytest.fixture(autouse=True)
def _reset():
    reset_config_cache()
    yield
    reset_config_cache()


@pytest.fixture
def mock_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_gateway: AsyncMock) -> EntityExtractionService:
    return EntityExtractionService(ai_gateway=mock_gateway)


@pytest.fixture
def service_no_llm() -> EntityExtractionService:
    return EntityExtractionService(ai_gateway=None)


# === LLM 成功 ===


class TestLLMSuccess:
    @pytest.mark.asyncio
    async def test_extracts_entities(self, service: EntityExtractionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=EntityExtractionOutput(
            entities=[
                ExtractedEntity(
                    name="OpenAI",
                    type=EntityType.company,
                    description="AI research company",
                    relation_to_topic="GPT 系列模型开发者",
                    should_expand=True,
                ),
                ExtractedEntity(
                    name="Sam Altman",
                    type=EntityType.person,
                    description="CEO of OpenAI",
                    relation_to_topic="公司领导者",
                    should_expand=False,
                ),
            ]
        ))

        results = await service.extract(
            topic="GPT-4",
            text="OpenAI 由 Sam Altman 领导，发布了 GPT-4 模型。",
            source_url="https://example.com/article",
        )

        assert len(results) == 2
        assert all(isinstance(r, EntityCandidate) for r in results)

        openai = next(r for r in results if r.name == "OpenAI")
        assert openai.type == "company"
        assert openai.description == "AI research company"
        assert openai.relation_to_topic == "GPT 系列模型开发者"
        assert openai.source_url == "https://example.com/article"
        assert openai.should_expand is True
        assert openai.confidence == "high"

        sam = next(r for r in results if r.name == "Sam Altman")
        assert sam.type == "person"
        assert sam.should_expand is False
        assert sam.confidence == "medium"

    @pytest.mark.asyncio
    async def test_all_entity_types(self, service: EntityExtractionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=EntityExtractionOutput(
            entities=[
                ExtractedEntity(name="北京", type=EntityType.place),
                ExtractedEntity(name="量子纠缠", type=EntityType.concept),
                ExtractedEntity(name="GPT-4", type=EntityType.product),
            ]
        ))

        results = await service.extract(topic="AI", text="some text", source_url="")
        types = {r.name: r.type for r in results}
        assert types["北京"] == "place"
        assert types["量子纠缠"] == "concept"
        assert types["GPT-4"] == "product"


# === LLM 失败 fallback ===


class TestLLMFailure:
    @pytest.mark.asyncio
    async def test_fallback_returns_empty_list(
        self, service: EntityExtractionService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=LLMFallbackRequired(
            task="entity_extraction", reason="parse failed"
        ))

        results = await service.extract(topic="test", text="some content", source_url="")
        assert results == []

    @pytest.mark.asyncio
    async def test_runtime_error_returns_empty(
        self, service: EntityExtractionService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=RuntimeError("timeout"))

        results = await service.extract(topic="test", text="content", source_url="")
        assert results == []

    @pytest.mark.asyncio
    async def test_no_gateway_returns_empty(self, service_no_llm: EntityExtractionService) -> None:
        results = await service_no_llm.extract(topic="test", text="content", source_url="")
        assert results == []


# === 空文本 ===


class TestEmptyInput:
    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self, service: EntityExtractionService) -> None:
        results = await service.extract(topic="test", text="", source_url="")
        assert results == []

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty(self, service: EntityExtractionService) -> None:
        results = await service.extract(topic="test", text="   \n\t  ", source_url="")
        assert results == []

    @pytest.mark.asyncio
    async def test_no_llm_empty_text(self, service_no_llm: EntityExtractionService) -> None:
        results = await service_no_llm.extract(topic="test", text="", source_url="")
        assert results == []
