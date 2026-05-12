"""搜索 Provider 抽象层测试。"""

import pytest

from models.enums import SearchSource, SourceType
from providers.search.base import BaseSearchProvider, SearchProviderError, SearchResult


# === SearchResult Tests ===


class TestSearchResult:
    def test_minimal_creation(self):
        r = SearchResult(
            title="Test",
            url="https://example.com",
            source_provider=SearchSource.TAVILY,
        )
        assert r.title == "Test"
        assert r.url == "https://example.com"
        assert r.source_provider == SearchSource.TAVILY

    def test_defaults(self):
        r = SearchResult(
            title="T",
            url="https://x.com",
            source_provider=SearchSource.BRAVE,
        )
        assert r.snippet == ""
        assert r.source_type == SourceType.OTHER
        assert r.published_at is None
        assert r.raw == {}

    def test_raw_excluded_from_serialization(self):
        r = SearchResult(
            title="T",
            url="https://x.com",
            source_provider=SearchSource.TAVILY,
            raw={"internal": "data"},
        )
        dumped = r.model_dump()
        assert "raw" not in dumped

    def test_full_creation(self):
        from datetime import UTC, datetime

        r = SearchResult(
            title="Paper Title",
            url="https://arxiv.org/abs/123",
            snippet="Abstract text",
            source_provider=SearchSource.GOOGLE_BOOKS,
            source_type=SourceType.ACADEMIC,
            published_at=datetime(2024, 1, 15, tzinfo=UTC),
            raw={"id": "abc"},
        )
        assert r.source_type == SourceType.ACADEMIC
        assert r.published_at.year == 2024


# === SearchProviderError Tests ===


class TestSearchProviderError:
    def test_basic_error(self):
        err = SearchProviderError(provider="tavily", message="rate limited")
        assert str(err) == "[tavily] rate limited"
        assert err.provider == "tavily"
        assert err.status_code is None

    def test_error_with_status(self):
        err = SearchProviderError(
            provider="brave",
            message="unauthorized",
            status_code=401,
            raw_error="Invalid API key",
        )
        assert err.status_code == 401
        assert err.raw_error == "Invalid API key"

    def test_is_exception(self):
        err = SearchProviderError(provider="x", message="fail")
        assert isinstance(err, Exception)
        with pytest.raises(SearchProviderError):
            raise err


# === BaseSearchProvider Abstract Tests ===


class TestBaseSearchProvider:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseSearchProvider()

    def test_concrete_implementation(self):
        class FakeProvider(BaseSearchProvider):
            @property
            def provider_name(self) -> SearchSource:
                return SearchSource.TAVILY

            async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
                return [
                    SearchResult(
                        title=f"Result for {query}",
                        url="https://example.com",
                        source_provider=self.provider_name,
                    )
                ]

        provider = FakeProvider()
        assert provider.provider_name == SearchSource.TAVILY

    @pytest.mark.asyncio
    async def test_health_check_default(self):
        class FakeProvider(BaseSearchProvider):
            @property
            def provider_name(self) -> SearchSource:
                return SearchSource.BRAVE

            async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
                return []

        provider = FakeProvider()
        assert await provider.health_check() is True
