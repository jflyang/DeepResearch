"""ReferenceExtractionService 单元测试。"""

import pytest

from app.services.reference_extraction_service import ReferenceExtractionService
from models.enums import ReferenceStatus, ReferenceType
from models.schemas import (
    ExtractedBookReference,
    ExtractedPaperReference,
    ExtractedUrlReference,
    ParsedReport,
    ReferenceCandidate,
)


@pytest.fixture
def service():
    return ReferenceExtractionService()


class TestUrlConversion:
    def test_url_to_candidate(self, service):
        parsed = ParsedReport(
            urls=[
                ExtractedUrlReference(
                    url="https://example.com/article",
                    title_hint="Example Article",
                    surrounding_text="context text here",
                )
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1
        c = result[0]
        assert c.type == ReferenceType.URL
        assert c.value == "https://example.com/article"
        assert c.title_hint == "Example Article"
        assert c.source_url == "https://example.com/article"
        assert c.status == ReferenceStatus.PARSED
        assert c.confidence == 1.0

    def test_multiple_urls(self, service):
        parsed = ParsedReport(
            urls=[
                ExtractedUrlReference(url="https://a.com/1"),
                ExtractedUrlReference(url="https://b.com/2"),
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 2
        values = {c.value for c in result}
        assert "https://a.com/1" in values
        assert "https://b.com/2" in values


class TestBookConversion:
    def test_book_to_candidate(self, service):
        parsed = ParsedReport(
            books=[
                ExtractedBookReference(
                    title="蒂姆·库克传",
                    author_hint="利恩德·卡尼",
                    year_hint="2019",
                    surrounding_text="在《蒂姆·库克传》中描述了...",
                    confidence=0.7,
                )
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1
        c = result[0]
        assert c.type == ReferenceType.BOOK
        assert c.value == "蒂姆·库克传"
        assert c.title_hint == "蒂姆·库克传"
        assert c.source_url is None
        assert c.status == ReferenceStatus.PARSED
        assert c.confidence == 0.7

    def test_book_metadata(self, service):
        parsed = ParsedReport(
            books=[
                ExtractedBookReference(
                    title="Deep Learning",
                    author_hint="Ian Goodfellow",
                    year_hint="2016",
                    surrounding_text="As described in Deep Learning...",
                    confidence=0.8,
                )
            ]
        )
        result = service.extract(parsed)
        c = result[0]
        assert c.metadata["author_hint"] == "Ian Goodfellow"
        assert c.metadata["year_hint"] == "2016"
        assert c.metadata["surrounding_text"] == "As described in Deep Learning..."


class TestPaperDoiConversion:
    def test_paper_doi_to_candidate(self, service):
        parsed = ParsedReport(
            papers=[
                ExtractedPaperReference(
                    title="DOI:10.1145/3292500.3330648",
                    doi_hint="10.1145/3292500.3330648",
                    surrounding_text="该论文的标识为...",
                    confidence=0.9,
                )
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1
        c = result[0]
        assert c.type == ReferenceType.PAPER
        assert c.value == "10.1145/3292500.3330648"
        assert c.confidence == 0.9
        assert c.metadata["doi_hint"] == "10.1145/3292500.3330648"


class TestPaperArxivConversion:
    def test_paper_arxiv_to_candidate(self, service):
        parsed = ParsedReport(
            papers=[
                ExtractedPaperReference(
                    title="arXiv:1706.03762",
                    arxiv_id="1706.03762",
                    surrounding_text="Transformer 论文...",
                    confidence=0.9,
                )
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1
        c = result[0]
        assert c.type == ReferenceType.PAPER
        assert c.value == "1706.03762"
        assert c.metadata["arxiv_id"] == "1706.03762"

    def test_paper_value_priority(self, service):
        """DOI 优先于 arXiv ID。"""
        parsed = ParsedReport(
            papers=[
                ExtractedPaperReference(
                    title="Some Paper",
                    doi_hint="10.1000/test",
                    arxiv_id="2301.00001",
                    confidence=0.9,
                )
            ]
        )
        result = service.extract(parsed)
        assert result[0].value == "10.1000/test"


class TestUrlDeduplication:
    def test_duplicate_urls_removed(self, service):
        parsed = ParsedReport(
            urls=[
                ExtractedUrlReference(url="https://example.com/page", title_hint="First"),
                ExtractedUrlReference(url="https://example.com/page", title_hint="Second"),
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1
        assert result[0].title_hint == "First"

    def test_case_insensitive_dedup(self, service):
        parsed = ParsedReport(
            urls=[
                ExtractedUrlReference(url="https://Example.COM/Page"),
                ExtractedUrlReference(url="https://example.com/page"),
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1

    def test_trailing_slash_dedup(self, service):
        parsed = ParsedReport(
            urls=[
                ExtractedUrlReference(url="https://example.com/page/"),
                ExtractedUrlReference(url="https://example.com/page"),
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1


class TestBookDeduplication:
    def test_duplicate_books_removed(self, service):
        parsed = ParsedReport(
            books=[
                ExtractedBookReference(title="Deep Learning", confidence=0.8),
                ExtractedBookReference(title="deep learning", confidence=0.6),
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 1
        assert result[0].value == "Deep Learning"

    def test_different_books_kept(self, service):
        parsed = ParsedReport(
            books=[
                ExtractedBookReference(title="Book A", confidence=0.7),
                ExtractedBookReference(title="Book B", confidence=0.7),
            ]
        )
        result = service.extract(parsed)
        assert len(result) == 2


class TestMetadataSurroundingText:
    def test_url_surrounding_text_in_metadata(self, service):
        parsed = ParsedReport(
            urls=[
                ExtractedUrlReference(
                    url="https://example.com",
                    surrounding_text="前后文内容",
                )
            ]
        )
        result = service.extract(parsed)
        assert result[0].metadata["surrounding_text"] == "前后文内容"

    def test_book_surrounding_text_in_metadata(self, service):
        parsed = ParsedReport(
            books=[
                ExtractedBookReference(
                    title="Test Book",
                    surrounding_text="在《Test Book》中提到...",
                    confidence=0.7,
                )
            ]
        )
        result = service.extract(parsed)
        assert result[0].metadata["surrounding_text"] == "在《Test Book》中提到..."

    def test_paper_surrounding_text_in_metadata(self, service):
        parsed = ParsedReport(
            papers=[
                ExtractedPaperReference(
                    title="arXiv:2301.00001",
                    arxiv_id="2301.00001",
                    surrounding_text="参考该论文的方法...",
                    confidence=0.9,
                )
            ]
        )
        result = service.extract(parsed)
        assert result[0].metadata["surrounding_text"] == "参考该论文的方法..."

    def test_no_surrounding_text_omitted(self, service):
        parsed = ParsedReport(
            urls=[ExtractedUrlReference(url="https://example.com")]
        )
        result = service.extract(parsed)
        assert "surrounding_text" not in result[0].metadata


class TestEdgeCases:
    def test_empty_parsed_report(self, service):
        result = service.extract(ParsedReport())
        assert result == []

    def test_mixed_types(self, service):
        parsed = ParsedReport(
            urls=[ExtractedUrlReference(url="https://example.com")],
            books=[ExtractedBookReference(title="Book", confidence=0.7)],
            papers=[ExtractedPaperReference(title="arXiv:2301.00001", arxiv_id="2301.00001", confidence=0.9)],
        )
        result = service.extract(parsed)
        assert len(result) == 3
        types = {c.type for c in result}
        assert types == {ReferenceType.URL, ReferenceType.BOOK, ReferenceType.PAPER}
