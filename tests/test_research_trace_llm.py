"""Research Trace LLM 集成测试 - 验证研究流程中的 LLM trace 记录。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tracing.models import TraceStep
from app.tracing.recorder import get_recorder
from models.enums import TaskMode, TaskStatus
from models.schemas import ResearchTask


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_task():
    return ResearchTask(
        id="llm-trace-001",
        topic="Test LLM Trace",
        mode=TaskMode.AUTO,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def _setup_task_with_llm_trace(sample_task):
    """注入测试任务和模拟 LLM trace 事件。"""
    from tests.conftest_db import inject_task_to_db, remove_task_from_db
    from api.routes_research import _source_items

    inject_task_to_db(sample_task.id, sample_task.topic, status="completed")
    _source_items[sample_task.id] = []

    # 模拟 LLM plan
    recorder = get_recorder()
    recorder.record(
        task_id=sample_task.id,
        step="llm_plan_created",
        phase="planning",
        message="LLM plan: 3 enabled, 2 disabled",
        service="ResearchService",
        provider="deepseek",
        input_summary={
            "active_provider": "deepseek",
            "enabled_tasks": ["topic_understanding", "query_expansion", "entity_extraction"],
            "disabled_tasks": ["source_review", "reranking"],
            "planned_tasks": ["gossip_classification", "research_card_generation"],
            "prompt_templates_found": ["topic_understanding", "query_expansion"],
            "prompt_templates_missing": ["research_card"],
        },
    )

    # 模拟 LLM 调用
    recorder.record(
        task_id=sample_task.id,
        step=TraceStep.LLM_CALL_FINISHED,
        phase="llm",
        message="LLM call OK: topic_understanding",
        service="AIGateway",
        provider="deepseek",
        model="deepseek-chat",
        duration_ms=1800,
        output_summary={
            "task_name": "topic_understanding",
            "output_chars": 800,
            "input_chars": 1200,
        },
    )

    recorder.record(
        task_id=sample_task.id,
        step=TraceStep.LLM_CALL_FINISHED,
        phase="llm",
        message="LLM call OK: query_expansion",
        service="AIGateway",
        provider="deepseek",
        model="deepseek-chat",
        duration_ms=2200,
        output_summary={
            "task_name": "query_expansion",
            "output_chars": 1500,
            "input_chars": 2000,
        },
    )

    recorder.record(
        task_id=sample_task.id,
        step=TraceStep.TASK_COMPLETED,
        phase="processing",
        message="Research completed",
    )

    yield

    _source_items.pop(sample_task.id, None)
    recorder.clear(sample_task.id)
    from tests.conftest_db import remove_task_from_db
    remove_task_from_db(sample_task.id)


class TestTraceLLMEndpoint:
    def test_returns_llm_data(self, client, _setup_task_with_llm_trace) -> None:
        """GET /trace/llm 返回 LLM 使用数据。"""
        response = client.get("/research/tasks/llm-trace-001/trace/llm")
        assert response.status_code == 200
        data = response.json()
        assert "llm_tasks" in data
        assert "active_provider" in data
        assert "llm_call_count" in data
        assert data["llm_call_count"] == 2

    def test_used_llm_tasks_have_provider(self, client, _setup_task_with_llm_trace) -> None:
        """used_llm 状态的 task 有 provider 信息。"""
        response = client.get("/research/tasks/llm-trace-001/trace/llm")
        data = response.json()
        used_tasks = [t for t in data["llm_tasks"] if t["status"] == "used_llm"]
        assert len(used_tasks) == 2
        for t in used_tasks:
            assert t["provider"] == "deepseek"
            assert t["model"] == "deepseek-chat"

    def test_active_provider_in_response(self, client, _setup_task_with_llm_trace) -> None:
        """响应包含 active_provider。"""
        response = client.get("/research/tasks/llm-trace-001/trace/llm")
        data = response.json()
        assert data["active_provider"] is not None

    def test_disabled_tasks_shown(self, client, _setup_task_with_llm_trace) -> None:
        """disabled tasks 显示 skipped_disabled。"""
        response = client.get("/research/tasks/llm-trace-001/trace/llm")
        data = response.json()
        disabled = [t for t in data["llm_tasks"] if t["status"] == "skipped_disabled"]
        disabled_names = [t["task_name"] for t in disabled]
        assert "source_review" in disabled_names

    def test_not_implemented_tasks_shown(self, client, _setup_task_with_llm_trace) -> None:
        """not_implemented tasks 显示 skipped_not_implemented。"""
        response = client.get("/research/tasks/llm-trace-001/trace/llm")
        data = response.json()
        not_impl = [t for t in data["llm_tasks"] if t["status"] == "skipped_not_implemented"]
        not_impl_names = [t["task_name"] for t in not_impl]
        assert "gossip_classification" in not_impl_names

    def test_rule_only_steps_present(self, client, _setup_task_with_llm_trace) -> None:
        """rule_only_steps 在响应中。"""
        response = client.get("/research/tasks/llm-trace-001/trace/llm")
        data = response.json()
        assert "rule_only_steps" in data
        assert "url_dedupe" in data["rule_only_steps"]
        assert "db_save" in data["rule_only_steps"]

    def test_no_api_key_in_response(self, client, _setup_task_with_llm_trace) -> None:
        """响应不包含 API key。"""
        response = client.get("/research/tasks/llm-trace-001/trace/llm")
        text = response.text
        assert "sk-" not in text
        assert "api_key" not in text.lower() or "***" in text

    def test_task_not_found(self, client) -> None:
        response = client.get("/research/tasks/nonexistent/trace/llm")
        assert response.status_code == 404


class TestLLMPlanRecording:
    def test_llm_plan_event_exists(self, _setup_task_with_llm_trace) -> None:
        """研究流程记录 llm_plan_created 事件。"""
        recorder = get_recorder()
        events = recorder.get_events("llm-trace-001")
        plan_events = [e for e in events if e.step == "llm_plan_created"]
        assert len(plan_events) == 1
        assert plan_events[0].input_summary is not None
        assert "active_provider" in plan_events[0].input_summary
        assert "enabled_tasks" in plan_events[0].input_summary

    def test_prompt_template_info_in_plan(self, _setup_task_with_llm_trace) -> None:
        """LLM plan 包含 prompt template 信息。"""
        recorder = get_recorder()
        events = recorder.get_events("llm-trace-001")
        plan_events = [e for e in events if e.step == "llm_plan_created"]
        summary = plan_events[0].input_summary
        assert "prompt_templates_found" in summary
        assert "prompt_templates_missing" in summary
