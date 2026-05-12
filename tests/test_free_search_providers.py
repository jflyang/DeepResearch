"""测试免费搜索 Provider - JSON/XML 解析、错误处理。"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from models.enums import SearchSource, SourceType


# ============================================================
# SearXNG
# ============================================================


class TestSearXNGProvider:
    """SearXNG Provider 测试。"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.enable_searxng = True
        settings.searxng_base_url = "http://localhost:8080"
        settings.searxng_timeout_seconds = 20
        return settings

    @pytest.fixture
    def searxng_json(self):
        return {
            "results": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "content": "This is a test snippet",
                    "publishedDate": "2024-01-01",
                },
                {
                    "title": "Test Result 2",
                    "url": "https://example.com/2",
                    "snippet": "Another snippet",
                },
            ]
        }

    @patch("providers.search.searxng.get_settings")
    async def test_normal_json_parse(self, mock_get_settings, mock_settings, searxng_json):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = searxng_json

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.searxng import SearXNGSearchProvider
            provider = SearXNGSearchProvider()
            results = await provider.search("test query", limit=10)

        assert len(results) == 2
        assert results[0].title == "Test Result 1"
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "This is a test snippet"
        assert results[0].source_provider == SearchSource.SEARXNG
        assert results[0].source_type == SourceType.WEB

    @patch("providers.search.searxng.get_settings")
    async def test_empty_results(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.searxng import SearXNGSearchProvider
            provider = SearXNGSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []

    @patch("providers.search.searxng.get_settings")
    async def test_base_url_not_configured(self, mock_get_settings):
        settings = MagicMock()
        settings.enable_searxng = True
        settings.searxng_base_url = ""
        mock_get_settings.return_value = settings

        from providers.search.searxng import SearXNGSearchProvider
        provider = SearXNGSearchProvider()
        results = await provider.search("test", limit=10)
        assert results == []

    @patch("providers.search.searxng.get_settings")
    async def test_http_500(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.searxng import SearXNGSearchProvider
            provider = SearXNGSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []

    @patch("providers.search.searxng.get_settings")
    async def test_timeout(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.searxng import SearXNGSearchProvider
            provider = SearXNGSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []


# ============================================================
# Open Library
# ============================================================


class TestOpenLibraryProvider:
    """Open Library Provider 测试。"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.enable_open_library = True
        return settings

    @pytest.fixture
    def open_library_json(self):
        return {
            "docs": [
                {
                    "title": "Deep Learning",
                    "key": "/works/OL123W",
                    "author_name": ["Ian Goodfellow", "Yoshua Bengio"],
                    "first_publish_year": 2016,
                    "publisher": ["MIT Press"],
                    "subject": ["Machine learning", "Neural networks"],
                },
                {
                    "title": "Another Book",
                    "key": "/works/OL456W",
                    "first_publish_year": 2020,
                },
            ]
        }

    @patch("providers.search.open_library.get_settings")
    async def test_normal_docs_parse(self, mock_get_settings, mock_settings, open_library_json):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = open_library_json

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.open_library import OpenLibrarySearchProvider
            provider = OpenLibrarySearchProvider()
            results = await provider.search("deep learning", limit=10)

        assert len(results) == 2
        assert results[0].title == "Deep Learning"
        assert results[0].url == "https://openlibrary.org/works/OL123W"
        assert results[0].source_provider == SearchSource.OPEN_LIBRARY
        assert results[0].source_type == SourceType.BOOK
        assert "Ian Goodfellow" in results[0].authors

    @patch("providers.search.open_library.get_settings")
    async def test_no_key_url_fallback(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        data = {"docs": [{"title": "No Key Book"}]}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = data

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.open_library import OpenLibrarySearchProvider
            provider = OpenLibrarySearchProvider()
            results = await provider.search("test", limit=10)

        assert len(results) == 1
        assert results[0].url == ""  # No key → empty URL

    @patch("providers.search.open_library.get_settings")
    async def test_no_author_name(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        data = {"docs": [{"title": "Anonymous Book", "key": "/works/OL789W"}]}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = data

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.open_library import OpenLibrarySearchProvider
            provider = OpenLibrarySearchProvider()
            results = await provider.search("test", limit=10)

        assert len(results) == 1
        assert results[0].authors == []

    @patch("providers.search.open_library.get_settings")
    async def test_network_failure(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.open_library import OpenLibrarySearchProvider
            provider = OpenLibrarySearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []


# ============================================================
# Crossref
# ============================================================


class TestCrossrefProvider:
    """Crossref Provider 测试。"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.enable_crossref = True
        settings.crossref_mailto = ""
        settings.crossref_timeout_seconds = 20
        return settings

    @pytest.fixture
    def crossref_json(self):
        return {
            "message": {
                "items": [
                    {
                        "title": ["Attention Is All You Need"],
                        "URL": "https://doi.org/10.1234/test",
                        "DOI": "10.1234/test",
                        "container-title": ["NeurIPS"],
                        "abstract": "<jats:p>We propose a new architecture...</jats:p>",
                        "author": [
                            {"given": "Ashish", "family": "Vaswani"},
                            {"given": "Noam", "family": "Shazeer"},
                        ],
                        "issued": {"date-parts": [[2017, 6, 12]]},
                    }
                ]
            }
        }

    @patch("providers.search.crossref.get_settings")
    async def test_normal_items_parse(self, mock_get_settings, mock_settings, crossref_json):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = crossref_json

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.crossref import CrossrefSearchProvider
            provider = CrossrefSearchProvider()
            results = await provider.search("attention", limit=10)

        assert len(results) == 1
        assert results[0].title == "Attention Is All You Need"
        assert results[0].url == "https://doi.org/10.1234/test"
        assert results[0].source_provider == SearchSource.CROSSREF
        assert results[0].source_type == SourceType.PAPER
        assert "Ashish Vaswani" in results[0].authors

    @patch("providers.search.crossref.get_settings")
    async def test_doi_url_fallback(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        data = {
            "message": {
                "items": [
                    {
                        "title": ["Test Paper"],
                        "DOI": "10.5678/fallback",
                        "author": [],
                    }
                ]
            }
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = data

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.crossref import CrossrefSearchProvider
            provider = CrossrefSearchProvider()
            results = await provider.search("test", limit=10)

        assert len(results) == 1
        assert results[0].url == "https://doi.org/10.5678/fallback"

    @patch("providers.search.crossref.get_settings")
    async def test_authors_parse(self, mock_get_settings, mock_settings, crossref_json):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = crossref_json

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.crossref import CrossrefSearchProvider
            provider = CrossrefSearchProvider()
            results = await provider.search("test", limit=10)

        assert results[0].authors == ["Ashish Vaswani", "Noam Shazeer"]

    @patch("providers.search.crossref.get_settings")
    async def test_abstract_missing(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        data = {
            "message": {
                "items": [
                    {
                        "title": ["No Abstract Paper"],
                        "URL": "https://example.com",
                        "author": [],
                    }
                ]
            }
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = data

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.crossref import CrossrefSearchProvider
            provider = CrossrefSearchProvider()
            results = await provider.search("test", limit=10)

        assert len(results) == 1
        assert results[0].snippet == ""

    @patch("providers.search.crossref.get_settings")
    async def test_429_returns_empty(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limited"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.crossref import CrossrefSearchProvider
            provider = CrossrefSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []


# ============================================================
# arXiv
# ============================================================


class TestArxivProvider:
    """arXiv Provider 测试。"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.enable_arxiv = True
        settings.arxiv_timeout_seconds = 20
        return settings

    @pytest.fixture
    def arxiv_atom_xml(self):
        return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v1</id>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Another Paper</title>
    <summary>Some summary text.</summary>
    <published>2023-01-01T00:00:00Z</published>
    <author><name>John Doe</name></author>
  </entry>
</feed>"""

    @patch("providers.search.arxiv.get_settings")
    async def test_normal_atom_parse(self, mock_get_settings, mock_settings, arxiv_atom_xml):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = arxiv_atom_xml

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.arxiv import ArxivSearchProvider
            provider = ArxivSearchProvider()
            results = await provider.search("attention", limit=10)

        assert len(results) == 2
        assert results[0].title == "Attention Is All You Need"
        assert results[0].url == "http://arxiv.org/abs/1706.03762v1"
        assert results[0].source_provider == SearchSource.ARXIV
        assert results[0].source_type == SourceType.PAPER

    @patch("providers.search.arxiv.get_settings")
    async def test_multiple_authors(self, mock_get_settings, mock_settings, arxiv_atom_xml):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = arxiv_atom_xml

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.arxiv import ArxivSearchProvider
            provider = ArxivSearchProvider()
            results = await provider.search("test", limit=10)

        assert results[0].authors == ["Ashish Vaswani", "Noam Shazeer"]

    @patch("providers.search.arxiv.get_settings")
    async def test_empty_feed(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = empty_xml

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.arxiv import ArxivSearchProvider
            provider = ArxivSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []

    @patch("providers.search.arxiv.get_settings")
    async def test_xml_parse_error(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "not valid xml <<<"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.arxiv import ArxivSearchProvider
            provider = ArxivSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []

    @patch("providers.search.arxiv.get_settings")
    async def test_network_failure(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.arxiv import ArxivSearchProvider
            provider = ArxivSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []


# ============================================================
# Wikipedia
# ============================================================


class TestWikipediaProvider:
    """Wikipedia Provider 测试。"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.enable_wikipedia = True
        settings.wikipedia_language = "en"
        settings.wikipedia_timeout_seconds = 20
        return settings

    @pytest.fixture
    def wikipedia_json(self):
        return {
            "query": {
                "search": [
                    {
                        "title": "Machine learning",
                        "snippet": '<span class="searchmatch">Machine</span> learning is a subset of AI.',
                        "timestamp": "2024-01-15T10:00:00Z",
                    },
                    {
                        "title": "Deep learning",
                        "snippet": "Deep learning uses <b>neural networks</b>.",
                        "timestamp": "2024-02-01T12:00:00Z",
                    },
                ]
            }
        }

    @patch("providers.search.wikipedia.get_settings")
    async def test_normal_search_parse(self, mock_get_settings, mock_settings, wikipedia_json):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = wikipedia_json

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.wikipedia import WikipediaSearchProvider
            provider = WikipediaSearchProvider()
            results = await provider.search("machine learning", limit=10)

        assert len(results) == 2
        assert results[0].title == "Machine learning"
        assert results[0].url == "https://en.wikipedia.org/wiki/Machine_learning"
        assert results[0].source_provider == SearchSource.WIKIPEDIA
        assert results[0].source_type == SourceType.REFERENCE

    @patch("providers.search.wikipedia.get_settings")
    async def test_snippet_html_stripped(self, mock_get_settings, mock_settings, wikipedia_json):
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = wikipedia_json

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.wikipedia import WikipediaSearchProvider
            provider = WikipediaSearchProvider()
            results = await provider.search("test", limit=10)

        # HTML tags should be stripped
        assert "<span" not in results[0].snippet
        assert "<b>" not in results[1].snippet
        assert "Machine learning is a subset of AI." in results[0].snippet

    @patch("providers.search.wikipedia.get_settings")
    async def test_language_config(self, mock_get_settings):
        settings = MagicMock()
        settings.enable_wikipedia = True
        settings.wikipedia_language = "zh"
        settings.wikipedia_timeout_seconds = 20
        mock_get_settings.return_value = settings

        data = {
            "query": {
                "search": [
                    {"title": "机器学习", "snippet": "机器学习是人工智能的子集", "timestamp": "2024-01-01T00:00:00Z"}
                ]
            }
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = data

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.wikipedia import WikipediaSearchProvider
            provider = WikipediaSearchProvider()
            results = await provider.search("机器学习", limit=10)

        assert len(results) == 1
        assert "zh.wikipedia.org" in results[0].url

    @patch("providers.search.wikipedia.get_settings")
    async def test_network_failure(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from providers.search.wikipedia import WikipediaSearchProvider
            provider = WikipediaSearchProvider()
            results = await provider.search("test", limit=10)

        assert results == []
