"""LLM Task Registry 测试。"""

import pytest

from app.tracing.llm_registry import (
    RULE_ONLY_STEPS,
    LLMTaskInfo,
    get_all_task_info,
    get_task_info,
    _check_prompt_exists,
)


class TestGetAllTaskInfo:
    def test_contains_core_tasks(self) -> None:
        """Registry 包含核心 LLM 任务。"""
        tasks = get_all_task_info()
        names = [t.task_name for t in tasks]
        assert "topic_understanding" in names
        assert "query_expansion" in names
        assert "source_review" in names
        assert "entity_extraction" in names
        assert "document_summary" in names

    def test_contains_planned_tasks(self) -> None:
        """Registry 包含计划中的任务。"""
        tasks = get_all_task_info()
        names = [t.task_name for t in tasks]
        assert "contradiction_detection" in names
        assert "research_card_generation" in names
        assert "gossip_classification" in names

    def test_planned_task_does_not_cause_error(self) -> None:
        """planned task 不会导致错误。"""
        tasks = get_all_task_info()
        planned = [t for t in tasks if t.implementation_status == "planned"]
        assert len(planned) > 0
        # 所有 planned tasks 都有合法字段
        for t in planned:
            assert t.task_name
            assert t.stage

    def test_disabled_task_returns_disabled_status(self) -> None:
        """disabled task 返回 implementation_status=disabled。"""
        info = get_task_info("source_review")
        assert info is not None
        assert info.implementation_status == "disabled"
        assert info.enabled is False

    def test_all_tasks_have_stage(self) -> None:
        """所有任务都有 stage。"""
        tasks = get_all_task_info()
        for t in tasks:
            assert t.stage in ("planning", "scoring", "analysis", "synthesis", "export", "processing")

    def test_all_tasks_have_fallback(self) -> None:
        """所有已实现任务都有 fallback。"""
        tasks = get_all_task_info()
        implemented = [t for t in tasks if t.implemented]
        for t in implemented:
            assert t.fallback, f"{t.task_name} missing fallback"


class TestGetTaskInfo:
    def test_existing_task(self) -> None:
        info = get_task_info("query_expansion")
        assert info is not None
        assert info.task_name == "query_expansion"
        assert info.stage == "planning"
        assert info.prompt_template == "query_expansion.zh.md"

    def test_nonexistent_task(self) -> None:
        info = get_task_info("nonexistent_task")
        assert info is None


class TestPromptTemplateExists:
    def test_existing_template(self) -> None:
        """已有 prompt 模板能被识别。"""
        assert _check_prompt_exists("topic_understanding.zh.md") is True
        assert _check_prompt_exists("query_expansion.zh.md") is True
        assert _check_prompt_exists("document_summary.zh.md") is True

    def test_missing_template(self) -> None:
        """缺失的 prompt 模板能被识别。"""
        assert _check_prompt_exists("contradiction_detection.zh.md") is False
        assert _check_prompt_exists("research_card.zh.md") is False
        assert _check_prompt_exists("final_index.zh.md") is False

    def test_empty_template_name(self) -> None:
        assert _check_prompt_exists("") is False


class TestRuleOnlySteps:
    def test_contains_expected_steps(self) -> None:
        assert "url_normalize" in RULE_ONLY_STEPS
        assert "url_dedupe" in RULE_ONLY_STEPS
        assert "db_save" in RULE_ONLY_STEPS
        assert "vault_write" in RULE_ONLY_STEPS
