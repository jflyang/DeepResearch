"""ResearchLanguagePlannerService 测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.schemas import TopicUnderstandingOutput
from app.services.research_language_planner import ResearchLanguagePlannerService
from models.enums import LanguageCode, SearchStrategy, TaskMode


@pytest.fixture
def planner():
    """无 LLM 的 planner（纯规则模式）。"""
    return ResearchLanguagePlannerService(ai_gateway=None)


class TestRuleBasedPlanning:
    """规则 fallback 测试。"""

    async def test_tim_cook_chinese(self, planner):
        """库克的童年故事 → working_language=en, canonical 包含 Tim Cook。"""
        plan = await planner.plan("库克的童年故事")
        assert plan.working_language == LanguageCode.EN
        assert "Tim Cook" in plan.canonical_topic
        assert plan.main_entity_canonical == "Tim Cook"
        assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST
        assert plan.user_language == LanguageCode.ZH
        assert plan.output_language == LanguageCode.ZH

    async def test_jensen_huang(self, planner):
        """黄仁勋早期创业 → working_language=en, canonical 包含 Jensen Huang。"""
        plan = await planner.plan("黄仁勋早期创业")
        assert plan.working_language == LanguageCode.EN
        assert "Jensen Huang" in plan.canonical_topic or "NVIDIA" in plan.canonical_topic
        assert plan.main_entity_canonical == "Jensen Huang"
        assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST

    async def test_xiaomi_chinese_first(self, planner):
        """小米早期创业故事 → working_language=zh, search_strategy 不是 english_first。"""
        plan = await planner.plan("小米早期创业故事")
        assert plan.search_strategy != SearchStrategy.ENGLISH_FIRST
        assert plan.working_language in (LanguageCode.ZH, LanguageCode.MIXED)

    async def test_tesla_solarcity(self, planner):
        """Tesla 收购 SolarCity 争议 → working_language=en。"""
        plan = await planner.plan("Tesla 收购 SolarCity 争议")
        assert plan.working_language == LanguageCode.EN
        assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST

    async def test_openai_palace_drama(self, planner):
        """OpenAI 宫斗 → working_language=en。"""
        plan = await planner.plan("OpenAI 宫斗")
        assert plan.working_language == LanguageCode.EN
        assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST

    async def test_transformer_origin(self, planner):
        """Transformer 的起源 → working_language=en。"""
        plan = await planner.plan("Transformer 的起源")
        assert plan.working_language == LanguageCode.EN
        assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST

    async def test_musk_chinese(self, planner):
        """马斯克的早期创业 → working_language=en, canonical=Elon Musk。"""
        plan = await planner.plan("马斯克的早期创业")
        assert plan.working_language == LanguageCode.EN
        assert plan.main_entity_canonical == "Elon Musk"

    async def test_altman_chinese(self, planner):
        """奥特曼被解雇事件 → working_language=en, canonical=Sam Altman。"""
        plan = await planner.plan("奥特曼被解雇事件")
        assert plan.working_language == LanguageCode.EN
        assert plan.main_entity_canonical == "Sam Altman"

    async def test_pure_english_input(self, planner):
        """Pure English input → user_language=en, output_language=en。"""
        plan = await planner.plan("Steve Jobs early career at Atari")
        assert plan.user_language == LanguageCode.EN
        assert plan.output_language == LanguageCode.EN

    async def test_chinese_domestic_entity(self, planner):
        """腾讯早期发展 → chinese_first。"""
        plan = await planner.plan("腾讯早期发展")
        assert plan.search_strategy == SearchStrategy.CHINESE_FIRST
        assert plan.working_language == LanguageCode.ZH

    async def test_unknown_topic_bilingual(self, planner):
        """无法识别的主题 → bilingual。"""
        plan = await planner.plan("某个不知名的话题研究")
        assert plan.search_strategy == SearchStrategy.BILINGUAL
        assert plan.working_language == LanguageCode.MIXED

    async def test_search_languages_western(self, planner):
        """欧美实体 → search_languages 以 en 开头。"""
        plan = await planner.plan("库克的童年故事")
        assert plan.search_languages[0] == LanguageCode.EN

    async def test_search_languages_chinese(self, planner):
        """中国实体 → search_languages 以 zh 开头。"""
        plan = await planner.plan("雷军创业故事")
        assert plan.search_languages[0] == LanguageCode.ZH


class TestEmptyTopic:
    """空 topic 测试。"""

    async def test_empty_string_raises(self, planner):
        with pytest.raises(ValueError):
            await planner.plan("")

    async def test_whitespace_only_raises(self, planner):
        with pytest.raises(ValueError):
            await planner.plan("   ")


class TestLLMIntegration:
    """LLM 路径测试（mock）。"""

    async def test_llm_success_uses_result(self):
        """LLM 成功时使用 LLM 结果。"""
        mock_gateway = AsyncMock()
        mock_gateway.run_json.return_value = TopicUnderstandingOutput(
            mode="person",
            main_entity="Tim Cook",
            normalized_topic="Tim Cook childhood",
            language="zh",
            aliases=["Timothy Donald Cook", "蒂姆·库克"],
        )

        planner = ResearchLanguagePlannerService(ai_gateway=mock_gateway)
        plan = await planner.plan("库克的童年故事")

        assert plan.main_entity_canonical == "Tim Cook"
        assert plan.canonical_topic == "Tim Cook childhood"
        assert plan.working_language == LanguageCode.EN
        assert plan.confidence == 0.8
        assert "Timothy Donald Cook" in plan.aliases

    async def test_llm_failure_fallback(self):
        """LLM 失败时 fallback 仍返回可用 plan。"""
        mock_gateway = AsyncMock()
        mock_gateway.run_json.side_effect = RuntimeError("LLM unavailable")

        planner = ResearchLanguagePlannerService(ai_gateway=mock_gateway)
        plan = await planner.plan("库克的童年故事")

        # 应该 fallback 到规则版，仍然能识别库克
        assert plan.working_language == LanguageCode.EN
        assert plan.main_entity_canonical == "Tim Cook"
        assert plan.original_topic == "库克的童年故事"

    async def test_llm_none_gateway_uses_rules(self):
        """ai_gateway=None 时直接走规则。"""
        planner = ResearchLanguagePlannerService(ai_gateway=None)
        plan = await planner.plan("黄仁勋早期创业")
        assert plan.main_entity_canonical == "Jensen Huang"


class TestLanguageDetection:
    """语言检测测试。"""

    async def test_pure_chinese(self, planner):
        plan = await planner.plan("华为的早期发展历程")
        assert plan.user_language == LanguageCode.ZH

    async def test_pure_english(self, planner):
        plan = await planner.plan("Apple early history and founding")
        assert plan.user_language == LanguageCode.EN

    async def test_mixed_mostly_chinese(self, planner):
        """中文为主混合 → user_language=zh。"""
        plan = await planner.plan("库克在Apple的管理风格")
        # 中文字符多于英文
        assert plan.user_language in (LanguageCode.ZH, LanguageCode.MIXED)

    async def test_mixed_mostly_english(self, planner):
        """英文为主混合 → user_language=en 或 mixed。"""
        plan = await planner.plan("Tesla acquisition of SolarCity 争议")
        assert plan.user_language in (LanguageCode.EN, LanguageCode.MIXED)


class TestOutputLanguage:
    """输出语言决策测试。"""

    async def test_chinese_input_chinese_output(self, planner):
        plan = await planner.plan("库克的童年故事")
        assert plan.output_language == LanguageCode.ZH

    async def test_english_input_english_output(self, planner):
        plan = await planner.plan("Tim Cook childhood story")
        assert plan.output_language == LanguageCode.EN

    async def test_mixed_defaults_to_zh(self, planner):
        """混合输入默认中文输出（除非英文占绝对多数）。"""
        plan = await planner.plan("OpenAI 宫斗")
        assert plan.output_language == LanguageCode.ZH
