"""QueryExpansionService LLM 增强测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.errors import LLMFallbackRequired
from app.ai.schemas import ExpandedQueryItem, QueryExpansionOutput, SourceHint
from models.enums import TaskMode
from services.query_expansion_service import ExpandedQuery, QueryExpansionService


@pytest.fixture
def mock_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_gateway: AsyncMock) -> QueryExpansionService:
    return QueryExpansionService(ai_gateway=mock_gateway)


@pytest.fixture
def service_no_llm() -> QueryExpansionService:
    return QueryExpansionService(ai_gateway=None)


# === LLM 成功 ===


class TestLLMSuccess:
    @pytest.mark.asyncio
    async def test_includes_llm_queries(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=QueryExpansionOutput(
            queries=[
                ExpandedQueryItem(query="quantum computing breakthroughs 2024", purpose="recent", source_hint=SourceHint.web, priority=5),
                ExpandedQueryItem(query="quantum supremacy experiments", purpose="academic", source_hint=SourceHint.web, priority=4),
            ]
        ))

        results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)
        queries = [r.query for r in results]
        assert "quantum computing breakthroughs 2024" in queries
        assert "quantum supremacy experiments" in queries

    @pytest.mark.asyncio
    async def test_also_includes_rule_queries(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=QueryExpansionOutput(
            queries=[
                ExpandedQueryItem(query="unique llm query", purpose="llm", source_hint=SourceHint.web, priority=3),
            ]
        ))

        results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)
        queries = [r.query for r in results]
        # 规则版 queries 也应存在
        assert "quantum computing origin" in queries
        assert "quantum computing history" in queries
        # LLM query 也在
        assert "unique llm query" in queries

    @pytest.mark.asyncio
    async def test_source_hint_preserved(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=QueryExpansionOutput(
            queries=[
                ExpandedQueryItem(query="quantum book title", purpose="book", source_hint=SourceHint.book, priority=5),
            ]
        ))

        results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)
        book_q = next(r for r in results if r.query == "quantum book title")
        assert book_q.source_hint == "book"


# === LLM 失败 fallback ===


class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_fallback_to_rules_on_exception(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=LLMFallbackRequired(
            task="query_expansion", fallback="rule_based_query_expansion", reason="parse failed"
        ))

        results = await service.expand("Elon Musk", mode=TaskMode.PERSON)
        queries = [r.query for r in results]
        # 应该有规则版结果
        assert "Elon Musk biography" in queries
        assert "Elon Musk childhood" in queries
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_fallback_on_runtime_error(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=RuntimeError("connection refused"))

        results = await service.expand("Tesla", mode=TaskMode.COMPANY)
        queries = [r.query for r in results]
        assert "Tesla founding story" in queries

    @pytest.mark.asyncio
    async def test_no_gateway_uses_rules(self, service_no_llm: QueryExpansionService) -> None:
        results = await service_no_llm.expand("AI", mode=TaskMode.CONCEPT)
        queries = [r.query for r in results]
        assert "AI origin" in queries
        assert len(results) > 0


# === 去重 ===


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_duplicate_query_deduplicated(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        # LLM 返回一个和规则版重复的 query
        mock_gateway.run_json = AsyncMock(return_value=QueryExpansionOutput(
            queries=[
                ExpandedQueryItem(query="quantum computing origin", purpose="llm_origin", source_hint=SourceHint.web, priority=8),
                ExpandedQueryItem(query="unique from llm", purpose="unique", source_hint=SourceHint.web, priority=3),
            ]
        ))

        results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)
        queries_lower = [r.query.lower().strip() for r in results]
        # 不应有重复
        assert len(queries_lower) == len(set(queries_lower))

    @pytest.mark.asyncio
    async def test_llm_higher_priority_wins(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        # LLM 返回同名 query 但 priority 更高
        mock_gateway.run_json = AsyncMock(return_value=QueryExpansionOutput(
            queries=[
                ExpandedQueryItem(query="quantum computing origin", purpose="llm_version", source_hint=SourceHint.archive, priority=9),
            ]
        ))

        results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)
        origin_q = next(r for r in results if r.query.lower() == "quantum computing origin")
        # LLM 版本应该胜出（priority=9 > 规则版 priority=1）
        assert origin_q.purpose == "llm_version"
        assert origin_q.source_hint == "archive"
        assert origin_q.priority == 9

    @pytest.mark.asyncio
    async def test_case_insensitive_dedup(self, service: QueryExpansionService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=QueryExpansionOutput(
            queries=[
                ExpandedQueryItem(query="Quantum Computing Origin", purpose="upper", source_hint=SourceHint.web, priority=7),
            ]
        ))

        results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)
        origin_matches = [r for r in results if r.query.lower().strip() == "quantum computing origin"]
        assert len(origin_matches) == 1
