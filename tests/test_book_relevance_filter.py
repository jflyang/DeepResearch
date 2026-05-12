"""图书相关性过滤测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.book_relevance_service import (
    BookRelevanceResult,
    BookRelevanceService,
    rule_based_book_relevance,
)


class TestRuleBasedBookRelevance:
    """规则兜底过滤测试。"""

    def test_python_nlp_cookbook_filtered(self):
        """Tim Cook topic 下，Python Natural Language Processing Cookbook 被过滤。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Python Natural Language Processing Cookbook",
            authors="Zhenya Antić",
            snippet="Over 50 recipes to understand, analyze, and generate text",
        )
        assert not result.is_relevant
        assert result.relevance_level == "irrelevant"

    def test_jamie_oliver_filtered(self):
        """Jamie Oliver 被过滤。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Jamie Oliver's Comfort Food",
            authors="Jamie Oliver",
            snippet="The ultimate weekend cookbook",
        )
        assert not result.is_relevant
        assert result.relevance_level == "irrelevant"

    def test_julius_caesar_filtered(self):
        """Julius Caesar 被过滤。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Julius Caesar: Life of a Colossus",
            authors="Adrian Goldsworthy",
            snippet="A biography of the Roman dictator",
        )
        assert not result.is_relevant
        assert result.relevance_level == "irrelevant"

    def test_bible_filtered(self):
        """Bible 被过滤。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="The Bible: King James Version",
            authors="",
            snippet="Complete text of the King James Bible",
        )
        assert not result.is_relevant
        assert result.relevance_level == "irrelevant"

    def test_gourmet_cooking_filtered(self):
        """Gourmet cooking for dummies 被过滤。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Gourmet Cooking for Dummies",
            authors="Charlie Trotter",
            snippet="Learn to cook gourmet meals at home",
        )
        assert not result.is_relevant
        assert result.relevance_level == "irrelevant"

    def test_tim_cook_biography_kept(self):
        """Tim Cook biography 保留。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Tim Cook: The Genius Who Took Apple to the Next Level",
            authors="Leander Kahney",
            snippet="A biography of Apple CEO Tim Cook",
        )
        assert result.is_relevant
        assert result.relevance_level == "high"

    def test_apple_leadership_book_kept(self):
        """Apple leadership book 保留。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Inside Apple: How America's Most Admired Company Really Works",
            authors="Adam Lashinsky",
            snippet="An inside look at Apple's leadership and culture",
        )
        assert result.is_relevant

    def test_cook_without_tim_filtered(self):
        """标题只有 Cook 但不是 Tim Cook，不得判为相关。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Cook's Illustrated Cookbook",
            authors="America's Test Kitchen",
            snippet="2000 recipes from 20 years of America's most trusted food magazine",
        )
        assert not result.is_relevant

    def test_tim_without_cook_filtered(self):
        """标题只有 Tim 但不是 Tim Cook，不得判为相关。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="The Life and Times of Tim",
            authors="Unknown Author",
            snippet="A fictional story about a man named Tim",
        )
        assert not result.is_relevant

    def test_steve_jobs_book_kept(self):
        """Steve Jobs 相关书保留（与 Tim Cook 研究相关）。"""
        result = rule_based_book_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Steve Jobs",
            authors="Walter Isaacson",
            snippet="The exclusive biography of Steve Jobs",
        )
        assert result.is_relevant

    def test_rule_fallback_works_without_llm(self):
        """规则 fallback 无 LLM 时可用。"""
        # 直接调用规则函数，不需要 LLM
        result = rule_based_book_relevance(
            topic="Tim Cook",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Chocolate Cookbook Deluxe",
            authors="Chef Someone",
            snippet="Delicious chocolate recipes",
        )
        assert not result.is_relevant
        # 确认返回了有效的 BookRelevanceResult
        assert isinstance(result, BookRelevanceResult)
        assert result.relevance_level == "irrelevant"


class TestBookRelevanceService:
    """BookRelevanceService 集成测试。"""

    @pytest.mark.asyncio
    async def test_irrelevant_book_skips_llm(self):
        """明显不相关的图书不调用 LLM。"""
        mock_gateway = MagicMock()
        mock_gateway.run_json = AsyncMock()

        service = BookRelevanceService(ai_gateway=mock_gateway)
        result = await service.check_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Python Natural Language Processing Cookbook",
            authors="Zhenya Antić",
        )

        assert not result.is_relevant
        # LLM 不应被调用
        mock_gateway.run_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_relevant_book_calls_llm(self):
        """可能相关的图书调用 LLM 确认。"""
        mock_gateway = MagicMock()
        mock_gateway.run_json = AsyncMock(return_value=BookRelevanceResult(
            is_relevant=True,
            relevance_level="high",
            book_title_zh="蒂姆·库克传",
            book_type="biography",
            why_relevant="直接以 Tim Cook 为主题的传记",
            likely_contains=["童年经历", "Auburn University"],
        ))

        service = BookRelevanceService(ai_gateway=mock_gateway)
        result = await service.check_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Tim Cook: The Genius Who Took Apple to the Next Level",
            authors="Leander Kahney",
        )

        assert result.is_relevant
        assert result.book_title_zh == "蒂姆·库克传"
        mock_gateway.run_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_rules(self):
        """LLM 失败时使用规则兜底。"""
        mock_gateway = MagicMock()
        mock_gateway.run_json = AsyncMock(side_effect=Exception("API error"))

        service = BookRelevanceService(ai_gateway=mock_gateway)
        result = await service.check_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Tim Cook: The Genius Who Took Apple to the Next Level",
            authors="Leander Kahney",
        )

        # 规则判断应该通过（标题包含 Tim Cook）
        assert result.is_relevant

    @pytest.mark.asyncio
    async def test_no_gateway_uses_rules(self):
        """没有 AI Gateway 时使用规则。"""
        service = BookRelevanceService(ai_gateway=None)
        result = await service.check_relevance(
            topic="Tim Cook 童年故事",
            canonical_topic="Tim Cook",
            main_entity="Tim Cook",
            book_title="Gourmet Cooking for Dummies",
        )

        assert not result.is_relevant
