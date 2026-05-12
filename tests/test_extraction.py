"""正文提取模块测试。"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from models.enums import DownloadStatus
from models.schemas import ExtractedDocument, SourceItem
from providers.extraction.base import BaseExtractor, ExtractedContent
from providers.extraction.trafilatura_extractor import TrafilaturaExtractor
from services.extraction_service import ExtractionService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# === Mock Extractor ===


class MockExtractor(BaseExtractor):
    """测试用 Mock 提取器。"""

    def __init__(self, result: ExtractedContent | None = None):
        self._result = result

    @property
    def name(self) -> str:
        return "mock"

    async def extract(self, url: str) -> ExtractedContent:
        if self._result:
            return self._result
        return ExtractedContent(
            title="Mock Title",
            author="Mock Author",
            published_at="2024-01-01",
            source_url=url,
            text="Mock extracted content with enough text.",
            success=True,
        )


class MockFailingExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "mock_failing"

    async def extract(self, url: str) -> ExtractedContent:
        return ExtractedContent(
            source_url=url,
            success=False,
            error="Simulated extraction failure",
        )


# === BaseExtractor Tests ===


class TestBaseExtractor:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseExtractor()


# === ExtractedContent Tests ===


class TestExtractedContent:
    def test_success_defaults(self):
        c = ExtractedContent(source_url="https://example.com", text="content")
        assert c.success is True
        assert c.error is None

    def test_failure_state(self):
        c = ExtractedContent(source_url="https://x.com", success=False, error="timeout")
        assert c.success is False
        assert c.error == "timeout"
        assert c.text == ""


# === TrafilaturaExtractor Tests ===


class TestTrafilaturaExtractor:
    @pytest.fixture
    def extractor(self):
        return TrafilaturaExtractor()

    def test_name(self, extractor):
        assert extractor.name == "trafilatura"

    @pytest.mark.asyncio
    async def test_invalid_url_returns_failure(self, extractor):
        result = await extractor.extract("not-a-url")
        assert result.success is False
        assert "Invalid URL" in result.error

    @pytest.mark.asyncio
    async def test_empty_url_returns_failure(self, extractor):
        result = await extractor.extract("")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_ftp_url_returns_failure(self, extractor):
        result = await extractor.extract("ftp://files.example.com/doc.pdf")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_extract_from_html_string(self, extractor):
        """测试用本地 HTML fixture 验证提取逻辑。"""
        html_path = FIXTURES_DIR / "sample_article.html"
        html_content = html_path.read_text(encoding="utf-8")

        # Mock fetch_url 返回本地 HTML
        with patch("providers.extraction.trafilatura_extractor.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = html_content
            mock_traf.extract.side_effect = [
                # 第一次调用：提取正文
                "Quantum computing represents a fundamentally different approach to computation. "
                "The field originated in the early 1980s when physicist Richard Feynman proposed "
                "that quantum systems could be used to simulate other quantum systems.",
                # 第二次调用：提取 JSON 元数据
                '{"title": "The History of Quantum Computing", "author": "Dr. Alice Smith", "date": "2024-03-15"}',
            ]

            result = await extractor.extract("https://example.com/article")

            assert result.success is True
            assert "quantum" in result.text.lower()
            assert result.title == "The History of Quantum Computing"
            assert result.author == "Dr. Alice Smith"
            assert result.published_at == "2024-03-15"
            assert result.source_url == "https://example.com/article"

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_error(self, extractor):
        with patch("providers.extraction.trafilatura_extractor.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = None

            result = await extractor.extract("https://unreachable.example.com")

            assert result.success is False
            assert "fetch" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_extraction_returns_error(self, extractor):
        with patch("providers.extraction.trafilatura_extractor.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body></body></html>"
            mock_traf.extract.return_value = ""

            result = await extractor.extract("https://example.com/empty")

            assert result.success is False
            assert "empty" in result.error.lower()

    def test_parse_metadata_valid_json(self):
        result = TrafilaturaExtractor._parse_metadata('{"title": "Test", "author": "Bob"}')
        assert result["title"] == "Test"
        assert result["author"] == "Bob"

    def test_parse_metadata_invalid_json(self):
        result = TrafilaturaExtractor._parse_metadata("not json")
        assert result == {}

    def test_parse_metadata_none(self):
        result = TrafilaturaExtractor._parse_metadata(None)
        assert result == {}


# === ExtractionService Tests ===


def _make_source_item(url: str = "https://example.com/article") -> SourceItem:
    return SourceItem(
        task_id="task-1",
        url=url,
        title="Original Title",
        domain="example.com",
    )


class TestExtractionService:
    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        service = ExtractionService(extractor=MockExtractor())
        item = _make_source_item()

        doc = await service.extract_source(item)

        assert isinstance(doc, ExtractedDocument)
        assert doc.title == "Mock Title"
        assert doc.content == "Mock extracted content with enough text."
        assert doc.source_item_id == item.id
        assert item.download_status == DownloadStatus.EXTRACTED

    @pytest.mark.asyncio
    async def test_failed_extraction_marks_failed(self):
        service = ExtractionService(extractor=MockFailingExtractor())
        item = _make_source_item()

        doc = await service.extract_source(item)

        assert doc.content == ""
        assert item.download_status == DownloadStatus.FAILED

    @pytest.mark.asyncio
    async def test_uses_source_title_as_fallback(self):
        extractor = MockExtractor(result=ExtractedContent(
            title="",  # 提取器没拿到 title
            source_url="https://example.com",
            text="Some content",
            success=True,
        ))
        service = ExtractionService(extractor=extractor)
        item = _make_source_item()

        doc = await service.extract_source(item)

        # 应该 fallback 到 source_item 的 title
        assert doc.title == "Original Title"

    @pytest.mark.asyncio
    async def test_download_status_transitions(self):
        service = ExtractionService(extractor=MockExtractor())
        item = _make_source_item()

        assert item.download_status == DownloadStatus.PENDING
        doc = await service.extract_source(item)
        assert item.download_status == DownloadStatus.EXTRACTED

    @pytest.mark.asyncio
    async def test_extraction_with_custom_extractor(self):
        """验证可以注入不同的提取器。"""
        custom_result = ExtractedContent(
            title="Custom Title",
            author="Custom Author",
            source_url="https://example.com",
            text="Custom extracted text",
            success=True,
        )
        service = ExtractionService(extractor=MockExtractor(result=custom_result))
        item = _make_source_item()

        doc = await service.extract_source(item)

        assert doc.title == "Custom Title"
        assert doc.content == "Custom extracted text"
