"""arXiv Search Provider - 论文搜索（免费，无需 API key）。

使用 arXiv API (Atom XML)，仅依赖标准库 xml.etree.ElementTree。
"""

import logging
import xml.etree.ElementTree as ET

import httpx

from core.config import get_settings
from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, ProviderHealth, SearchResult

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"

# Atom namespace
_ATOM_NS = "http://www.w3.org/2005/Atom"


class ArxivSearchProvider(BaseSearchProvider):
    """arXiv 论文搜索 Provider。完全免费，无需 API key。"""

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.ARXIV

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        settings = get_settings()

        if not settings.enable_arxiv:
            logger.warning("provider_search_skipped provider=arxiv reason=disabled")
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
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
        }

        timeout = httpx.Timeout(float(settings.arxiv_timeout_seconds), connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(ARXIV_API_URL, params=params)

        if response.status_code != 200:
            logger.warning("arxiv_http_error status=%d", response.status_code)
            return []

        try:
            return self._parse_atom(response.text, limit)
        except ET.ParseError as e:
            logger.warning("arxiv_xml_parse_error error=%s", str(e))
            return []

    def _parse_atom(self, xml_text: str, limit: int) -> list[SearchResult]:
        root = ET.fromstring(xml_text)
        entries = root.findall(f"{{{_ATOM_NS}}}entry")
        results: list[SearchResult] = []

        for entry in entries[:limit]:
            try:
                title_el = entry.find(f"{{{_ATOM_NS}}}title")
                title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""
                if not title:
                    continue

                # URL (entry id)
                id_el = entry.find(f"{{{_ATOM_NS}}}id")
                url = id_el.text.strip() if id_el is not None and id_el.text else ""
                if not url:
                    continue

                # Summary
                summary_el = entry.find(f"{{{_ATOM_NS}}}summary")
                snippet = ""
                if summary_el is not None and summary_el.text:
                    snippet = summary_el.text.strip().replace("\n", " ")[:500]

                # Authors
                authors = []
                for author_el in entry.findall(f"{{{_ATOM_NS}}}author"):
                    name_el = author_el.find(f"{{{_ATOM_NS}}}name")
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                # Published date
                published_el = entry.find(f"{{{_ATOM_NS}}}published")
                published_str = published_el.text.strip() if published_el is not None and published_el.text else ""

                # Categories
                categories = []
                for cat_el in entry.findall("{http://arxiv.org/schemas/atom}primary_category"):
                    term = cat_el.get("term", "")
                    if term:
                        categories.append(term)

                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source_provider=SearchSource.ARXIV,
                        source_type=SourceType.PAPER,
                        published_at=None,
                        authors=authors[:10],
                        raw={
                            "arxiv_id": url.split("/abs/")[-1] if "/abs/" in url else url,
                            "published": published_str,
                            "categories": categories,
                        },
                    )
                )
            except Exception as e:
                logger.debug("arxiv_parse_entry_error error=%s", str(e))
                continue

        return results

    async def health_check(self) -> ProviderHealth:
        settings = get_settings()
        if not settings.enable_arxiv:
            return ProviderHealth(
                provider="arxiv", enabled=False, configured=True
            )
        try:
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(ARXIV_API_URL, params={"search_query": "all:test", "max_results": 1})
            reachable = resp.status_code == 200
            return ProviderHealth(
                provider="arxiv", enabled=True, configured=True, reachable=reachable,
            )
        except Exception as e:
            return ProviderHealth(
                provider="arxiv", enabled=True, configured=True,
                reachable=False, error=str(e),
            )
