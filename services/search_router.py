"""SearchRouter - 根据 source_hint 路由到免费/付费 Provider 组合。

职责：
- 根据 ExpandedQuery.source_hint 选择 provider
- 每个 provider 独立 try/except，单个失败不影响其他
- 合并所有结果返回统一 SearchResult 列表
- 不做评分、不做正文提取
"""

import asyncio
import logging
from typing import Any

from core.config import get_settings
from models.schemas import ExpandedQuery
from providers.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)


# === 路由规则 ===

_FREE_ROUTING: dict[str, list[str]] = {
    "web": ["searxng", "wikipedia"],
    "general": ["searxng", "wikipedia"],
    "legal": ["searxng", "wikipedia"],
    "archive": ["searxng", "wikipedia"],
    "book": ["open_library"],
    "academic": ["crossref", "arxiv", "wikipedia"],
    "paper": ["crossref", "arxiv"],
    "concept": ["crossref", "arxiv", "wikipedia"],
}

_DEFAULT_ROUTE = ["searxng", "wikipedia"]


class SearchRouter:
    """根据 source_hint 路由搜索请求到对应 Provider。"""

    def __init__(
        self,
        providers: dict[str, BaseSearchProvider] | None = None,
        max_concurrency: int = 5,
    ):
        self._providers = providers or self._create_default_providers()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @staticmethod
    def _create_default_providers() -> dict[str, BaseSearchProvider]:
        """根据配置创建所有可用的免费 Provider 实例。"""
        settings = get_settings()
        providers: dict[str, BaseSearchProvider] = {}

        if settings.enable_searxng and settings.searxng_base_url:
            from providers.search.searxng import SearXNGSearchProvider
            providers["searxng"] = SearXNGSearchProvider()

        if settings.enable_open_library:
            from providers.search.open_library import OpenLibrarySearchProvider
            providers["open_library"] = OpenLibrarySearchProvider()

        if settings.enable_crossref:
            from providers.search.crossref import CrossrefSearchProvider
            providers["crossref"] = CrossrefSearchProvider()

        if settings.enable_arxiv:
            from providers.search.arxiv import ArxivSearchProvider
            providers["arxiv"] = ArxivSearchProvider()

        if settings.enable_wikipedia:
            from providers.search.wikipedia import WikipediaSearchProvider
            providers["wikipedia"] = WikipediaSearchProvider()

        # 付费 Provider（如果可用）
        if settings.tavily_available:
            from providers.search.tavily import TavilySearchProvider
            providers["tavily"] = TavilySearchProvider()

        if settings.brave_available:
            from providers.search.brave import BraveSearchProvider
            providers["brave"] = BraveSearchProvider()

        if settings.enable_google_books:
            from providers.search.google_books import GoogleBooksSearchProvider
            providers["google_books"] = GoogleBooksSearchProvider()

        logger.info(
            "search_router_initialized providers=%s",
            ",".join(providers.keys()),
        )
        return providers

    def _get_providers_for_hint(self, source_hint: str) -> list[BaseSearchProvider]:
        """根据 source_hint 获取对应的 provider 列表。"""
        route_names = _FREE_ROUTING.get(source_hint, _DEFAULT_ROUTE)
        providers = []
        for name in route_names:
            if name in self._providers:
                providers.append(self._providers[name])
        return providers

    async def search_one(
        self, query: ExpandedQuery, limit: int = 10
    ) -> list[SearchResult]:
        """对单条 ExpandedQuery 执行搜索。"""
        hint = query.source_hint if isinstance(query.source_hint, str) else query.source_hint.value
        providers = self._get_providers_for_hint(hint)

        if not providers:
            logger.warning(
                "search_router_no_providers hint=%s query=%s",
                hint, query.query,
            )
            return []

        tasks = [
            self._search_provider(provider, query.query, limit)
            for provider in providers
        ]

        results_nested = await asyncio.gather(*tasks)

        all_results: list[SearchResult] = []
        for result_or_none in results_nested:
            if result_or_none:
                all_results.extend(result_or_none)

        logger.info(
            "search_router_completed hint=%s query=%s providers_used=%d total_results=%d",
            hint, query.query[:50], len(providers), len(all_results),
        )
        return all_results

    async def search_many(
        self, queries: list[ExpandedQuery], limit_per_query: int = 10
    ) -> list[SearchResult]:
        """对多条 ExpandedQuery 执行搜索并合并结果。"""
        tasks = [self.search_one(q, limit_per_query) for q in queries]
        results_nested = await asyncio.gather(*tasks)

        all_results: list[SearchResult] = []
        for results in results_nested:
            all_results.extend(results)

        logger.info(
            "search_router_batch_completed queries=%d total_results=%d",
            len(queries), len(all_results),
        )
        return all_results

    async def _search_provider(
        self, provider: BaseSearchProvider, query: str, limit: int
    ) -> list[SearchResult]:
        """带并发限制和错误隔离的单 provider 搜索。"""
        async with self._semaphore:
            try:
                results = await provider.search(query, limit)
                logger.debug(
                    "search_provider_done provider=%s query=%s count=%d",
                    provider.provider_name, query[:50], len(results),
                )
                return results
            except Exception as e:
                logger.warning(
                    "search_provider_failed provider=%s query=%s error=%s",
                    provider.provider_name, query[:50], str(e),
                )
                return []

    def list_available_providers(self) -> list[str]:
        """列出当前可用的 provider 名称。"""
        return list(self._providers.keys())
