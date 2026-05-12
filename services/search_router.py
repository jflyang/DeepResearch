"""SearchRouter - 根据 source_hint 路由到免费/付费 Provider 组合。

职责：
- 根据 ExpandedQuery.source_hint 选择 provider
- 每个 provider 独立 try/except，单个失败不影响其他
- 合并所有结果返回统一 SearchResult 列表
- 不做评分、不做正文提取
- 读取 runtime_settings.search_policy 决定 provider 启用和优先级
"""

import asyncio
import logging
from typing import Any

from core.config import get_settings, _load_runtime_settings
from models.schemas import ExpandedQuery
from providers.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)


# === 路由规则（默认，被 runtime_settings.search_policy.provider_priority 覆盖） ===

_DEFAULT_FREE_ROUTING: dict[str, list[str]] = {
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


def _load_search_policy() -> dict[str, Any]:
    """从 runtime_settings.json 加载 search_policy 配置。"""
    runtime = _load_runtime_settings()
    return runtime.get("search_policy", {})


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
        """根据配置创建所有可用的 Provider 实例（受 search_policy 控制）。"""
        settings = get_settings()
        policy = _load_search_policy()
        policy_providers = policy.get("providers", {})
        paid_enabled = policy.get("paid_providers_enabled", False)

        providers: dict[str, BaseSearchProvider] = {}

        # Free providers - check policy enabled status
        def _is_enabled(name: str, default: bool = True) -> bool:
            p_cfg = policy_providers.get(name, {})
            if "enabled" in p_cfg:
                return p_cfg["enabled"]
            return default

        if _is_enabled("searxng", settings.enable_searxng) and settings.searxng_base_url:
            from providers.search.searxng import SearXNGSearchProvider
            providers["searxng"] = SearXNGSearchProvider()

        if _is_enabled("open_library", settings.enable_open_library):
            from providers.search.open_library import OpenLibrarySearchProvider
            providers["open_library"] = OpenLibrarySearchProvider()

        if _is_enabled("crossref", settings.enable_crossref):
            from providers.search.crossref import CrossrefSearchProvider
            providers["crossref"] = CrossrefSearchProvider()

        if _is_enabled("arxiv", settings.enable_arxiv):
            from providers.search.arxiv import ArxivSearchProvider
            providers["arxiv"] = ArxivSearchProvider()

        if _is_enabled("wikipedia", settings.enable_wikipedia):
            from providers.search.wikipedia import WikipediaSearchProvider
            providers["wikipedia"] = WikipediaSearchProvider()

        # Paid providers - only if paid_providers_enabled or policy explicitly enables
        tavily_cfg = policy_providers.get("tavily", {})
        tavily_enabled = tavily_cfg.get("enabled", True)
        tavily_mode = tavily_cfg.get("mode", "fallback")

        if tavily_enabled and settings.tavily_available:
            if paid_enabled or tavily_mode == "always":
                from providers.search.tavily import TavilySearchProvider
                providers["tavily"] = TavilySearchProvider()
            elif tavily_mode == "fallback":
                # Include but mark for fallback usage
                from providers.search.tavily import TavilySearchProvider
                providers["tavily"] = TavilySearchProvider()
            else:
                logger.info("tavily_skipped reason=paid_search_disabled mode=%s", tavily_mode)
        elif tavily_enabled and not settings.tavily_available:
            logger.debug("tavily_skipped reason=api_key_missing")
        elif not tavily_enabled:
            logger.debug("tavily_skipped reason=disabled_by_policy")

        if _is_enabled("brave", settings.enable_brave) and settings.brave_available and paid_enabled:
            from providers.search.brave import BraveSearchProvider
            providers["brave"] = BraveSearchProvider()
        elif _is_enabled("brave") and not paid_enabled:
            logger.debug("brave_skipped reason=paid_search_disabled")

        if _is_enabled("google_books", settings.enable_google_books):
            from providers.search.google_books import GoogleBooksSearchProvider
            providers["google_books"] = GoogleBooksSearchProvider()

        logger.info(
            "search_router_initialized providers=%s",
            ",".join(providers.keys()),
        )
        return providers

    def _get_providers_for_hint(self, source_hint: str) -> list[BaseSearchProvider]:
        """根据 source_hint 获取对应的 provider 列表（使用 policy priority）。"""
        policy = _load_search_policy()
        policy_priority = policy.get("provider_priority", {})

        # Use policy priority if available, otherwise default
        route_names = policy_priority.get(source_hint)
        if not route_names:
            route_names = _DEFAULT_FREE_ROUTING.get(source_hint, _DEFAULT_ROUTE)

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
