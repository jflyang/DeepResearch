"""测试 SearchRouter 免费 MVP - 路由逻辑、错误隔离、结果合并。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.enums import SearchSource, SourceType
from models.schemas import ExpandedQuery, SourceHint
from providers.search.base import BaseSearchProvider, SearchResult
from services.search_router import SearchRouter


# === Helper: Mock Provider ===


class MockProvider(BaseSearchProvider):
    """可配置的 Mock Provider。"""

    def __init__(self, name: SearchSource, results: list[SearchResult] | None = None, error: Exception | None = None):
        self._name = name
        self._results = results or []
        self._error = error

    @property
    def provider_name(self) -> SearchSource:
        return self._name

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if self._error:
            raise self._error
        return self._results[:limit]


def _make_result(title: str, provider: SearchSource) -> SearchResult:
    return SearchResult(
        title=title,
        url=f"https://example.com/{title.replace(' ', '_')}",
        snippet=f"Snippet for {title}",
        source_provider=provider,
        source_type=SourceType.WEB,
    )


# ============================================================
# Tests
# ============================================================


class TestSearchRouterRouting:
    """测试路由逻辑。"""

    async def test_web_hint_uses_searxng_and_wikipedia(self):
        """source_hint=web 应调用 SearXNG + Wikipedia。"""
        searxng_results = [_make_result("SearXNG Result", SearchSource.SEARXNG)]
        wiki_results = [_make_result("Wiki Result", SearchSource.WIKIPEDIA)]

        providers = {
            "searxng": MockProvider(SearchSource.SEARXNG, searxng_results),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, wiki_results),
            "open_library": MockProvider(SearchSource.OPEN_LIBRARY, []),
        }

        router = SearchRouter(providers=providers)
        query = ExpandedQuery(query="test", source_hint=SourceHint.WEB)
        results = await router.search_one(query)

        assert len(results) == 2
        providers_used = {r.source_provider for r in results}
        assert SearchSource.SEARXNG in providers_used
        assert SearchSource.WIKIPEDIA in providers_used

    async def test_book_hint_uses_open_library(self):
        """source_hint=book 应调用 Open Library。"""
        book_results = [_make_result("Book Result", SearchSource.OPEN_LIBRARY)]

        providers = {
            "searxng": MockProvider(SearchSource.SEARXNG, [_make_result("X", SearchSource.SEARXNG)]),
            "open_library": MockProvider(SearchSource.OPEN_LIBRARY, book_results),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, []),
        }

        router = SearchRouter(providers=providers)
        query = ExpandedQuery(query="deep learning book", source_hint=SourceHint.BOOK)
        results = await router.search_one(query)

        assert len(results) == 1
        assert results[0].source_provider == SearchSource.OPEN_LIBRARY

    async def test_academic_hint_uses_crossref_arxiv_wikipedia(self):
        """source_hint=academic 应调用 Crossref + arXiv + Wikipedia。"""
        crossref_results = [_make_result("Crossref Paper", SearchSource.CROSSREF)]
        arxiv_results = [_make_result("arXiv Paper", SearchSource.ARXIV)]
        wiki_results = [_make_result("Wiki Ref", SearchSource.WIKIPEDIA)]

        providers = {
            "crossref": MockProvider(SearchSource.CROSSREF, crossref_results),
            "arxiv": MockProvider(SearchSource.ARXIV, arxiv_results),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, wiki_results),
            "searxng": MockProvider(SearchSource.SEARXNG, []),
        }

        router = SearchRouter(providers=providers)
        query = ExpandedQuery(query="transformer architecture", source_hint=SourceHint.ACADEMIC)
        results = await router.search_one(query)

        assert len(results) == 3
        providers_used = {r.source_provider for r in results}
        assert SearchSource.CROSSREF in providers_used
        assert SearchSource.ARXIV in providers_used
        assert SearchSource.WIKIPEDIA in providers_used


class TestSearchRouterErrorIsolation:
    """测试错误隔离。"""

    async def test_single_provider_error_does_not_affect_others(self):
        """单个 provider 抛错不影响其他 provider。"""
        wiki_results = [_make_result("Wiki Result", SearchSource.WIKIPEDIA)]

        providers = {
            "searxng": MockProvider(SearchSource.SEARXNG, error=RuntimeError("SearXNG down")),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, wiki_results),
        }

        router = SearchRouter(providers=providers)
        query = ExpandedQuery(query="test", source_hint=SourceHint.WEB)
        results = await router.search_one(query)

        # Wikipedia should still return results
        assert len(results) == 1
        assert results[0].source_provider == SearchSource.WIKIPEDIA

    async def test_all_providers_fail_returns_empty(self):
        """所有 provider 都失败时返回空列表。"""
        providers = {
            "searxng": MockProvider(SearchSource.SEARXNG, error=RuntimeError("down")),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, error=RuntimeError("down")),
        }

        router = SearchRouter(providers=providers)
        query = ExpandedQuery(query="test", source_hint=SourceHint.WEB)
        results = await router.search_one(query)

        assert results == []


class TestSearchRouterMerge:
    """测试结果合并。"""

    async def test_merged_result_count(self):
        """合并结果数量正确。"""
        searxng_results = [_make_result(f"S{i}", SearchSource.SEARXNG) for i in range(3)]
        wiki_results = [_make_result(f"W{i}", SearchSource.WIKIPEDIA) for i in range(2)]

        providers = {
            "searxng": MockProvider(SearchSource.SEARXNG, searxng_results),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, wiki_results),
        }

        router = SearchRouter(providers=providers)
        query = ExpandedQuery(query="test", source_hint=SourceHint.WEB)
        results = await router.search_one(query)

        assert len(results) == 5

    async def test_search_many_merges_all_queries(self):
        """search_many 合并所有 query 的结果。"""
        searxng_results = [_make_result("S1", SearchSource.SEARXNG)]
        wiki_results = [_make_result("W1", SearchSource.WIKIPEDIA)]

        providers = {
            "searxng": MockProvider(SearchSource.SEARXNG, searxng_results),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, wiki_results),
        }

        router = SearchRouter(providers=providers)
        queries = [
            ExpandedQuery(query="query1", source_hint=SourceHint.WEB),
            ExpandedQuery(query="query2", source_hint=SourceHint.WEB),
        ]
        results = await router.search_many(queries)

        # Each query returns 2 results (searxng + wiki), total = 4
        assert len(results) == 4


class TestSearchRouterDisabledProviders:
    """测试未启用 provider 不调用。"""

    async def test_disabled_provider_not_called(self):
        """未在 providers dict 中的 provider 不会被调用。"""
        # Only wikipedia available, no searxng
        wiki_results = [_make_result("Wiki", SearchSource.WIKIPEDIA)]

        providers = {
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, wiki_results),
        }

        router = SearchRouter(providers=providers)
        query = ExpandedQuery(query="test", source_hint=SourceHint.WEB)
        results = await router.search_one(query)

        # Only wikipedia results (searxng not in providers)
        assert len(results) == 1
        assert results[0].source_provider == SearchSource.WIKIPEDIA

    async def test_unknown_hint_uses_default_route(self):
        """未知 source_hint 使用默认路由（searxng + wikipedia）。"""
        searxng_results = [_make_result("S1", SearchSource.SEARXNG)]
        wiki_results = [_make_result("W1", SearchSource.WIKIPEDIA)]

        providers = {
            "searxng": MockProvider(SearchSource.SEARXNG, searxng_results),
            "wikipedia": MockProvider(SearchSource.WIKIPEDIA, wiki_results),
        }

        router = SearchRouter(providers=providers)
        # Use FORUM which is not in routing table → falls back to default
        query = ExpandedQuery(query="test", source_hint=SourceHint.FORUM)
        results = await router.search_one(query)

        assert len(results) == 2
