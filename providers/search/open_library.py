"""Open Library Search Provider - 图书资料搜索（免费，无需 API key）。"""

import logging

import httpx

from core.config import get_settings
from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, ProviderHealth, SearchResult

logger = logging.getLogger(__name__)

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"


class OpenLibrarySearchProvider(BaseSearchProvider):
    """Open Library 图书搜索 Provider。完全免费，无需 API key。"""

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.OPEN_LIBRARY

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        settings = get_settings()

        if not settings.enable_open_library:
            logger.warning("provider_search_skipped provider=open_library reason=disabled")
            return []

        self._log_search_start(query, limit)

        try:
            results = await self._do_search(query, limit)
            self._log_search_done(query, len(results))
            return results
        except Exception as e:
            self._log_search_failed(query, str(e))
            return []

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        params = {
            "q": query,
            "limit": limit,
        }

        timeout = httpx.Timeout(30.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(OPEN_LIBRARY_SEARCH_URL, params=params)

        if response.status_code != 200:
            logger.warning(
                "open_library_http_error status=%d", response.status_code
            )
            return []

        try:
            data = response.json()
        except ValueError:
            logger.warning("open_library_json_parse_error")
            return []

        return self._parse_results(data, limit)

    def _parse_results(self, data: dict, limit: int) -> list[SearchResult]:
        docs = data.get("docs", [])
        results: list[SearchResult] = []

        for doc in docs[:limit]:
            try:
                title = doc.get("title", "")
                if not title:
                    continue

                # Build URL
                key = doc.get("key", "")
                url = f"https://openlibrary.org{key}" if key else ""

                # Build snippet
                authors = doc.get("author_name", [])
                first_year = doc.get("first_publish_year")
                publishers = doc.get("publisher", [])
                subjects = doc.get("subject", [])

                snippet_parts = []
                if authors:
                    snippet_parts.append(f"by {', '.join(authors[:3])}")
                if first_year:
                    snippet_parts.append(f"({first_year})")
                if publishers:
                    snippet_parts.append(f"Publisher: {publishers[0]}")
                if subjects:
                    snippet_parts.append(f"Subjects: {', '.join(subjects[:3])}")

                snippet = " — ".join(snippet_parts) if snippet_parts else ""

                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_provider=SearchSource.OPEN_LIBRARY,
                        source_type=SourceType.BOOK,
                        published_at=None,
                        authors=authors[:10] if authors else [],
                        raw=doc,
                    )
                )
            except Exception as e:
                logger.debug("open_library_parse_doc_error error=%s", str(e))
                continue

        return results

    async def health_check(self) -> ProviderHealth:
        settings = get_settings()
        if not settings.enable_open_library:
            return ProviderHealth(
                provider="open_library", enabled=False, configured=True
            )
        try:
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(OPEN_LIBRARY_SEARCH_URL, params={"q": "test", "limit": 1})
            reachable = resp.status_code == 200
            return ProviderHealth(
                provider="open_library", enabled=True, configured=True, reachable=reachable,
            )
        except Exception as e:
            return ProviderHealth(
                provider="open_library", enabled=True, configured=True,
                reachable=False, error=str(e),
            )
