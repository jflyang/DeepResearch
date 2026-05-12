"""Report Ingestion schema 和 enum 测试。"""

import pytest
from pydantic import ValidationError

from models.enums import ReferenceStatus, ReferenceType, ResearchTaskType, SourceOrigin
from models.schemas import (
    ExtractedBookReference,
    ExtractedPaperReference,
    ExtractedUrlReference,
    ImportedReportCreate,
    ParsedReport,
    ReferenceCandidate,
    ReportIngestionOptions,
    ReportIngestionResult,
)


# === Enum Tests ===


class TestResearchTaskType:
    def test_valid_values(self):
        assert ResearchTaskType.SEARCH_RESEARCH == "search_research"
        assert ResearchTaskType.REPORT_INGESTION == "report_ingestion"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ResearchTaskType("invalid_type")


class TestReferenceType:
    def test_valid_values(self):
        assert ReferenceType.URL == "url"
        assert ReferenceType.BOOK == "book"
        assert ReferenceType.PAPER == "paper"
        assert ReferenceType.ARTICLE == "article"
        assert ReferenceType.INTERVIEW == "interview"
        assert ReferenceType.VIDEO == "video"
        assert ReferenceType.UNKNOWN == "unknown"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ReferenceType("podcast")


class TestReferenceStatus:
    def test_valid_values(self):
        assert ReferenceStatus.PARSED == "parsed"
        assert ReferenceStatus.ENRICHED == "enriched"
        assert ReferenceStatus.EXTRACTED == "extracted"
        assert ReferenceStatus.FAILED == "failed"
        assert ReferenceStatus.SKIPPED == "skipped"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ReferenceStatus("pending")


class TestSourceOrigin:
    def test_valid_values(self):
        assert SourceOrigin.SEARCH_PROVIDER == "search_provider"
        assert SourceOrigin.IMPORTED_REPORT == "imported_report"
        assert SourceOrigin.IMPORTED_REPORT_ENRICHED == "imported_report_enriched"
        assert SourceOrigin.MANUAL == "manual"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            SourceOrigin("api")


# === Schema Tests ===


class TestReportIngestionOptions:
    def test_defaults(self):
        opts = ReportIngestionOptions()
        assert opts.extract_urls is True
        assert opts.enrich_books is True
        assert opts.enrich_papers is True
        assert opts.analyze_documents is True
        assert opts.export_to_obsidian is False

    def test_override_all(self):
        opts = ReportIngestionOptions(
            extract_urls=False,
            enrich_books=False,
            enrich_papers=False,
            analyze_documents=False,
            export_to_obsidian=True,
        )
        assert opts.extract_urls is False
        assert opts.export_to_obsidian is True


class TestImportedReportCreate:
    def test_minimal_creation(self):
        report = ImportedReportCreate(topic="AI 发展", report_text="这是一份报告内容")
        assert report.topic == "AI 发展"
        assert report.report_text == "这是一份报告内容"
        assert report.report_source is None
        assert report.output_language == "zh"
        assert report.options.extract_urls is True

    def test_full_creation(self):
        report = ImportedReportCreate(
            topic="量子计算",
            report_text="量子计算的最新进展...",
            report_source="https://example.com/report.pdf",
            output_language="en",
            options=ReportIngestionOptions(export_to_obsidian=True),
        )
        assert report.report_source == "https://example.com/report.pdf"
        assert report.output_language == "en"
        assert report.options.export_to_obsidian is True

    def test_empty_report_text_raises(self):
        with pytest.raises(ValidationError):
            ImportedReportCreate(topic="test", report_text="")

    def test_whitespace_only_report_text_valid(self):
        # min_length=1 只检查长度，空格算有效字符
        report = ImportedReportCreate(topic="test", report_text=" ")
        assert report.report_text == " "


class TestExtractedUrlReference:
    def test_minimal(self):
        ref = ExtractedUrlReference(url="https://example.com")
        assert ref.url == "https://example.com"
        assert ref.title_hint is None
        assert ref.surrounding_text is None
        assert ref.citation_marker is None

    def test_full(self):
        ref = ExtractedUrlReference(
            url="https://arxiv.org/abs/2301.00001",
            title_hint="Attention Is All You Need",
            surrounding_text="根据论文[1]的研究...",
            citation_marker="[1]",
        )
        assert ref.title_hint == "Attention Is All You Need"
        assert ref.citation_marker == "[1]"


class TestExtractedBookReference:
    def test_minimal(self):
        ref = ExtractedBookReference(title="深度学习")
        assert ref.title == "深度学习"
        assert ref.author_hint is None
        assert ref.year_hint is None
        assert ref.surrounding_text is None
        assert ref.confidence == 0.5

    def test_full(self):
        ref = ExtractedBookReference(
            title="Deep Learning",
            author_hint="Ian Goodfellow",
            year_hint="2016",
            surrounding_text="如 Goodfellow 等人在《Deep Learning》中所述",
            confidence=0.9,
        )
        assert ref.author_hint == "Ian Goodfellow"
        assert ref.confidence == 0.9

    def test_confidence_bounds_lower(self):
        with pytest.raises(ValidationError):
            ExtractedBookReference(title="test", confidence=-0.1)

    def test_confidence_bounds_upper(self):
        with pytest.raises(ValidationError):
            ExtractedBookReference(title="test", confidence=1.1)

    def test_confidence_at_boundaries(self):
        ref_zero = ExtractedBookReference(title="test", confidence=0.0)
        assert ref_zero.confidence == 0.0
        ref_one = ExtractedBookReference(title="test", confidence=1.0)
        assert ref_one.confidence == 1.0


class TestExtractedPaperReference:
    def test_minimal(self):
        ref = ExtractedPaperReference(title="Attention Is All You Need")
        assert ref.title == "Attention Is All You Need"
        assert ref.author_hint is None
        assert ref.doi_hint is None
        assert ref.arxiv_id is None
        assert ref.confidence == 0.5

    def test_full(self):
        ref = ExtractedPaperReference(
            title="Attention Is All You Need",
            author_hint="Vaswani et al.",
            year_hint="2017",
            doi_hint="10.48550/arXiv.1706.03762",
            arxiv_id="1706.03762",
            surrounding_text="Transformer 架构首次在此论文中提出",
            confidence=0.95,
        )
        assert ref.arxiv_id == "1706.03762"
        assert ref.doi_hint == "10.48550/arXiv.1706.03762"

    def test_confidence_bounds_lower(self):
        with pytest.raises(ValidationError):
            ExtractedPaperReference(title="test", confidence=-0.01)

    def test_confidence_bounds_upper(self):
        with pytest.raises(ValidationError):
            ExtractedPaperReference(title="test", confidence=1.01)


class TestParsedReport:
    def test_defaults_empty_lists(self):
        report = ParsedReport()
        assert report.urls == []
        assert report.books == []
        assert report.papers == []
        assert report.people == []
        assert report.organizations == []
        assert report.places == []
        assert report.claims == []
        assert report.raw_citations == []

    def test_with_data(self):
        report = ParsedReport(
            urls=[ExtractedUrlReference(url="https://example.com")],
            books=[ExtractedBookReference(title="Test Book")],
            papers=[ExtractedPaperReference(title="Test Paper")],
            people=["张三", "李四"],
            organizations=["OpenAI"],
            places=["北京"],
            claims=["AI 将改变世界"],
            raw_citations=["[1] https://example.com"],
        )
        assert len(report.urls) == 1
        assert len(report.books) == 1
        assert len(report.papers) == 1
        assert report.people == ["张三", "李四"]

    def test_list_independence(self):
        """确保 default_factory 不会共享实例。"""
        r1 = ParsedReport()
        r2 = ParsedReport()
        r1.people.append("test")
        assert r2.people == []


class TestReferenceCandidate:
    def test_minimal(self):
        ref = ReferenceCandidate(type=ReferenceType.URL, value="https://example.com")
        assert ref.type == ReferenceType.URL
        assert ref.value == "https://example.com"
        assert ref.title_hint is None
        assert ref.source_url is None
        assert ref.status == ReferenceStatus.PARSED
        assert ref.confidence == 0.5
        assert ref.metadata == {}

    def test_full(self):
        ref = ReferenceCandidate(
            type=ReferenceType.PAPER,
            value="Attention Is All You Need",
            title_hint="Transformer 论文",
            source_url="https://arxiv.org/abs/1706.03762",
            status=ReferenceStatus.ENRICHED,
            confidence=0.9,
            metadata={"arxiv_id": "1706.03762", "year": 2017},
        )
        assert ref.status == ReferenceStatus.ENRICHED
        assert ref.metadata["arxiv_id"] == "1706.03762"

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ReferenceCandidate(type=ReferenceType.URL, value="x", confidence=-0.1)
        with pytest.raises(ValidationError):
            ReferenceCandidate(type=ReferenceType.URL, value="x", confidence=1.1)

    def test_metadata_independence(self):
        """确保 default_factory 不会共享 dict 实例。"""
        r1 = ReferenceCandidate(type=ReferenceType.URL, value="a")
        r2 = ReferenceCandidate(type=ReferenceType.URL, value="b")
        r1.metadata["key"] = "val"
        assert r2.metadata == {}


class TestReportIngestionResult:
    def test_minimal(self):
        result = ReportIngestionResult(task_id="abc-123")
        assert result.task_id == "abc-123"
        assert result.parsed_url_count == 0
        assert result.parsed_book_count == 0
        assert result.parsed_paper_count == 0
        assert result.extracted_document_count == 0
        assert result.enriched_source_count == 0
        assert result.failed_count == 0
        assert result.source_count == 0
        assert result.exported_path is None

    def test_full(self):
        result = ReportIngestionResult(
            task_id="task-001",
            parsed_url_count=10,
            parsed_book_count=3,
            parsed_paper_count=5,
            extracted_document_count=8,
            enriched_source_count=6,
            failed_count=2,
            source_count=18,
            exported_path="/vault/research/report",
        )
        assert result.parsed_url_count == 10
        assert result.exported_path == "/vault/research/report"
