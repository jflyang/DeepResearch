"""Google Books Search Provider 测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from models.enums import SearchSource, SourceType
from providers.search.base import SearchProviderError
from providers.search.google_books import GoogleBooksSearchProvider


@pytest.fixture
def provider():
    return GoogleBooksSearchProvider()


@pytest.fixture
def mock_google_books_response():
    return {
        "totalItems": 3,
        "items": [
            {
                "volumeInfo": {
                    "title": "Deep Learning",
                    "authors": ["Ian Goodfellow", "Yoshua Bengio"],
                    "subtitle": "An MIT Press Book",
                    "description": "A comprehensive textbook on deep learning methods.",
                    "publishedDate": "2016-11-18",
                    "infoLink": "https://books.google.com/books?id=deep1",
                }
            },
            {
                "volumeInfo": {
                    "title": "Year Only Book",
                    "authors": ["Author X"],
                    "publishedDate": "2020",
                    "infoLink": "https://books.google.com/books?id=year1",
                }
            },
            {
                "volumeInfo": {
                    "title": "No Link Book",
                    "authors": ["Nobody"],
                    "publishedDate": "2021",
                    # 没有 infoLink，应被过滤
                }
            },
        ],
    }


class TestGoogleBooksProviderName:
    def test_provider_name(self, provider):
        assert provider.provider_name == SearchSource.GOOGLE_BOOKS


class TestGoogleBooksDisabled:
    @pytest.mark.asyncio
    async def test_returns_empty_when_disabled(self, provider):
        with patch("providers.search.google_books.get_settings") as mock_settings:
            mock_settings.return_value.enable_google_books = False
            results = await provider.search("test")
            assert results == []


class TestGoogleBooksParseResults:
    def test_filters_items_without_info_link(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert len(results) == 2

    def test_source_type_is_book(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        for r in results:
            assert r.source_type == SourceType.BOOK

    def test_source_provider_is_google_books(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        for r in results:
            assert r.source_provider == SearchSource.GOOGLE_BOOKS

    def test_maps_title_and_url(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert results[0].title == "Deep Learning"
        assert results[0].url == "https://books.google.com/books?id=deep1"

    def test_snippet_contains_authors(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert "Ian Goodfellow" in results[0].snippet
        assert "Yoshua Bengio" in results[0].snippet

    def test_snippet_contains_subtitle(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert "An MIT Press Book" in results[0].snippet

    def test_snippet_contains_description(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert "comprehensive textbook" in results[0].snippet

    def test_handles_published_date_full(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert results[0].published_at is not None
        assert results[0].published_at.year == 2016
        assert results[0].published_at.month == 11

    def test_handles_published_date_year_only(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert results[1].published_at is not None
        assert results[1].published_at.year == 2020

    def test_empty_items(self, provider):
        results = provider._parse_results({"items": []})
        assert results == []

    def test_missing_items_key(self, provider):
        results = provider._parse_results({})
        assert results == []

    def test_raw_contains_volume_info(self, provider, mock_google_books_response):
        results = provider._parse_results(mock_google_books_response)
        assert "title" in results[0].raw
        assert "authors" in results[0].raw


class TestGoogleBooksBuildSnippet:
    def test_full_snippet(self):
        snippet = GoogleBooksSearchProvider._build_snippet(
            authors=["Alice", "Bob"],
            subtitle="A Great Book",
            description="Long description here.",
        )
        assert "by Alice, Bob" in snippet
        assert "A Great Book" in snippet
        assert "Long description" in snippet

    def test_no_authors(self):
        snippet = GoogleBooksSearchProvider._build_snippet(
            authors=[], subtitle="Sub", description="Desc"
        )
        assert "by" not in snippet
        assert "Sub" in snippet

    def test_no_subtitle(self):
        snippet = GoogleBooksSearchProvider._build_snippet(
            authors=["X"], subtitle="", description="Desc"
        )
        assert "by X" in snippet
        assert "Desc" in snippet

    def test_all_empty(self):
        snippet = GoogleBooksSearchProvider._build_snippet(
            authors=[], subtitle="", description=""
        )
        assert snippet == ""

    def test_description_truncated(self):
        long_desc = "x" * 300
        snippet = GoogleBooksSearchProvider._build_snippet(
            authors=[], subtitle="", description=long_desc
        )
        assert len(snippet) <= 200


class TestGoogleBooksParseDate:
    def test_full_date(self):
        dt = GoogleBooksSearchProvider._parse_date("2016-11-18")
        assert dt.year == 2016
        assert dt.month == 11
        assert dt.day == 18

    def test_year_month(self):
        dt = GoogleBooksSearchProvider._parse_date("2020-03")
        assert dt.year == 2020
        assert dt.month == 3

    def test_year_only(self):
        dt = GoogleBooksSearchProvider._parse_date("2019")
        assert dt.year == 2019

    def test_none(self):
        assert GoogleBooksSearchProvider._parse_date(None) is None

    def test_empty(self):
        assert GoogleBooksSearchProvider._parse_date("") is None

    def test_invalid(self):
        assert GoogleBooksSearchProvider._parse_date("not-a-date") is None


class TestGoogleBooksHttpErrors:
    @pytest.mark.asyncio
    async def test_non_200_raises_error(self, provider):
        import httpx

        mock_response = httpx.Response(
            status_code=403,
            text="Forbidden",
            request=httpx.Request("GET", "https://www.googleapis.com/books/v1/volumes"),
        )

        with patch("providers.search.google_books.get_settings") as mock_settings:
            mock_settings.return_value.enable_google_books = True
            mock_settings.return_value.google_books_api_key = ""

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_response

                with pytest.raises(SearchProviderError) as exc_info:
                    await provider.search("test")

                assert exc_info.value.status_code == 403
                assert exc_info.value.provider == "google_books"
