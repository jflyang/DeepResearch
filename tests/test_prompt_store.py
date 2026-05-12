"""PromptStore 单元测试。"""

from pathlib import Path

import pytest

from app.ai.prompts import PromptRenderError, PromptStore, PromptTemplateNotFound

TEMPLATE_DIR = Path("config/prompt_templates")


@pytest.fixture
def store() -> PromptStore:
    return PromptStore(template_dir=TEMPLATE_DIR)


class TestGetTemplatePath:
    def test_returns_correct_path(self, store: PromptStore) -> None:
        path = store.get_template_path("query_expansion", "zh")
        assert path == TEMPLATE_DIR / "query_expansion.zh.md"

    def test_different_language(self, store: PromptStore) -> None:
        path = store.get_template_path("topic_understanding", "en")
        assert path == TEMPLATE_DIR / "topic_understanding.en.md"


class TestRender:
    def test_topic_understanding(self, store: PromptStore) -> None:
        result = store.render("topic_understanding", "zh", {"topic": "量子计算"})
        assert "量子计算" in result
        assert "core_concepts" in result

    def test_query_expansion_with_context(self, store: PromptStore) -> None:
        result = store.render("query_expansion", "zh", {
            "topic": "深度学习",
            "context": "计算机视觉方向",
            "num_queries": 5,
        })
        assert "深度学习" in result
        assert "计算机视觉方向" in result
        assert "5" in result

    def test_query_expansion_without_context(self, store: PromptStore) -> None:
        result = store.render("query_expansion", "zh", {
            "topic": "NLP",
            "context": "",
            "num_queries": 3,
        })
        assert "NLP" in result
        # context 为空时不应显示背景行
        assert "背景" not in result

    def test_entity_extraction(self, store: PromptStore) -> None:
        result = store.render("entity_extraction", "zh", {"text": "OpenAI 发布了 GPT-4。"})
        assert "OpenAI 发布了 GPT-4" in result
        assert "entities" in result

    def test_source_review(self, store: PromptStore) -> None:
        result = store.render("source_review", "zh", {
            "topic": "机器学习",
            "title": "ML Survey",
            "snippet": "A comprehensive survey...",
            "url": "https://example.com",
        })
        assert "机器学习" in result
        assert "ML Survey" in result
        assert "https://example.com" in result

    def test_document_summary(self, store: PromptStore) -> None:
        result = store.render("document_summary", "zh", {
            "topic": "强化学习",
            "content": "本文介绍了 Q-learning 算法...",
        })
        assert "强化学习" in result
        assert "Q-learning" in result


class TestTemplateNotFound:
    def test_missing_template_raises(self, store: PromptStore) -> None:
        with pytest.raises(PromptTemplateNotFound) as exc_info:
            store.render("nonexistent_task", "zh", {})
        assert exc_info.value.task_name == "nonexistent_task"
        assert exc_info.value.language == "zh"
        assert "nonexistent_task.zh.md" in str(exc_info.value)

    def test_missing_language_raises(self, store: PromptStore) -> None:
        with pytest.raises(PromptTemplateNotFound):
            store.render("topic_understanding", "fr", {"topic": "test"})


class TestRenderError:
    def test_missing_variable_raises(self, store: PromptStore) -> None:
        with pytest.raises(PromptRenderError) as exc_info:
            store.render("topic_understanding", "zh", {})  # 缺少 topic
        assert "topic_understanding.zh.md" in exc_info.value.template_name

    def test_partial_variables_raises(self, store: PromptStore) -> None:
        with pytest.raises(PromptRenderError):
            store.render("source_review", "zh", {
                "topic": "test",
                # 缺少 title, snippet, url
            })
