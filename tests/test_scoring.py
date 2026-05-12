"""评分服务测试。"""

import pytest

from models.enums import SearchSource, SourceLevel, SourceType
from services.dedupe_service import DedupedSourceCandidate
from services.scoring_service import score_candidate, score_candidates


def _make_candidate(
    url: str,
    title: str = "Test Title",
    snippet: str = "A reasonably long snippet with enough content to score well in relevance checks.",
    source_type: SourceType = SourceType.OTHER,
    providers: list[SearchSource] | None = None,
    published_at: str | None = "2024-06-01T00:00:00Z",
) -> DedupedSourceCandidate:
    return DedupedSourceCandidate(
        normalized_url=url,
        url=url,
        title=title,
        snippet=snippet,
        source_providers=providers or [SearchSource.TAVILY],
        source_type=source_type,
        published_at=published_at,
    )


# === 权威域名测试 ===


class TestAuthorityScoring:
    def test_sec_gov_is_S_level(self):
        c = _make_candidate(
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
            title="Tesla Inc SEC Filing 10-K",
        )
        result = score_candidate(c, topic="Tesla")
        assert result.source_level == SourceLevel.S
        assert result.authority_score >= 0.9
        assert result.category == "official"

    def test_apple_com_leadership(self):
        c = _make_candidate(
            "https://www.apple.com/leadership/",
            title="Apple Leadership - Tim Cook, CEO",
            snippet="Tim Cook is the CEO of Apple and serves on its board of directors. He leads the company's strategy and operations worldwide.",
        )
        result = score_candidate(c, topic="Apple")
        # apple.com 不在高权威列表中，但 topic 匹配加分
        # 至少应该是 C 或以上（unknown domain 限制了 authority）
        assert result.source_level in (SourceLevel.S, SourceLevel.A, SourceLevel.B, SourceLevel.C)
        assert result.relevance_score > 0.4

    def test_arxiv_is_S_or_A(self):
        c = _make_candidate(
            "https://arxiv.org/abs/2301.00001",
            title="Quantum Computing Survey",
            source_type=SourceType.ACADEMIC,
        )
        result = score_candidate(c, topic="quantum computing")
        assert result.source_level in (SourceLevel.S, SourceLevel.A)
        assert result.category == "primary_source"

    def test_nytimes_is_A_or_B(self):
        c = _make_candidate(
            "https://www.nytimes.com/2024/01/15/business/tesla-investigation.html",
            title="Tesla Under Investigation",
        )
        result = score_candidate(c, topic="Tesla")
        assert result.source_level in (SourceLevel.S, SourceLevel.A, SourceLevel.B)
        assert result.authority_score >= 0.7

    def test_edu_domain_high_authority(self):
        c = _make_candidate(
            "https://cs.stanford.edu/research/quantum",
            title="Stanford Quantum Computing Research",
        )
        result = score_candidate(c, topic="quantum computing")
        assert result.authority_score >= 0.8


# === 低质量检测 ===


class TestLowQualityDetection:
    def test_top_10_facts_title_downgrades(self):
        c = _make_candidate(
            "https://randomsite.com/top-10-facts",
            title="Top 10 Facts About Elon Musk",
        )
        result = score_candidate(c, topic="Elon Musk")
        assert result.source_level in (SourceLevel.C, SourceLevel.D)
        assert result.category == "low_quality"

    def test_net_worth_title_downgrades(self):
        c = _make_candidate(
            "https://celebnetworth.com/elon-musk",
            title="Elon Musk Net Worth 2024",
        )
        result = score_candidate(c, topic="Elon Musk")
        assert result.source_level in (SourceLevel.C, SourceLevel.D)
        assert result.category == "low_quality"

    def test_wiki_clone_downgrades(self):
        c = _make_candidate(
            "https://wikibio.in/elon-musk",
            title="Elon Musk Biography Wiki - Age, Height, Net Worth",
        )
        result = score_candidate(c, topic="Elon Musk")
        assert result.category == "low_quality"


# === 八卦评分 ===


class TestGossipScoring:
    def test_reddit_has_higher_gossip(self):
        c = _make_candidate(
            "https://www.reddit.com/r/celebrity/comments/abc",
            title="Elon Musk personal life rumors",
        )
        result = score_candidate(c, topic="Elon Musk")
        assert result.gossip_score > 0
        assert result.source_level in (SourceLevel.C, SourceLevel.D)

    def test_tmz_high_gossip(self):
        c = _make_candidate(
            "https://www.tmz.com/2024/01/scandal",
            title="Celebrity Scandal Revealed",
        )
        result = score_candidate(c, topic="celebrity")
        assert result.gossip_score >= 0.3
        assert result.category == "gossip"

    def test_academic_no_gossip(self):
        c = _make_candidate(
            "https://arxiv.org/abs/123",
            title="Research Paper on AI",
            source_type=SourceType.ACADEMIC,
        )
        result = score_candidate(c, topic="AI")
        assert result.gossip_score == 0.0


# === 图书评分 ===


class TestBookScoring:
    def test_google_books_at_least_B(self):
        c = _make_candidate(
            "https://books.google.com/books?id=abc123",
            title="Elon Musk Biography by Walter Isaacson",
            source_type=SourceType.BOOK,
            snippet="A comprehensive biography covering Elon Musk's life from childhood in South Africa to leading Tesla and SpaceX.",
        )
        result = score_candidate(c, topic="Elon Musk")
        assert result.source_level in (SourceLevel.S, SourceLevel.A, SourceLevel.B)
        assert result.category == "book"

    def test_book_source_type_classified_as_book(self):
        c = _make_candidate(
            "https://openlibrary.org/works/OL123",
            title="The Everything Store",
            source_type=SourceType.BOOK,
        )
        result = score_candidate(c, topic="Amazon")
        assert result.category == "book"


# === 分类测试 ===


class TestCategoryClassification:
    def test_interview_classified(self):
        c = _make_candidate(
            "https://www.nytimes.com/interview-with-ceo",
            title="Interview with Tim Cook on Apple's Future",
        )
        result = score_candidate(c, topic="Apple")
        assert result.category == "interview"

    def test_transcript_classified(self):
        c = _make_candidate(
            "https://www.sec.gov/transcript",
            title="Full Transcript of Senate Hearing",
        )
        result = score_candidate(c, topic="hearing")
        assert result.category in ("transcript", "official")

    def test_government_classified_as_official(self):
        c = _make_candidate(
            "https://www.fda.gov/report",
            title="FDA Safety Report",
        )
        result = score_candidate(c, topic="safety")
        assert result.category == "official"


# === 批量评分 ===


class TestScoreCandidates:
    def test_returns_sorted_by_score(self):
        candidates = [
            _make_candidate("https://randomsite.com/page", title="Random Page"),
            _make_candidate("https://arxiv.org/abs/123", title="Research Paper", source_type=SourceType.ACADEMIC),
            _make_candidate("https://celebnetworth.com/x", title="Net Worth 2024"),
        ]
        scored = score_candidates(candidates, topic="research")
        scores = [s.final_score for s in scored]
        assert scores == sorted(scores, reverse=True)

    def test_arxiv_ranks_above_random(self):
        candidates = [
            _make_candidate("https://randomsite.com/page", title="Random"),
            _make_candidate("https://arxiv.org/abs/123", title="Paper", source_type=SourceType.ACADEMIC),
        ]
        scored = score_candidates(candidates, topic="test")
        assert scored[0].candidate.url == "https://arxiv.org/abs/123"


# === reason_to_read ===


class TestReasonToRead:
    def test_reason_contains_level(self):
        c = _make_candidate("https://arxiv.org/abs/123", source_type=SourceType.ACADEMIC)
        result = score_candidate(c, topic="test")
        assert result.source_level.value in result.reason_to_read

    def test_reason_not_empty(self):
        c = _make_candidate("https://example.com/page")
        result = score_candidate(c, topic="test")
        assert len(result.reason_to_read) > 0
