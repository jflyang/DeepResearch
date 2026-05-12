"""QueryExpansionService 语言规划支持测试。"""

from unittest.mock import AsyncMock

import pytest

from models.enums import LanguageCode, SearchStrategy, TaskMode
from models.schemas import ExpandedQuery as RichExpandedQuery
from models.schemas import ResearchLanguagePlan
from services.query_expansion_service import QueryExpansionService


@pytest.fixture
def service():
    """无 LLM 的 service。"""
    return QueryExpansionService(ai_gateway=None)


def _make_plan(
    original_topic: str = "库克的童年故事",
    canonical_topic: str = "Tim Cook childhood story",
    main_entity_original: str = "库克",
    main_entity_canonical: str = "Tim Cook",
    search_strategy: SearchStrategy = SearchStrategy.ENGLISH_FIRST,
    **kwargs,
) -> ResearchLanguagePlan:
    """创建测试用 ResearchLanguagePlan。"""
    defaults = {
        "user_language": LanguageCode.ZH,
        "working_language": LanguageCode.EN,
        "output_language": LanguageCode.ZH,
        "original_topic": original_topic,
        "canonical_topic": canonical_topic,
        "main_entity_original": main_entity_original,
        "main_entity_canonical": main_entity_canonical,
        "search_strategy": search_strategy,
        "search_languages": [LanguageCode.EN, LanguageCode.ZH],
        "confidence": 0.7,
    }
    defaults.update(kwargs)
    return ResearchLanguagePlan(**defaults)


class TestEnglishFirst:
    """search_strategy=english_first 测试。"""

    async def test_english_queries_more_than_chinese(self, service):
        """英文 query 数量多于中文。"""
        plan = _make_plan(search_strategy=SearchStrategy.ENGLISH_FIRST)
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        en_count = sum(1 for q in results if q.language == LanguageCode.EN)
        zh_count = sum(1 for q in results if q.language == LanguageCode.ZH)
        assert en_count > zh_count, f"EN={en_count}, ZH={zh_count}"

    async def test_canonical_entity_is_tim_cook(self, service):
        """canonical_entity 为 Tim Cook。"""
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        for q in results:
            assert q.canonical_entity == "Tim Cook"

    async def test_english_queries_contain_canonical(self, service):
        """英文 query 使用 canonical entity。"""
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        en_queries = [q.query for q in results if q.language == LanguageCode.EN]
        assert any("Tim Cook" in q for q in en_queries)

    async def test_english_priority_higher(self, service):
        """英文 query 优先级高于中文补充 query。"""
        plan = _make_plan(search_strategy=SearchStrategy.ENGLISH_FIRST)
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        en_priorities = [q.priority for q in results if q.language == LanguageCode.EN]
        zh_priorities = [q.priority for q in results if q.language == LanguageCode.ZH]
        if en_priorities and zh_priorities:
            assert max(en_priorities) > max(zh_priorities)


class TestChineseFirst:
    """search_strategy=chinese_first 测试。"""

    async def test_chinese_queries_more_than_english(self, service):
        """中文 query 数量多于英文。"""
        plan = _make_plan(
            original_topic="小米早期创业故事",
            canonical_topic="小米早期创业故事",
            main_entity_original="小米",
            main_entity_canonical=None,
            search_strategy=SearchStrategy.CHINESE_FIRST,
            working_language=LanguageCode.ZH,
        )
        results = await service.expand(
            topic="小米早期创业故事",
            mode=TaskMode.COMPANY,
            language_plan=plan,
        )
        en_count = sum(1 for q in results if q.language == LanguageCode.EN)
        zh_count = sum(1 for q in results if q.language == LanguageCode.ZH)
        assert zh_count > en_count, f"ZH={zh_count}, EN={en_count}"

    async def test_chinese_priority_higher(self, service):
        """中文 query 优先级高于英文补充 query。"""
        plan = _make_plan(
            original_topic="小米早期创业故事",
            canonical_topic="小米早期创业故事",
            main_entity_original="小米",
            main_entity_canonical=None,
            search_strategy=SearchStrategy.CHINESE_FIRST,
            working_language=LanguageCode.ZH,
        )
        results = await service.expand(
            topic="小米早期创业故事",
            mode=TaskMode.COMPANY,
            language_plan=plan,
        )
        zh_priorities = [q.priority for q in results if q.language == LanguageCode.ZH]
        en_priorities = [q.priority for q in results if q.language == LanguageCode.EN]
        if zh_priorities and en_priorities:
            assert max(zh_priorities) > max(en_priorities)


class TestBilingual:
    """search_strategy=bilingual 测试。"""

    async def test_both_languages_present(self, service):
        """中英文都有。"""
        plan = _make_plan(
            original_topic="TikTok 禁令争议",
            canonical_topic="TikTok ban controversy",
            main_entity_original="TikTok",
            main_entity_canonical="TikTok",
            search_strategy=SearchStrategy.BILINGUAL,
            working_language=LanguageCode.MIXED,
        )
        results = await service.expand(
            topic="TikTok 禁令争议",
            mode=TaskMode.EVENT,
            language_plan=plan,
        )
        en_count = sum(1 for q in results if q.language == LanguageCode.EN)
        zh_count = sum(1 for q in results if q.language == LanguageCode.ZH)
        assert en_count > 0, "Should have English queries"
        assert zh_count > 0, "Should have Chinese queries"


class TestLLMFallback:
    """LLM 失败时仍生成规则 query。"""

    async def test_llm_failure_still_returns_queries(self):
        """LLM 失败时 fallback 仍返回可用 queries。"""
        mock_gateway = AsyncMock()
        mock_gateway.run_json.side_effect = RuntimeError("LLM unavailable")

        service = QueryExpansionService(ai_gateway=mock_gateway)
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        assert len(results) > 0
        # 仍然有英文 queries
        en_queries = [q for q in results if q.language == LanguageCode.EN]
        assert len(en_queries) > 0

    async def test_no_gateway_uses_rules(self, service):
        """ai_gateway=None 时直接走规则。"""
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        assert len(results) > 0


class TestQueryQuality:
    """query 质量测试。"""

    async def test_no_low_quality_patterns(self, service):
        """query 不包含 top 10 / facts about / overview / what is / wiki。"""
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        for q in results:
            query_lower = q.query.lower()
            assert "top 10" not in query_lower
            assert "facts about" not in query_lower
            assert "overview" not in query_lower
            assert "what is" not in query_lower
            assert "wiki" not in query_lower

    async def test_every_query_has_language(self, service):
        """每个 query 都有 language 字段。"""
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        for q in results:
            assert q.language in (LanguageCode.EN, LanguageCode.ZH, LanguageCode.MIXED)

    async def test_every_query_is_rich_type(self, service):
        """返回 RichExpandedQuery 类型。"""
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        for q in results:
            assert isinstance(q, RichExpandedQuery)


class TestBackwardCompatibility:
    """language_plan=None 时保持原有逻辑。"""

    async def test_none_plan_returns_results(self, service):
        """无 language_plan 时仍返回结果。"""
        results = await service.expand(
            topic="Elon Musk",
            mode=TaskMode.PERSON,
            language_plan=None,
        )
        assert len(results) > 0

    async def test_none_plan_returns_rich_type(self, service):
        """无 language_plan 时也返回 RichExpandedQuery。"""
        results = await service.expand(
            topic="Elon Musk",
            mode=TaskMode.PERSON,
            language_plan=None,
        )
        for q in results:
            assert isinstance(q, RichExpandedQuery)

    async def test_none_plan_has_language_field(self, service):
        """无 language_plan 时 query 也有 language 字段。"""
        results = await service.expand(
            topic="Elon Musk",
            mode=TaskMode.PERSON,
            language_plan=None,
        )
        for q in results:
            assert q.language in (LanguageCode.EN, LanguageCode.ZH, LanguageCode.MIXED)


class TestOriginalUserTerm:
    """original_user_term 追溯测试。"""

    async def test_original_user_term_populated(self, service):
        """query 包含 original_user_term。"""
        plan = _make_plan()
        results = await service.expand(
            topic="库克的童年故事",
            mode=TaskMode.PERSON,
            language_plan=plan,
        )
        for q in results:
            assert q.original_user_term == "库克"
