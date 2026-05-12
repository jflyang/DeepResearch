"""Crossref Search Provider - 学术论文/元数据搜索（免费，无需 API key）。"""

import logging
import re

import httpx

from core.config import get_settings
from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, ProviderHealth, SearchResult

logger = logging.getLogger(__name__)

CROSSREF_API_URL = "https://api.crossref.org/works"


def _strip_jats_tags(text: str) -> str:
    """去除 JATS/XML 标签，保留纯文本。"""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


class CrossrefSearchProvider(BaseSearchProvider):
    """Crossref 学术元数据搜索 Provider。免费，可选 mailto 提高速率限制。"""

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.CROSSREF

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        settings = get_settings()

        if not settings.enable_crossref:
            logger.warning("provider_search_skipped provider=crossref reason=disabled")
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
            "query": query,
            "rows": limit,
        }

        headers = {}
        user_agent = "research-collector/0.1"
        if settings.crossref_mailto:
            user_agent += f" (mailto:{settings.crossref_mailto})"
        headers["User-Agent"] = user_agent

        timeout = httpx.Timeout(float(settings.crossref_timeout_seconds), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(CROSSREF_API_URL, params=params, headers=headers)

        if response.status_code == 429:
            logger.warning("crossref_rate_limited")
            return []

        if response.status_code >= 500:
            logger.warning("crossref_server_error status=%d", response.status_code)
            return []

        if response.status_code != 200:
            logger.warning("crossref_http_error status=%d", response.status_code)
            return []

        try:
            data = response.json()
        except ValueError:
            logger.warning("crossref_json_parse_error")
            return []

        return self._parse_results(data, limit)

    def _parse_results(self, data: dict, limit: int) -> list[SearchResult]:
        message = data.get("message", {})
        items = message.get("items", [])
        results: list[SearchResult] = []

        for item in items[:limit]:
            try:
                # Title
                titles = item.get("title", [])
                title = titles[0] if titles else ""
                if not title:
                    continue

                # URL
                url = item.get("URL", "")
                if not url:
                    doi = item.get("DOI", "")
                    url = f"https://doi.org/{doi}" if doi else ""
                if not url:
                    continue

                # Snippet
                container_titles = item.get("container-title", [])
                container = container_titles[0] if container_titles else ""
                abstract = _strip_jats_tags(item.get("abstract", ""))[:300]

                snippet_parts = []
                if container:
                    snippet_parts.append(container)
                if abstract:
                    snippet_parts.append(abstract)

                snippet = " — ".join(snippet_parts) if snippet_parts else ""

                # Authors
                authors = []
                for author in item.get("author", []):
                    given = author.get("given", "")
                    family = author.get("family", "")
                    name = f"{given} {family}".strip()
                    if name:
                        authors.append(name)

                # Published date
                published_at_str = self._extract_date(item)

                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_provider=SearchSource.CROSSREF,
                        source_type=SourceType.PAPER,
                        published_at=None,  # Keep as None, store in raw
                        authors=authors[:10],
                        raw={"published_date": published_at_str, **{k: v for k, v in item.items() if k in ("DOI", "type", "container-title", "ISSN")}},
                    )
                )
            except Exception as e:
                logger.debug("crossref_parse_item_error error=%s", str(e))
                continue

        return results

    @staticmethod
    def _extract_date(item: dict) -> str:
        """从 issued 或 published-print 提取日期字符串。"""
        for field in ("issued", "published-print", "published-online"):
            date_parts = item.get(field, {}).get("date-parts", [[]])
            if date_parts and date_parts[0]:
                parts = date_parts[0]
                # parts = [year] or [year, month] or [year, month, day]
                return "-".join(str(p) for p in parts if p is not None)
        return ""

    async def health_check(self) -> ProviderHealth:
        settings = get_settings()
        if not settings.enable_crossref:
            return ProviderHealth(
                provider="crossref", enabled=False, configured=True
            )
        try:
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(CROSSREF_API_URL, params={"query": "test", "rows": 1})
            reachable = resp.status_code == 200
            return ProviderHealth(
                provider="crossref", enabled=True, configured=True, reachable=reachable,
            )
        except Exception as e:
            return ProviderHealth(
                provider="crossref", enabled=True, configured=True,
                reachable=False, error=str(e),
            )
