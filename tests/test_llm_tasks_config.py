"""LLM 任务配置加载测试。"""

import pytest

from app.ai.budget import apply_input_budget
from app.ai.tasks import (
    LLMTaskConfig,
    TaskNotFoundError,
    load_llm_task_config,
    reset_config_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_config_cache()
    yield  # type: ignore[misc]
    reset_config_cache()


class TestDefaultsMerge:
    def test_task_inherits_defaults(self) -> None:
        from core.config import get_settings
        active = get_settings().active_llm_provider

        cfg = load_llm_task_config("query_expansion")
        # task 使用 active provider（解析为当前配置的 active provider）
        assert cfg.provider == active
        # model 继承 defaults
        assert cfg.model == "qwen3:8b"
        # 从 defaults 继承
        assert cfg.timeout_seconds == 120
        assert cfg.json_required is True
        # task 自身覆盖
        assert cfg.temperature == 0.3
        assert cfg.max_input_chars == 3000
        assert cfg.max_output_tokens == 1200
        assert cfg.fallback == "rule_based_query_expansion"

    def test_task_override_takes_precedence(self) -> None:
        cfg = load_llm_task_config("entity_extraction")
        assert cfg.temperature == 0.1
        assert cfg.max_input_chars == 8000
        assert cfg.max_output_tokens == 1200
        assert cfg.fallback == "regex_entity_extraction"

    def test_all_defaults_applied_when_task_minimal(self) -> None:
        from core.config import get_settings
        active = get_settings().active_llm_provider

        cfg = load_llm_task_config("topic_understanding")
        assert cfg.provider == active
        assert cfg.model == "qwen3:8b"
        assert cfg.retry_on_parse_error is True
        assert cfg.max_retries == 1


class TestUnknownTask:
    def test_raises_task_not_found(self) -> None:
        with pytest.raises(TaskNotFoundError, match="nonexistent_task"):
            load_llm_task_config("nonexistent_task")

    def test_error_contains_task_name(self) -> None:
        try:
            load_llm_task_config("bad_name")
        except TaskNotFoundError as e:
            assert e.task_name == "bad_name"


class TestRequireLLM:
    def test_default_false(self) -> None:
        cfg = load_llm_task_config("query_expansion")
        assert cfg.require_llm is False

    def test_all_tasks_inherit_default_false(self) -> None:
        cfg = load_llm_task_config("research_card_generation")
        assert cfg.require_llm is False


class TestMaxInputChars:
    def test_topic_understanding(self) -> None:
        cfg = load_llm_task_config("topic_understanding")
        assert cfg.max_input_chars == 2000

    def test_document_summary(self) -> None:
        cfg = load_llm_task_config("document_summary")
        assert cfg.max_input_chars == 12000

    def test_default_value(self) -> None:
        # source_review 覆盖为 2500
        cfg = load_llm_task_config("source_review")
        assert cfg.max_input_chars == 2500


class TestApplyInputBudget:
    def test_short_text_unchanged(self) -> None:
        text = "short text"
        result = apply_input_budget(text, max_input_chars=100)
        assert result == text

    def test_exact_limit_unchanged(self) -> None:
        text = "a" * 100
        result = apply_input_budget(text, max_input_chars=100)
        assert result == text

    def test_truncation_applied(self) -> None:
        text = "a" * 1000
        result = apply_input_budget(text, max_input_chars=200)
        assert len(result) <= 200
        assert "[...TRUNCATED...]" in result

    def test_head_tail_ratio(self) -> None:
        text = "H" * 500 + "T" * 500
        result = apply_input_budget(text, max_input_chars=200)
        marker = "\n\n[...TRUNCATED...]\n\n"
        parts = result.split(marker)
        assert len(parts) == 2
        head, tail = parts
        usable = 200 - len(marker)
        expected_head = int(usable * 0.7)
        assert len(head) == expected_head
        assert tail == "T" * len(tail)

    def test_preserves_start_and_end(self) -> None:
        text = "START" + "x" * 990 + "END!!"
        result = apply_input_budget(text, max_input_chars=100)
        assert result.startswith("START")
        assert result.endswith("END!!")
