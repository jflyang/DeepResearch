"""SearXNG Search Provider - 通用网页搜索（自托管元搜索引擎）。"""

import logging

import httpx

from core.config import get_settings
from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, ProviderHealth, SearchResult

logger = logging.getLogger(__name__)


class SearXNGSearchProvider(BaseSearchProvider):
    """SearXNG 元搜索引擎 Provider。需要自托管 SearXNG 实例。"""

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.SEARXNG

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        settings = get_settings()

        if not settings.enable_searxng:
            logger.warning("provider_search_skipped provider=searxng reason=disabled")
            return []

        if not settings.searxng_base_url:
            logger.warning("provider_search_skipped provider=searxng reason=no_base_url")
            return []

        self._log_search_start(query, limit)

        try:
            results = await self._do_search(query, limit, settings)
            self._log_search_done(query, len(results))
            return results
        except Exception as e:
            self._log_search_failed(query, str(e))
            return []

    async def _do_search(self, query: str, limit: int, settings) -> list[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "language": "auto",
            "categories": "general",
        }

        timeout = httpx.Timeout(float(settings.searxng_timeout_seconds), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{settings.searxng_base_url.rstrip('/')}/search",
                params=params,
            )

        if response.status_code != 200:
            logger.warning(
                "searxng_http_error status=%d body=%s",
                response.status_code,
                response.text[:200],
            )
            return []

        try:
            data = response.json()
        except ValueError:
            logger.warning("searxng_json_parse_error")
            return []

        return self._parse_results(data, limit)

    def _parse_results(self, data: dict, limit: int) -> list[SearchResult]:
        raw_results = data.get("results", [])
        results: list[SearchResult] = []

        for item in raw_results[:limit]:
            title = item.get("title", "")
            url = item.get("url", "")
            if not url:
                continue

            snippet = item.get("content") or item.get("snippet") or ""
            published_at_str = item.get("publishedDate")

            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source_provider=SearchSource.SEARXNG,
                    source_type=SourceType.WEB,
                    published_at=None,  # SearXNG date format varies, skip parsing
                    raw=item,
                )
            )

        return results

    async def health_check(self) -> ProviderHealth:
        settings = get_settings()
        if not settings.enable_searxng:
            return ProviderHealth(
                provider="searxng", enabled=False, configured=False
            )
        if not settings.searxng_base_url:
            return ProviderHealth(
                provider="searxng", enabled=True, configured=False,
                error="SEARXNG_BASE_URL not set",
            )
        try:
            timeout = httpx.Timeout(5.0, connect=3.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{settings.searxng_base_url.rstrip('/')}/search", params={"q": "test", "format": "json"})
            reachable = resp.status_code == 200
            return ProviderHealth(
                provider="searxng", enabled=True, configured=True, reachable=reachable,
            )
        except Exception as e:
            return ProviderHealth(
                provider="searxng", enabled=True, configured=True,
                reachable=False, error=str(e),
            )
