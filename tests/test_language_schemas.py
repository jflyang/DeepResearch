"""Research Language Planning schema 和 enum 测试。"""

import pytest
from pydantic import ValidationError

from models.enums import LanguageCode, SearchStrategy
from models.schemas import ExpandedQuery, ResearchLanguagePlan, SourceHint


class TestLanguageCode:
    def test_valid_values(self):
        assert LanguageCode.ZH == "zh"
        assert LanguageCode.EN == "en"
        assert LanguageCode.MIXED == "mixed"
        assert LanguageCode.UNKNOWN == "unknown"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            LanguageCode("japanese")


class TestSearchStrategy:
    def test_valid_values(self):
        assert SearchStrategy.ENGLISH_FIRST == "english_first"
        assert SearchStrategy.CHINESE_FIRST == "chinese_first"
        assert SearchStrategy.BILINGUAL == "bilingual"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            SearchStrategy("random_strategy")


class TestResearchLanguagePlan:
    def test_minimal_creation(self):
        plan = ResearchLanguagePlan(original_topic="库克的童年故事")
        assert plan.original_topic == "库克的童年故事"
        assert plan.user_language == LanguageCode.ZH
        assert plan.working_language == LanguageCode.EN
        assert plan.output_language == LanguageCode.ZH
        assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST

    def test_defaults_empty_lists(self):
        plan = ResearchLanguagePlan(original_topic="test")
        assert plan.aliases == []
        assert plan.search_languages == []

    def test_full_creation(self):
        plan = ResearchLanguagePlan(
            user_language=LanguageCode.ZH,
            working_language=LanguageCode.EN,
            output_language=LanguageCode.ZH,
            original_topic="库克的童年故事",
            canonical_topic="Tim Cook childhood story",
            main_entity_original="库克",
            main_entity_canonical="Tim Cook",
            aliases=["Timothy Donald Cook", "蒂姆·库克"],
            search_languages=[LanguageCode.EN, LanguageCode.ZH],
            search_strategy=SearchStrategy.ENGLISH_FIRST,
            translation_notes="库克 → Tim Cook (Apple CEO), not James Cook",
            confidence=0.9,
        )
        assert plan.canonical_topic == "Tim Cook childhood story"
        assert plan.main_entity_canonical == "Tim Cook"
        assert len(plan.aliases) == 2
        assert plan.search_languages == [LanguageCode.EN, LanguageCode.ZH]
        assert plan.confidence == 0.9

    def test_confidence_bounds_lower(self):
        with pytest.raises(ValidationError):
            ResearchLanguagePlan(original_topic="test", confidence=-0.1)

    def test_confidence_bounds_upper(self):
        with pytest.raises(ValidationError):
            ResearchLanguagePlan(original_topic="test", confidence=1.1)

    def test_confidence_at_boundaries(self):
        plan_zero = ResearchLanguagePlan(original_topic="test", confidence=0.0)
        assert plan_zero.confidence == 0.0
        plan_one = ResearchLanguagePlan(original_topic="test", confidence=1.0)
        assert plan_one.confidence == 1.0

    def test_optional_fields_none(self):
        plan = ResearchLanguagePlan(original_topic="test")
        assert plan.main_entity_original is None
        assert plan.main_entity_canonical is None
        assert plan.translation_notes is None


class TestExpandedQuery:
    def test_minimal_creation(self):
        q = ExpandedQuery(query="Tim Cook childhood Robertsville Alabama")
        assert q.query == "Tim Cook childhood Robertsville Alabama"
        assert q.language == LanguageCode.EN
        assert q.source_hint == SourceHint.GENERAL
        assert q.priority == 5
        assert q.round == 1

    def test_with_language_en(self):
        q = ExpandedQuery(
            query="Tim Cook early life",
            language=LanguageCode.EN,
            canonical_entity="Tim Cook",
            original_user_term="库克",
        )
        assert q.language == LanguageCode.EN
        assert q.canonical_entity == "Tim Cook"
        assert q.original_user_term == "库克"

    def test_with_language_zh(self):
        q = ExpandedQuery(
            query="库克 苹果 早期经历",
            language=LanguageCode.ZH,
            purpose="中文补充搜索",
        )
        assert q.language == LanguageCode.ZH
        assert q.purpose == "中文补充搜索"

    def test_source_hint_values(self):
        for hint in SourceHint:
            q = ExpandedQuery(query="test", source_hint=hint)
            assert q.source_hint == hint

    def test_priority_bounds(self):
        with pytest.raises(ValidationError):
            ExpandedQuery(query="test", priority=0)
        with pytest.raises(ValidationError):
            ExpandedQuery(query="test", priority=11)

    def test_priority_at_boundaries(self):
        q_low = ExpandedQuery(query="test", priority=1)
        assert q_low.priority == 1
        q_high = ExpandedQuery(query="test", priority=10)
        assert q_high.priority == 10

    def test_optional_fields_none(self):
        q = ExpandedQuery(query="test")
        assert q.canonical_entity is None
        assert q.original_user_term is None
