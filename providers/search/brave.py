"""Brave Web Search Provider - 调用 Brave Search API。"""

import logging
from datetime import UTC, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import get_settings
from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, SearchProviderError, SearchResult

logger = logging.getLogger(__name__)

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider(BaseSearchProvider):
    """Brave Web Search API Provider。"""

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.BRAVE

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        settings = get_settings()

        if not settings.brave_available:
            logger.warning("provider_search_skipped provider=brave reason=no_api_key_or_disabled")
            return []

        self._log_search_start(query, limit)

        try:
            results = await self._do_search(query, limit, settings.brave_api_key)
            self._log_search_done(query, len(results))
            return results
        except SearchProviderError:
            raise
        except Exception as e:
            self._log_search_failed(query, str(e))
            raise SearchProviderError(
                provider="brave",
                message=f"Unexpected error: {type(e).__name__}",
                raw_error=str(e),
            ) from e

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPError)),
        reraise=True,
    )
    async def _do_search(self, query: str, limit: int, api_key: str) -> list[SearchResult]:
        settings = get_settings()

        params = {
            "q": query,
            "count": min(limit, 20),
        }

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }

        timeout = httpx.Timeout(float(settings.default_result_limit), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(BRAVE_API_URL, params=params, headers=headers)
            except httpx.TimeoutException as e:
                self._log_search_failed(query, "timeout")
                raise SearchProviderError(
                    provider="brave",
                    message="Request timed out",
                    raw_error=str(e),
                ) from e
            except httpx.HTTPError as e:
                self._log_search_failed(query, f"http_error: {e}")
                raise SearchProviderError(
                    provider="brave",
                    message=f"HTTP error: {type(e).__name__}",
                    raw_error=str(e),
                ) from e

        if response.status_code != 200:
            self._log_search_failed(query, f"status={response.status_code}")
            raise SearchProviderError(
                provider="brave",
                message=f"API returned status {response.status_code}",
                status_code=response.status_code,
                raw_error=response.text[:500],
            )

        try:
            data = response.json()
        except ValueError as e:
            self._log_search_failed(query, "json_parse_error")
            raise SearchProviderError(
                provider="brave",
                message="Failed to parse JSON response",
                raw_error=str(e),
            ) from e

        return self._parse_results(data)

    def _parse_results(self, data: dict) -> list[SearchResult]:
        web_results = data.get("web", {}).get("results", [])
        results: list[SearchResult] = []

        for item in web_results:
            url = item.get("url", "")
            if not url:
                continue

            published_at = self._parse_date(item.get("page_age"))

            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("description", ""),
                    source_provider=SearchSource.BRAVE,
                    source_type=self._infer_source_type(url),
                    published_at=published_at,
                    raw=item,
                )
            )

        return results

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        """解析 Brave 返回的 page_age 字段。格式可能为 ISO 或自然语言。"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
        # Brave 有时返回 "2024-03-15T00:00:00" 无时区
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _infer_source_type(url: str) -> SourceType:
        url_lower = url.lower()
        if any(d in url_lower for d in ("arxiv.org", "scholar.google", "ieee.org", "acm.org")):
            return SourceType.ACADEMIC
        if any(d in url_lower for d in ("reuters.com", "bbc.com", "nytimes.com", "cnn.com")):
            return SourceType.NEWS
        if any(d in url_lower for d in ("docs.", "readthedocs", "developer.")):
            return SourceType.DOCUMENTATION
        if any(d in url_lower for d in ("stackoverflow.com", "reddit.com")):
            return SourceType.FORUM
        if any(d in url_lower for d in ("medium.com", "dev.to", "substack.com")):
            return SourceType.BLOG
        if ".gov" in url_lower or ".gov." in url_lower:
            return SourceType.GOVERNMENT
        return SourceType.OTHER
