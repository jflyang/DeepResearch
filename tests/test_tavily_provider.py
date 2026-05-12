"""Tavily Search Provider 测试。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from models.enums import SearchSource, SourceType
from providers.search.base import SearchProviderError, SearchResult
from providers.search.tavily import TavilySearchProvider


@pytest.fixture
def provider():
    return TavilySearchProvider()


@pytest.fixture
def mock_tavily_response():
    return {
        "query": "quantum computing",
        "results": [
            {
                "title": "Quantum Computing Explained",
                "url": "https://arxiv.org/abs/2301.00001",
                "content": "A comprehensive overview of quantum computing principles.",
                "score": 0.95,
                "published_date": "2024-03-15",
            },
            {
                "title": "Reddit Discussion on QC",
                "url": "https://reddit.com/r/quantum/post1",
                "content": "Community discussion about quantum computing.",
                "score": 0.72,
            },
            {
                "title": "No URL Item",
                "url": "",
                "content": "Should be skipped.",
                "score": 0.5,
            },
        ],
        "response_time": "1.23",
    }


class TestTavilyProviderName:
    def test_provider_name(self, provider):
        assert provider.provider_name == SearchSource.TAVILY


class TestTavilyNoApiKey:
    @pytest.mark.asyncio
    async def test_returns_empty_without_key(self, provider):
        with patch("providers.search.tavily.get_settings") as mock_settings:
            mock_settings.return_value.tavily_available = False
            results = await provider.search("test query")
            assert results == []


class TestTavilyParseResults:
    def test_parse_results_filters_empty_urls(self, provider, mock_tavily_response):
        results = provider._parse_results(mock_tavily_response)
        assert len(results) == 2  # 第三条 url 为空被过滤

    def test_parse_results_maps_fields(self, provider, mock_tavily_response):
        results = provider._parse_results(mock_tavily_response)
        first = results[0]
        assert first.title == "Quantum Computing Explained"
        assert first.url == "https://arxiv.org/abs/2301.00001"
        assert first.snippet == "A comprehensive overview of quantum computing principles."
        assert first.source_provider == SearchSource.TAVILY

    def test_parse_results_infers_source_type(self, provider, mock_tavily_response):
        results = provider._parse_results(mock_tavily_response)
        assert results[0].source_type == SourceType.ACADEMIC
        assert results[1].source_type == SourceType.FORUM

    def test_parse_results_handles_date(self, provider, mock_tavily_response):
        results = provider._parse_results(mock_tavily_response)
        assert results[0].published_at is not None
        assert results[0].published_at.year == 2024
        # 第二条没有日期
        assert results[1].published_at is None

    def test_parse_results_empty_response(self, provider):
        results = provider._parse_results({"results": []})
        assert results == []

    def test_parse_results_missing_results_key(self, provider):
        results = provider._parse_results({})
        assert results == []


class TestTavilyInferSourceType:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://arxiv.org/abs/123", SourceType.ACADEMIC),
            ("https://scholar.google.com/x", SourceType.ACADEMIC),
            ("https://ieee.org/paper", SourceType.ACADEMIC),
            ("https://www.bbc.com/news/article", SourceType.NEWS),
            ("https://reuters.com/world", SourceType.NEWS),
            ("https://docs.python.org/3/", SourceType.DOCUMENTATION),
            ("https://readthedocs.io/proj", SourceType.DOCUMENTATION),
            ("https://stackoverflow.com/q/123", SourceType.FORUM),
            ("https://reddit.com/r/python", SourceType.FORUM),
            ("https://medium.com/@user/post", SourceType.BLOG),
            ("https://dev.to/article", SourceType.BLOG),
            ("https://www.fda.gov/report", SourceType.GOVERNMENT),
            ("https://random-site.com/page", SourceType.OTHER),
        ],
    )
    def test_infer_source_type(self, url, expected):
        assert TavilySearchProvider._infer_source_type(url) == expected


class TestTavilyParseDate:
    def test_valid_iso_date(self):
        dt = TavilySearchProvider._parse_date("2024-06-15")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6

    def test_valid_iso_datetime_with_z(self):
        dt = TavilySearchProvider._parse_date("2024-01-01T12:00:00Z")
        assert dt is not None

    def test_none_input(self):
        assert TavilySearchProvider._parse_date(None) is None

    def test_empty_string(self):
        assert TavilySearchProvider._parse_date("") is None

    def test_invalid_format(self):
        assert TavilySearchProvider._parse_date("not-a-date") is None


class TestTavilyHttpErrors:
    @pytest.mark.asyncio
    async def test_non_200_raises_error(self, provider):
        import httpx

        mock_response = httpx.Response(
            status_code=429,
            text="Rate limited",
            request=httpx.Request("POST", TAVILY_API_URL),
        )

        with patch("providers.search.tavily.get_settings") as mock_settings:
            mock_settings.return_value.tavily_available = True
            mock_settings.return_value.tavily_api_key = "tvly-test"
            mock_settings.return_value.default_result_limit = 10

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                with pytest.raises(SearchProviderError) as exc_info:
                    await provider.search("test")

                assert exc_info.value.status_code == 429
                assert "429" in exc_info.value.message


TAVILY_API_URL = "https://api.tavily.com/search"
