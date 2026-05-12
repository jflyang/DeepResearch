"""topic_understanding.zh.md prompt 模板内容测试。

验证 prompt 模板包含研究语言规划所需的关键指令和字段。
"""

from pathlib import Path

import pytest

from app.ai.prompts import PromptStore

TEMPLATE_DIR = Path("config/prompt_templates")


@pytest.fixture
def rendered_prompt() -> str:
    """渲染一个典型中文主题的 prompt。"""
    store = PromptStore(template_dir=TEMPLATE_DIR)
    return store.render("topic_understanding", "zh", {"topic": "库克的童年故事"})


@pytest.fixture
def store() -> PromptStore:
    return PromptStore(template_dir=TEMPLATE_DIR)


class TestPromptContainsLanguagePlanningFields:
    """验证 prompt 输出 schema 包含语言规划字段。"""

    def test_contains_main_entity_canonical(self, rendered_prompt):
        assert "main_entity_canonical" in rendered_prompt

    def test_contains_canonical_topic(self, rendered_prompt):
        assert "canonical_topic" in rendered_prompt

    def test_contains_working_language(self, rendered_prompt):
        assert "working_language" in rendered_prompt

    def test_contains_output_language(self, rendered_prompt):
        assert "output_language" in rendered_prompt

    def test_contains_search_strategy(self, rendered_prompt):
        assert "search_strategy" in rendered_prompt

    def test_contains_user_language(self, rendered_prompt):
        assert "user_language" in rendered_prompt

    def test_contains_translation_notes(self, rendered_prompt):
        assert "translation_notes" in rendered_prompt

    def test_contains_english_first_strategy(self, rendered_prompt):
        assert "english_first" in rendered_prompt

    def test_contains_chinese_first_strategy(self, rendered_prompt):
        assert "chinese_first" in rendered_prompt

    def test_contains_bilingual_strategy(self, rendered_prompt):
        assert "bilingual" in rendered_prompt


class TestPromptContainsEntityExamples:
    """验证 prompt 包含关键实体消歧示例。"""

    def test_tim_cook_mapping(self, rendered_prompt):
        assert "Tim Cook" in rendered_prompt

    def test_jensen_huang_mapping(self, rendered_prompt):
        assert "Jensen Huang" in rendered_prompt

    def test_nvidia_mapping(self, rendered_prompt):
        assert "NVIDIA" in rendered_prompt

    def test_sam_altman_mapping(self, rendered_prompt):
        assert "Sam Altman" in rendered_prompt

    def test_elon_musk_mapping(self, rendered_prompt):
        assert "Elon Musk" in rendered_prompt


class TestPromptContainsCoreInstructions:
    """验证 prompt 包含核心指令。"""

    def test_no_pinyin_instruction(self, rendered_prompt):
        """禁止把中文名直接音译为英文。"""
        assert "音译" in rendered_prompt or "Kuke" in rendered_prompt

    def test_user_language_not_equals_working(self, rendered_prompt):
        """说明用户语言不等于研究语言。"""
        assert "用户输入语言" in rendered_prompt or "用户语言" in rendered_prompt
        assert "研究工作语言" in rendered_prompt or "研究语言" in rendered_prompt or "工作语言" in rendered_prompt

    def test_json_only_output(self, rendered_prompt):
        """要求只输出 JSON。"""
        assert "JSON" in rendered_prompt

    def test_no_markdown_instruction(self, rendered_prompt):
        """禁止输出 markdown。"""
        assert "markdown" in rendered_prompt.lower() or "code block" in rendered_prompt.lower()

    def test_no_fabrication_instruction(self, rendered_prompt):
        """禁止编造。"""
        assert "编造" in rendered_prompt


class TestPromptRendersTopicVariable:
    """验证 topic 变量正确渲染。"""

    def test_topic_appears_in_output(self, rendered_prompt):
        assert "库克的童年故事" in rendered_prompt

    def test_different_topic_renders(self, store):
        result = store.render("topic_understanding", "zh", {"topic": "Transformer 的起源"})
        assert "Transformer 的起源" in result

    def test_english_topic_renders(self, store):
        result = store.render("topic_understanding", "zh", {"topic": "OpenAI leadership crisis"})
        assert "OpenAI leadership crisis" in result


class TestPromptOutputSchema:
    """验证输出 schema 包含所有必需字段。"""

    REQUIRED_FIELDS = [
        "mode",
        "main_entity",
        "main_entity_canonical",
        "normalized_topic",
        "canonical_topic",
        "language",
        "user_language",
        "working_language",
        "output_language",
        "search_strategy",
        "aliases",
        "people",
        "organizations",
        "places",
        "concepts",
        "suggested_focus",
        "controversy_flags",
        "research_angles",
        "translation_notes",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_schema_contains_field(self, rendered_prompt, field):
        assert f'"{field}"' in rendered_prompt
