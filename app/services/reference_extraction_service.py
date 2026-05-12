"""引用提取服务 - 将 ParsedReport 转换为统一 ReferenceCandidate 列表。

不调用 LLM，不访问网络，不写数据库。
"""

from __future__ import annotations

import logging

from models.enums import ReferenceStatus, ReferenceType
from models.schemas import (
    ExtractedBookReference,
    ExtractedPaperReference,
    ExtractedUrlReference,
    ParsedReport,
    ReferenceCandidate,
)

logger = logging.getLogger(__name__)


class ReferenceExtractionService:
    """将 ParsedReport 中的 urls/books/papers 统一转换为 ReferenceCandidate 列表。"""

    def extract(self, parsed_report: ParsedReport) -> list[ReferenceCandidate]:
        """转换 ParsedReport → list[ReferenceCandidate]，去重后返回。"""
        candidates: list[ReferenceCandidate] = []

        candidates.extend(self._convert_urls(parsed_report.urls))
        candidates.extend(self._convert_books(parsed_report.books))
        candidates.extend(self._convert_papers(parsed_report.papers))

        return candidates

    # ------------------------------------------------------------------
    # URL 转换
    # ------------------------------------------------------------------

    def _convert_urls(
        self, urls: list[ExtractedUrlReference]
    ) -> list[ReferenceCandidate]:
        seen: set[str] = set()
        results: list[ReferenceCandidate] = []

        for ref in urls:
            try:
                normalized = ref.url.strip().lower().rstrip("/")
                if normalized in seen:
                    continue
                seen.add(normalized)

                results.append(ReferenceCandidate(
                    type=ReferenceType.URL,
                    value=ref.url,
                    title_hint=ref.title_hint,
                    source_url=ref.url,
                    status=ReferenceStatus.PARSED,
                    confidence=1.0,
                    metadata=self._build_url_metadata(ref),
                ))
            except Exception:
                logger.warning("Failed to convert URL reference: %s", ref.url, exc_info=True)
                continue

        return results

    # ------------------------------------------------------------------
    # Book 转换
    # ------------------------------------------------------------------

    def _convert_books(
        self, books: list[ExtractedBookReference]
    ) -> list[ReferenceCandidate]:
        seen: set[str] = set()
        results: list[ReferenceCandidate] = []

        for ref in books:
            try:
                key = ref.title.strip().lower()
                if key in seen:
                    continue
                seen.add(key)

                results.append(ReferenceCandidate(
                    type=ReferenceType.BOOK,
                    value=ref.title,
                    title_hint=ref.title,
                    source_url=None,
                    status=ReferenceStatus.PARSED,
                    confidence=ref.confidence,
                    metadata=self._build_book_metadata(ref),
                ))
            except Exception:
                logger.warning("Failed to convert book reference: %s", ref.title, exc_info=True)
                continue

        return results

    # ------------------------------------------------------------------
    # Paper 转换
    # ------------------------------------------------------------------

    def _convert_papers(
        self, papers: list[ExtractedPaperReference]
    ) -> list[ReferenceCandidate]:
        seen: set[str] = set()
        results: list[ReferenceCandidate] = []

        for ref in papers:
            try:
                # 去重 key：优先 DOI，其次 arXiv，其次 title
                dedup_key = self._paper_dedup_key(ref)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                # value：优先 DOI，其次 arXiv ID，其次 title
                value = ref.doi_hint or ref.arxiv_id or ref.title

                results.append(ReferenceCandidate(
                    type=ReferenceType.PAPER,
                    value=value,
                    title_hint=ref.title,
                    source_url=None,
                    status=ReferenceStatus.PARSED,
                    confidence=ref.confidence,
                    metadata=self._build_paper_metadata(ref),
                ))
            except Exception:
                logger.warning("Failed to convert paper reference: %s", ref.title, exc_info=True)
                continue

        return results

    # ------------------------------------------------------------------
    # Metadata 构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_url_metadata(ref: ExtractedUrlReference) -> dict:
        meta: dict = {}
        if ref.surrounding_text:
            meta["surrounding_text"] = ref.surrounding_text
        if ref.citation_marker:
            meta["citation_marker"] = ref.citation_marker
        return meta

    @staticmethod
    def _build_book_metadata(ref: ExtractedBookReference) -> dict:
        meta: dict = {}
        if ref.author_hint:
            meta["author_hint"] = ref.author_hint
        if ref.year_hint:
            meta["year_hint"] = ref.year_hint
        if ref.surrounding_text:
            meta["surrounding_text"] = ref.surrounding_text
        return meta

    @staticmethod
    def _build_paper_metadata(ref: ExtractedPaperReference) -> dict:
        meta: dict = {}
        if ref.doi_hint:
            meta["doi_hint"] = ref.doi_hint
        if ref.arxiv_id:
            meta["arxiv_id"] = ref.arxiv_id
        if ref.author_hint:
            meta["author_hint"] = ref.author_hint
        if ref.year_hint:
            meta["year_hint"] = ref.year_hint
        if ref.surrounding_text:
            meta["surrounding_text"] = ref.surrounding_text
        return meta

    # ------------------------------------------------------------------
    # 去重 key
    # ------------------------------------------------------------------

    @staticmethod
    def _paper_dedup_key(ref: ExtractedPaperReference) -> str:
        if ref.doi_hint:
            return f"doi:{ref.doi_hint.lower()}"
        if ref.arxiv_id:
            return f"arxiv:{ref.arxiv_id.lower()}"
        return f"title:{ref.title.strip().lower()}"
