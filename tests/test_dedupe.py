"""去重服务测试。"""

from datetime import UTC, datetime

import pytest

from models.enums import SearchSource, SourceType
from providers.search.base import SearchResult
from services.dedupe_service import (
    DedupedSourceCandidate,
    _merge_snippets,
    _select_better_title,
    dedupe_results,
)
from utils.url import normalize_url


# === URL 规范化测试 ===


class TestNormalizeUrl:
    def test_removes_utm_params(self):
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&id=123"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=123" in result

    def test_removes_fbclid(self):
        url = "https://example.com/article?fbclid=abc123&page=2"
        result = normalize_url(url)
        assert "fbclid" not in result
        assert "page=2" in result

    def test_removes_gclid(self):
        url = "https://example.com/page?gclid=xyz&q=test"
        result = normalize_url(url)
        assert "gclid" not in result
        assert "q=test" in result

    def test_removes_fragment(self):
        url = "https://example.com/page#section-2"
        result = normalize_url(url)
        assert "#" not in result
        assert result == "https://example.com/page"

    def test_removes_trailing_slash(self):
        url = "https://example.com/page/"
        result = normalize_url(url)
        assert result == "https://example.com/page"

    def test_preserves_root_slash(self):
        url = "https://example.com/"
        result = normalize_url(url)
        assert result == "https://example.com/"

    def test_lowercases_scheme_and_domain(self):
        url = "HTTPS://Example.COM/Page"
        result = normalize_url(url)
        assert result.startswith("https://example.com")
        # path 保持原始大小写
        assert "/Page" in result

    def test_preserves_meaningful_query_params(self):
        url = "https://example.com/search?q=python&page=2"
        result = normalize_url(url)
        assert "q=python" in result
        assert "page=2" in result

    def test_sorts_query_params(self):
        url1 = "https://example.com/page?b=2&a=1"
        url2 = "https://example.com/page?a=1&b=2"
        assert normalize_url(url1) == normalize_url(url2)

    def test_same_url_different_utm_normalize_equal(self):
        url1 = "https://example.com/article?utm_source=google"
        url2 = "https://example.com/article?utm_source=twitter&utm_campaign=spring"
        assert normalize_url(url1) == normalize_url(url2)

    def test_http_https_not_merged(self):
        """http 和 https 不强行合并（按要求）。"""
        url1 = "http://example.com/page"
        url2 = "https://example.com/page"
        assert normalize_url(url1) != normalize_url(url2)


# === 去重逻辑测试 ===


def _make_result(
    url: str,
    title: str = "Title",
    snippet: str = "Snippet",
    provider: SearchSource = SearchSource.TAVILY,
    source_type: SourceType = SourceType.OTHER,
    published_at: datetime | None = None,
) -> SearchResult:
    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        source_provider=provider,
        source_type=source_type,
        published_at=published_at,
    )


class TestDedupeResults:
    def test_no_duplicates_returns_all(self):
        results = [
            _make_result("https://a.com/1"),
            _make_result("https://b.com/2"),
            _make_result("https://c.com/3"),
        ]
        deduped = dedupe_results(results)
        assert len(deduped) == 3

    def test_exact_duplicate_merged(self):
        results = [
            _make_result("https://example.com/page", title="Short"),
            _make_result("https://example.com/page", title="A Much Longer Title"),
        ]
        deduped = dedupe_results(results)
        assert len(deduped) == 1
        assert deduped[0].title == "A Much Longer Title"

    def test_utm_params_cause_dedup(self):
        results = [
            _make_result("https://example.com/article?utm_source=google", title="From Google"),
            _make_result("https://example.com/article?utm_source=twitter", title="From Twitter Longer"),
        ]
        deduped = dedupe_results(results)
        assert len(deduped) == 1

    def test_fragment_does_not_prevent_dedup(self):
        results = [
            _make_result("https://example.com/page#intro"),
            _make_result("https://example.com/page#conclusion"),
        ]
        deduped = dedupe_results(results)
        assert len(deduped) == 1

    def test_trailing_slash_does_not_prevent_dedup(self):
        results = [
            _make_result("https://example.com/page/"),
            _make_result("https://example.com/page"),
        ]
        deduped = dedupe_results(results)
        assert len(deduped) == 1

    def test_merges_providers(self):
        results = [
            _make_result("https://example.com/page", provider=SearchSource.TAVILY),
            _make_result("https://example.com/page", provider=SearchSource.BRAVE),
        ]
        deduped = dedupe_results(results)
        assert len(deduped) == 1
        assert SearchSource.TAVILY in deduped[0].source_providers
        assert SearchSource.BRAVE in deduped[0].source_providers

    def test_merges_snippets(self):
        results = [
            _make_result("https://example.com/page", snippet="First snippet."),
            _make_result("https://example.com/page", snippet="Second snippet."),
        ]
        deduped = dedupe_results(results)
        assert "First snippet" in deduped[0].snippet
        assert "Second snippet" in deduped[0].snippet

    def test_does_not_duplicate_same_snippet(self):
        results = [
            _make_result("https://example.com/page", snippet="Same text"),
            _make_result("https://example.com/page", snippet="Same text"),
        ]
        deduped = dedupe_results(results)
        # snippet 不应重复
        assert deduped[0].snippet.count("Same text") == 1

    def test_preserves_first_non_other_source_type(self):
        results = [
            _make_result("https://example.com/page", source_type=SourceType.OTHER),
            _make_result("https://example.com/page", source_type=SourceType.ACADEMIC),
        ]
        deduped = dedupe_results(results)
        assert deduped[0].source_type == SourceType.ACADEMIC

    def test_preserves_first_published_at(self):
        dt = datetime(2024, 6, 15, tzinfo=UTC)
        results = [
            _make_result("https://example.com/page", published_at=None),
            _make_result("https://example.com/page", published_at=dt),
        ]
        deduped = dedupe_results(results)
        assert deduped[0].published_at is not None
        assert "2024" in deduped[0].published_at

    def test_preserves_order(self):
        results = [
            _make_result("https://first.com"),
            _make_result("https://second.com"),
            _make_result("https://third.com"),
        ]
        deduped = dedupe_results(results)
        assert deduped[0].url == "https://first.com"
        assert deduped[2].url == "https://third.com"

    def test_returns_deduped_source_candidate_type(self):
        results = [_make_result("https://example.com")]
        deduped = dedupe_results(results)
        assert isinstance(deduped[0], DedupedSourceCandidate)

    def test_empty_input(self):
        assert dedupe_results([]) == []


# === Helper Function Tests ===


class TestSelectBetterTitle:
    def test_selects_longer(self):
        assert _select_better_title("Short", "A Much Longer Title") == "A Much Longer Title"

    def test_keeps_existing_if_same_length(self):
        assert _select_better_title("AAAA", "BBBB") == "AAAA"

    def test_handles_empty_existing(self):
        assert _select_better_title("", "New") == "New"

    def test_handles_empty_new(self):
        assert _select_better_title("Existing", "") == "Existing"


class TestMergeSnippets:
    def test_merges_different(self):
        result = _merge_snippets("First", "Second")
        assert "First" in result
        assert "Second" in result

    def test_skips_contained(self):
        result = _merge_snippets("Full sentence here", "sentence")
        assert result == "Full sentence here"

    def test_replaces_with_superset(self):
        result = _merge_snippets("short", "short and more")
        assert result == "short and more"

    def test_handles_empty(self):
        assert _merge_snippets("", "New") == "New"
        assert _merge_snippets("Existing", "") == "Existing"
