"""LLM 辅助评审服务 - 增强规则评分，不替代。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.ai.schemas import SourceReviewOutput
from models.enums import SourceLevel
from services.scoring_service import ScoredCandidate, ScoringResult, score_candidate
from services.dedupe_service import DedupedSourceCandidate

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# 等级顺序（高→低）
_LEVEL_ORDER = [SourceLevel.S, SourceLevel.A, SourceLevel.B, SourceLevel.C, SourceLevel.D]

# 低质量域名黑名单（允许 LLM 大幅降级）
_LOW_QUALITY_DOMAINS = frozenset([
    "celebnetworth.com", "wikibio.in", "thefamouspeople.com",
    "biographyonline.net", "networth.com", "famousbirthdays.com",
])


class LLMScoringService:
    """LLM 辅助来源评审 - 增强规则评分结果。"""

    def __init__(self, ai_gateway: AIGateway | None = None) -> None:
        self._ai_gateway = ai_gateway

    async def score_with_review(
        self,
        candidate: DedupedSourceCandidate,
        topic: str = "",
        mode: str = "auto",
    ) -> ScoredCandidate:
        """规则评分 + LLM 辅助评审。"""
        # 1. 规则评分（主评分）
        rule_scoring = score_candidate(candidate, topic=topic, mode=mode)

        # 2. 尝试 LLM 评审
        llm_review = await self._try_llm_review(candidate, topic)

        # 3. 合并
        if llm_review is not None:
            merged = self._merge_review(rule_scoring, llm_review, candidate)
        else:
            merged = rule_scoring

        return ScoredCandidate(candidate=candidate, scoring=merged)

    async def _try_llm_review(
        self,
        candidate: DedupedSourceCandidate,
        topic: str,
    ) -> SourceReviewOutput | None:
        """尝试 LLM 评审，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        try:
            return await self._ai_gateway.run_json(
                task_name="source_review",
                payload={
                    "topic": topic,
                    "title": candidate.title,
                    "snippet": candidate.snippet,
                    "url": candidate.url,
                },
                output_schema=SourceReviewOutput,
                language="zh",
            )
        except Exception as e:
            logger.warning(
                "llm_source_review_failed url=%s error=%s",
                candidate.url, str(e),
            )
            return None

    def _merge_review(
        self,
        rule_scoring: ScoringResult,
        review: SourceReviewOutput,
        candidate: DedupedSourceCandidate,
    ) -> ScoringResult:
        """合并 LLM 评审到规则评分。"""
        # reason_to_read：优先 LLM，限制 120 字
        reason = rule_scoring.reason_to_read
        if review.reason_to_read:
            llm_reason = review.reason_to_read[:120]
            reason = llm_reason

        # source_level：规则决定，LLM 最多降一级
        level = rule_scoring.source_level
        if review.quality_warning and self._is_quality_warning(review.quality_warning):
            level = self._maybe_downgrade(level, candidate.url)

        # category：如果 LLM 有建议且规则是 general，使用 LLM
        category = rule_scoring.category
        if review.suggested_category and category == "general":
            category = review.suggested_category

        return ScoringResult(
            relevance_score=rule_scoring.relevance_score,
            authority_score=rule_scoring.authority_score,
            originality_score=rule_scoring.originality_score,
            gossip_score=rule_scoring.gossip_score,
            source_level=level,
            category=category,
            reason_to_read=reason,
        )

    def _is_quality_warning(self, warning: str) -> bool:
        """判断 quality_warning 是否明确指出 SEO/低质量。"""
        keywords = ("seo", "低质量", "low quality", "spam", "clickbait", "抄袭", "洗稿")
        warning_lower = warning.lower()
        return any(kw in warning_lower for kw in keywords)

    def _maybe_downgrade(self, level: SourceLevel, url: str) -> SourceLevel:
        """最多降一级，S/A 不允许降到 C/D（除非在黑名单）。"""
        domain = url.split("//")[-1].split("/")[0].lower()
        in_blacklist = any(d in domain for d in _LOW_QUALITY_DOMAINS)

        idx = _LEVEL_ORDER.index(level)

        if in_blacklist:
            # 黑名单域名允许降两级
            new_idx = min(idx + 2, len(_LEVEL_ORDER) - 1)
            return _LEVEL_ORDER[new_idx]

        # 非黑名单：最多降一级
        new_idx = min(idx + 1, len(_LEVEL_ORDER) - 1)
        new_level = _LEVEL_ORDER[new_idx]

        # S/A 不允许降到 C/D
        if level in (SourceLevel.S, SourceLevel.A) and new_level in (SourceLevel.C, SourceLevel.D):
            return level

        return new_level
