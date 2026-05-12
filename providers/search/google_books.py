"""Google Books Search Provider - 调用 Google Books API。"""

import logging
from datetime import UTC, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import get_settings
from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, SearchProviderError, SearchResult

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"


class GoogleBooksSearchProvider(BaseSearchProvider):
    """Google Books API Provider。不强制要求 API key，公开 endpoint 也可访问。"""

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.GOOGLE_BOOKS

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        settings = get_settings()

        # Google Books 公开 endpoint 不强制 key，但有 key 可提高配额
        if not settings.enable_google_books:
            logger.warning(
                "provider_search_skipped provider=google_books reason=disabled"
            )
            return []

        self._log_search_start(query, limit)

        try:
            results = await self._do_search(query, limit, settings.google_books_api_key)
            self._log_search_done(query, len(results))
            return results
        except SearchProviderError:
            raise
        except Exception as e:
            self._log_search_failed(query, str(e))
            raise SearchProviderError(
                provider="google_books",
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
        params: dict[str, str | int] = {
            "q": query,
            "maxResults": min(limit, 40),
            "printType": "books",
        }

        if api_key:
            params["key"] = api_key

        timeout = httpx.Timeout(30.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(GOOGLE_BOOKS_API_URL, params=params)
            except httpx.TimeoutException as e:
                self._log_search_failed(query, "timeout")
                raise SearchProviderError(
                    provider="google_books",
                    message="Request timed out",
                    raw_error=str(e),
                ) from e
            except httpx.HTTPError as e:
                self._log_search_failed(query, f"http_error: {e}")
                raise SearchProviderError(
                    provider="google_books",
                    message=f"HTTP error: {type(e).__name__}",
                    raw_error=str(e),
                ) from e

        if response.status_code != 200:
            self._log_search_failed(query, f"status={response.status_code}")
            raise SearchProviderError(
                provider="google_books",
                message=f"API returned status {response.status_code}",
                status_code=response.status_code,
                raw_error=response.text[:500],
            )

        try:
            data = response.json()
        except ValueError as e:
            self._log_search_failed(query, "json_parse_error")
            raise SearchProviderError(
                provider="google_books",
                message="Failed to parse JSON response",
                raw_error=str(e),
            ) from e

        return self._parse_results(data)

    def _parse_results(self, data: dict) -> list[SearchResult]:
        items = data.get("items", [])
        results: list[SearchResult] = []

        for item in items:
            volume_info = item.get("volumeInfo", {})
            info_link = volume_info.get("infoLink", "")
            if not info_link:
                continue

            title = volume_info.get("title", "")
            authors = volume_info.get("authors", [])
            subtitle = volume_info.get("subtitle", "")
            description = volume_info.get("description", "")

            snippet = self._build_snippet(authors, subtitle, description)
            published_at = self._parse_date(volume_info.get("publishedDate"))

            results.append(
                SearchResult(
                    title=title,
                    url=info_link,
                    snippet=snippet,
                    source_provider=SearchSource.GOOGLE_BOOKS,
                    source_type=SourceType.BOOK,
                    published_at=published_at,
                    raw=volume_info,
                )
            )

        return results

    @staticmethod
    def _build_snippet(authors: list[str], subtitle: str, description: str) -> str:
        parts: list[str] = []
        if authors:
            parts.append(f"by {', '.join(authors)}")
        if subtitle:
            parts.append(subtitle)
        if description:
            # 截取前 200 字符
            parts.append(description[:200])
        return " — ".join(parts) if parts else ""

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        """解析 Google Books 的 publishedDate，格式可能为 YYYY、YYYY-MM、YYYY-MM-DD。"""
        if not date_str:
            return None
        # 尝试从最精确到最粗略
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None
