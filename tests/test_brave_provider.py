"""Brave Search Provider 测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from models.enums import SearchSource, SourceType
from providers.search.base import SearchProviderError
from providers.search.brave import BraveSearchProvider


@pytest.fixture
def provider():
    return BraveSearchProvider()


@pytest.fixture
def mock_brave_response():
    return {
        "web": {
            "results": [
                {
                    "title": "Python Documentation",
                    "url": "https://docs.python.org/3/tutorial/",
                    "description": "The Python Tutorial.",
                    "page_age": "2024-06-01T00:00:00Z",
                },
                {
                    "title": "Stack Overflow Question",
                    "url": "https://stackoverflow.com/questions/123",
                    "description": "How to do X in Python?",
                    "page_age": None,
                },
                {
                    "title": "Empty URL",
                    "url": "",
                    "description": "Should be skipped.",
                },
            ]
        }
    }


class TestBraveProviderName:
    def test_provider_name(self, provider):
        assert provider.provider_name == SearchSource.BRAVE


class TestBraveNoApiKey:
    @pytest.mark.asyncio
    async def test_returns_empty_without_key(self, provider):
        with patch("providers.search.brave.get_settings") as mock_settings:
            mock_settings.return_value.brave_available = False
            results = await provider.search("test query")
            assert results == []


class TestBraveParseResults:
    def test_filters_empty_urls(self, provider, mock_brave_response):
        results = provider._parse_results(mock_brave_response)
        assert len(results) == 2

    def test_maps_fields_correctly(self, provider, mock_brave_response):
        results = provider._parse_results(mock_brave_response)
        first = results[0]
        assert first.title == "Python Documentation"
        assert first.url == "https://docs.python.org/3/tutorial/"
        assert first.snippet == "The Python Tutorial."
        assert first.source_provider == SearchSource.BRAVE

    def test_infers_source_type(self, provider, mock_brave_response):
        results = provider._parse_results(mock_brave_response)
        assert results[0].source_type == SourceType.DOCUMENTATION
        assert results[1].source_type == SourceType.FORUM

    def test_handles_published_at(self, provider, mock_brave_response):
        results = provider._parse_results(mock_brave_response)
        assert results[0].published_at is not None
        assert results[0].published_at.year == 2024
        assert results[1].published_at is None

    def test_empty_web_results(self, provider):
        results = provider._parse_results({"web": {"results": []}})
        assert results == []

    def test_missing_web_key(self, provider):
        results = provider._parse_results({})
        assert results == []

    def test_missing_results_key(self, provider):
        results = provider._parse_results({"web": {}})
        assert results == []


class TestBraveParseDate:
    def test_iso_with_z(self):
        dt = BraveSearchProvider._parse_date("2024-06-01T00:00:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6

    def test_iso_without_timezone(self):
        dt = BraveSearchProvider._parse_date("2024-03-15T12:30:00")
        assert dt is not None
        assert dt.year == 2024

    def test_date_only(self):
        dt = BraveSearchProvider._parse_date("2023-11-20")
        assert dt is not None
        assert dt.year == 2023

    def test_none_input(self):
        assert BraveSearchProvider._parse_date(None) is None

    def test_empty_string(self):
        assert BraveSearchProvider._parse_date("") is None

    def test_invalid_format(self):
        assert BraveSearchProvider._parse_date("not-a-date") is None


class TestBraveHttpErrors:
    @pytest.mark.asyncio
    async def test_non_200_raises_error(self, provider):
        import httpx

        mock_response = httpx.Response(
            status_code=401,
            text="Unauthorized",
            request=httpx.Request("GET", "https://api.search.brave.com/res/v1/web/search"),
        )

        with patch("providers.search.brave.get_settings") as mock_settings:
            mock_settings.return_value.brave_available = True
            mock_settings.return_value.brave_api_key = "BSA-test"
            mock_settings.return_value.default_result_limit = 10

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_response

                with pytest.raises(SearchProviderError) as exc_info:
                    await provider.search("test")

                assert exc_info.value.status_code == 401
                assert exc_info.value.provider == "brave"
