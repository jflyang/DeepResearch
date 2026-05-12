"""SerpAPI Provider - 通过 SerpAPI 获取 Google 搜索结果。

使用 SerpAPI (https://serpapi.com/) 获取搜索结果 URL 候选。
需要配置：SERPAPI_API_KEY

优势：
- 合规获取 Google 搜索结果
- 支持多种搜索引擎
- 结构化返回数据
"""

import logging

import httpx

from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, SearchProviderError, SearchResult

logger = logging.getLogger(__name__)

_API_URL = "https://serpapi.com/search"


class SerpAPISearchProvider(BaseSearchProvider):
    """SerpAPI 搜索 Provider。"""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 20,
    ):
        from core.config import get_settings

        settings = get_settings()
        self._api_key = api_key or getattr(settings, "serpapi_api_key", "")
        self._timeout = timeout

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.SERPAPI

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """执行 SerpAPI 搜索。

        Args:
            query: 搜索关键词
            limit: 最大返回条数

        Returns:
            SearchResult 列表
        """
        if not self.configured:
            raise SearchProviderError(
                provider="serpapi",
                message="SerpAPI not configured. Set SERPAPI_API_KEY.",
            )

        self._log_search_start(query, limit)

        results: list[SearchResult] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.get(
                    _API_URL,
                    params={
                        "api_key": self._api_key,
                        "engine": "google",
                        "q": query,
                        "num": min(limit, 100),
                    },
                )
                response.raise_for_status()
                data = response.json()

                organic_results = data.get("organic_results", [])

                for item in organic_results[:limit]:
                    result = SearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                        source_provider=SearchSource.SERPAPI,
                        source_type=SourceType.WEB,
                        raw=item,
                    )
                    results.append(result)

            except httpx.HTTPStatusError as e:
                raise SearchProviderError(
                    provider="serpapi",
                    message=f"API error: {e.response.status_code}",
                    status_code=e.response.status_code,
                    raw_error=str(e),
                )
            except Exception as e:
                raise SearchProviderError(
                    provider="serpapi",
                    message=str(e),
                    raw_error=str(e),
                )

        self._log_search_done(query, len(results))
        return results

    async def health_check(self) -> bool:
        """检查 API 是否可用。"""
        return self.configured
