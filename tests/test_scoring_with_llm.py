"""LLM 辅助评审测试。"""

from unittest.mock import AsyncMock

import pytest

from app.ai.errors import LLMFallbackRequired
from app.ai.schemas import Confidence, SourceReviewOutput
from app.services.scoring_service import LLMScoringService
from models.enums import SearchSource, SourceLevel, SourceType
from services.dedupe_service import DedupedSourceCandidate


def _make_candidate(
    url: str,
    title: str = "Test Title",
    snippet: str = "A reasonably long snippet with enough content to score well.",
    source_type: SourceType = SourceType.OTHER,
) -> DedupedSourceCandidate:
    return DedupedSourceCandidate(
        normalized_url=url,
        url=url,
        title=title,
        snippet=snippet,
        source_providers=[SearchSource.TAVILY],
        source_type=source_type,
        published_at="2024-06-01T00:00:00Z",
    )


@pytest.fixture
def mock_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_gateway: AsyncMock) -> LLMScoringService:
    return LLMScoringService(ai_gateway=mock_gateway)


@pytest.fixture
def service_no_llm() -> LLMScoringService:
    return LLMScoringService(ai_gateway=None)


# === LLM 成功更新 reason_to_read ===


class TestLLMReasonToRead:
    @pytest.mark.asyncio
    async def test_llm_reason_used(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=SourceReviewOutput(
            relevance_note="高度相关",
            reason_to_read="这是一篇核心论文，详细阐述了量子计算的最新进展",
            confidence=Confidence.high,
        ))

        candidate = _make_candidate("https://arxiv.org/abs/123", title="Quantum Paper", source_type=SourceType.ACADEMIC)
        result = await service.score_with_review(candidate, topic="quantum computing")
        assert "核心论文" in result.scoring.reason_to_read

    @pytest.mark.asyncio
    async def test_reason_truncated_to_120(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        long_reason = "这是一个非常长的理由" * 20  # 超过 120 字
        mock_gateway.run_json = AsyncMock(return_value=SourceReviewOutput(
            reason_to_read=long_reason,
            confidence=Confidence.medium,
        ))

        candidate = _make_candidate("https://example.com/page")
        result = await service.score_with_review(candidate, topic="test")
        assert len(result.scoring.reason_to_read) <= 120


# === LLM warning 可降一级 ===


class TestQualityWarningDowngrade:
    @pytest.mark.asyncio
    async def test_seo_warning_downgrades_one_level(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=SourceReviewOutput(
            quality_warning="SEO spam content, low quality aggregation",
            confidence=Confidence.high,
        ))

        # B 级来源
        candidate = _make_candidate(
            "https://randomsite.com/article",
            title="Some Article About Topic",
            snippet="A" * 200,
        )
        result_no_llm = await LLMScoringService(ai_gateway=None).score_with_review(candidate, topic="Topic")
        original_level = result_no_llm.scoring.source_level

        result = await service.score_with_review(candidate, topic="Topic")

        # 应该降了一级
        level_order = [SourceLevel.S, SourceLevel.A, SourceLevel.B, SourceLevel.C, SourceLevel.D]
        if original_level != SourceLevel.D:
            orig_idx = level_order.index(original_level)
            new_idx = level_order.index(result.scoring.source_level)
            assert new_idx == orig_idx + 1

    @pytest.mark.asyncio
    async def test_non_quality_warning_no_downgrade(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=SourceReviewOutput(
            quality_warning="Content is slightly outdated",
            confidence=Confidence.medium,
        ))

        candidate = _make_candidate("https://example.com/page", snippet="A" * 200)
        result_no_llm = await LLMScoringService(ai_gateway=None).score_with_review(candidate, topic="test")
        result = await service.score_with_review(candidate, topic="test")

        # 非 SEO/低质量 warning 不降级
        assert result.scoring.source_level == result_no_llm.scoring.source_level


# === S 级来源不会被随意降到 C ===


class TestHighLevelProtection:
    @pytest.mark.asyncio
    async def test_s_level_not_dropped_to_c(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=SourceReviewOutput(
            quality_warning="SEO low quality content detected",
            confidence=Confidence.high,
        ))

        # SEC.gov 是 S 级
        candidate = _make_candidate(
            "https://www.sec.gov/filing/10-K",
            title="Tesla SEC Filing",
        )
        result = await service.score_with_review(candidate, topic="Tesla")
        # S 级最多降到 A，不会到 C/D
        assert result.scoring.source_level in (SourceLevel.S, SourceLevel.A)

    @pytest.mark.asyncio
    async def test_a_level_not_dropped_to_d(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=SourceReviewOutput(
            quality_warning="low quality aggregation",
            confidence=Confidence.high,
        ))

        # arxiv 是 S/A 级
        candidate = _make_candidate(
            "https://arxiv.org/abs/2301.00001",
            title="Research Paper",
            source_type=SourceType.ACADEMIC,
        )
        result = await service.score_with_review(candidate, topic="research")
        assert result.scoring.source_level in (SourceLevel.S, SourceLevel.A, SourceLevel.B)
        assert result.scoring.source_level != SourceLevel.D

    @pytest.mark.asyncio
    async def test_blacklist_domain_can_drop_further(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(return_value=SourceReviewOutput(
            quality_warning="SEO spam",
            confidence=Confidence.high,
        ))

        candidate = _make_candidate(
            "https://celebnetworth.com/person",
            title="Person Net Worth",
        )
        result = await service.score_with_review(candidate, topic="person")
        # 黑名单域名允许更大降级
        assert result.scoring.source_level in (SourceLevel.C, SourceLevel.D)


# === LLM 失败不影响规则评分 ===


class TestLLMFailureFallback:
    @pytest.mark.asyncio
    async def test_exception_returns_rule_scoring(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=LLMFallbackRequired(
            task="source_review", reason="parse failed"
        ))

        candidate = _make_candidate("https://arxiv.org/abs/123", source_type=SourceType.ACADEMIC)
        result = await service.score_with_review(candidate, topic="test")

        # 应该和无 LLM 时一样
        result_no_llm = await LLMScoringService(ai_gateway=None).score_with_review(candidate, topic="test")
        assert result.scoring.source_level == result_no_llm.scoring.source_level
        assert result.scoring.reason_to_read == result_no_llm.scoring.reason_to_read

    @pytest.mark.asyncio
    async def test_runtime_error_returns_rule_scoring(self, service: LLMScoringService, mock_gateway: AsyncMock) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=RuntimeError("connection refused"))

        candidate = _make_candidate("https://nytimes.com/article", title="News Article")
        result = await service.score_with_review(candidate, topic="news")

        result_no_llm = await LLMScoringService(ai_gateway=None).score_with_review(candidate, topic="news")
        assert result.scoring.source_level == result_no_llm.scoring.source_level

    @pytest.mark.asyncio
    async def test_no_gateway_uses_pure_rules(self, service_no_llm: LLMScoringService) -> None:
        candidate = _make_candidate("https://example.com/page")
        result = await service_no_llm.score_with_review(candidate, topic="test")
        assert result.scoring is not None
        assert result.scoring.source_level is not None
