"""Google Custom Search JSON API Provider.

使用 Google Custom Search JSON API 获取搜索结果 URL 候选。
需要配置：
- GOOGLE_CUSTOM_SEARCH_API_KEY
- GOOGLE_CUSTOM_SEARCH_CX (Custom Search Engine ID)

文档：https://developers.google.com/custom-search/v1/overview

注意：
- 免费额度每天 100 次查询
- 每次查询最多返回 10 条结果
- 通过 start 参数分页获取 top30/top100
"""

import logging
from datetime import datetime

import httpx

from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, SearchProviderError, SearchResult

logger = logging.getLogger(__name__)

_API_URL = "https://www.googleapis.com/customsearch/v1"


class GoogleCustomSearchProvider(BaseSearchProvider):
    """Google Custom Search JSON API Provider。"""

    def __init__(
        self,
        api_key: str | None = None,
        cx: str | None = None,
        timeout: int = 20,
    ):
        from core.config import get_settings

        settings = get_settings()
        self._api_key = api_key or getattr(settings, "google_custom_search_api_key", "")
        self._cx = cx or getattr(settings, "google_custom_search_cx", "")
        self._timeout = timeout

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.GOOGLE_CUSTOM_SEARCH

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._cx)

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """执行 Google Custom Search。

        Args:
            query: 搜索关键词
            limit: 最大返回条数（每次 API 调用最多 10 条，超过需分页）

        Returns:
            SearchResult 列表
        """
        if not self.configured:
            raise SearchProviderError(
                provider="google_custom_search",
                message="Google Custom Search API not configured. Set GOOGLE_CUSTOM_SEARCH_API_KEY and GOOGLE_CUSTOM_SEARCH_CX.",
            )

        self._log_search_start(query, limit)

        results: list[SearchResult] = []
        pages_needed = min((limit + 9) // 10, 10)  # API 最多 100 条（start 1-91）

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for page in range(pages_needed):
                start = page * 10 + 1
                if start > 91:  # Google API 限制
                    break

                try:
                    response = await client.get(
                        _API_URL,
                        params={
                            "key": self._api_key,
                            "cx": self._cx,
                            "q": query,
                            "start": start,
                            "num": min(10, limit - len(results)),
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    items = data.get("items", [])
                    if not items:
                        break

                    for item in items:
                        result = SearchResult(
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            snippet=item.get("snippet", ""),
                            source_provider=SearchSource.GOOGLE_CUSTOM_SEARCH,
                            source_type=SourceType.WEB,
                            raw=item,
                        )
                        results.append(result)

                        if len(results) >= limit:
                            break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        logger.warning("google_custom_search_rate_limited page=%d", page)
                        break
                    raise SearchProviderError(
                        provider="google_custom_search",
                        message=f"API error: {e.response.status_code}",
                        status_code=e.response.status_code,
                        raw_error=str(e),
                    )
                except Exception as e:
                    raise SearchProviderError(
                        provider="google_custom_search",
                        message=str(e),
                        raw_error=str(e),
                    )

                if len(results) >= limit:
                    break

        self._log_search_done(query, len(results))
        return results

    async def health_check(self) -> bool:
        """检查 API 是否可用。"""
        return self.configured
