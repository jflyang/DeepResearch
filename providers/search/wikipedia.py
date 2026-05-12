"""Wikipedia Search Provider - 实体消歧与背景参考（免费，无需 API key）。

注意：Wikipedia 只用于参考和实体消歧，不作为高可信一手来源。
source_type 固定为 REFERENCE。
"""

import logging
import re

import httpx

from core.config import get_settings
from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, ProviderHealth, SearchResult

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """去除 HTML 标签。"""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


class WikipediaSearchProvider(BaseSearchProvider):
    """Wikipedia 搜索 Provider。用于实体消歧和背景参考。"""

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.WIKIPEDIA

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        settings = get_settings()

        if not settings.enable_wikipedia:
            logger.warning("provider_search_skipped provider=wikipedia reason=disabled")
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
        lang = settings.wikipedia_language or "en"
        base_url = f"https://{lang}.wikipedia.org/w/api.php"

        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": limit,
        }

        timeout = httpx.Timeout(float(settings.wikipedia_timeout_seconds), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(base_url, params=params)

        if response.status_code != 200:
            logger.warning("wikipedia_http_error status=%d", response.status_code)
            return []

        try:
            data = response.json()
        except ValueError:
            logger.warning("wikipedia_json_parse_error")
            return []

        return self._parse_results(data, lang, limit)

    def _parse_results(self, data: dict, lang: str, limit: int) -> list[SearchResult]:
        search_results = data.get("query", {}).get("search", [])
        results: list[SearchResult] = []

        for item in search_results[:limit]:
            try:
                title = item.get("title", "")
                if not title:
                    continue

                # Build URL with underscores
                title_encoded = title.replace(" ", "_")
                url = f"https://{lang}.wikipedia.org/wiki/{title_encoded}"

                # Strip HTML from snippet
                snippet = _strip_html(item.get("snippet", ""))

                # Timestamp
                timestamp = item.get("timestamp", "")

                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_provider=SearchSource.WIKIPEDIA,
                        source_type=SourceType.REFERENCE,
                        published_at=None,
                        language=lang,
                        raw=item,
                    )
                )
            except Exception as e:
                logger.debug("wikipedia_parse_item_error error=%s", str(e))
                continue

        return results

    async def health_check(self) -> ProviderHealth:
        settings = get_settings()
        if not settings.enable_wikipedia:
            return ProviderHealth(
                provider="wikipedia", enabled=False, configured=True
            )
        try:
            lang = settings.wikipedia_language or "en"
            base_url = f"https://{lang}.wikipedia.org/w/api.php"
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(base_url, params={"action": "query", "list": "search", "srsearch": "test", "format": "json", "srlimit": 1})
            reachable = resp.status_code == 200
            return ProviderHealth(
                provider="wikipedia", enabled=True, configured=True, reachable=reachable,
            )
        except Exception as e:
            return ProviderHealth(
                provider="wikipedia", enabled=True, configured=True,
                reachable=False, error=str(e),
            )
