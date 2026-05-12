"""Trace API 路由测试。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tracing.recorder import TraceRecorder, get_recorder
from app.tracing.models import TraceStep, TracePhase
from models.enums import TaskMode, TaskStatus
from models.schemas import ResearchTask


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_task():
    return ResearchTask(
        id="trace-test-001",
        topic="Test Topic",
        mode=TaskMode.AUTO,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def _setup_task_with_trace(sample_task):
    """注入测试任务和 trace 事件。"""
    from api.routes_research import _tasks, _source_items

    _tasks[sample_task.id] = {
        "task": sample_task,
        "obsidian_path": "",
    }
    _source_items[sample_task.id] = []

    # 添加 trace 事件
    recorder = get_recorder()
    recorder.info(
        sample_task.id, TraceStep.TASK_CREATED, TracePhase.PLANNING,
        message="Task created: Test Topic",
        input_summary={"topic": "Test Topic", "mode": "auto"},
    )
    recorder.info(
        sample_task.id, TraceStep.LANGUAGE_PLANNING_FINISHED, TracePhase.PLANNING,
        message="Language plan: english_first",
        output_summary={"canonical_topic": "Test Topic", "search_strategy": "english_first"},
    )
    recorder.info(
        sample_task.id, TraceStep.QUERY_EXPANSION_FINISHED, TracePhase.PLANNING,
        message="Generated 16 queries",
        service="QueryExpansionService",
        output_summary={"expanded_query_count": 16, "english_query_count": 12, "chinese_query_count": 4},
    )
    recorder.info(
        sample_task.id, TraceStep.SEARCH_PROVIDER_FINISHED, TracePhase.SEARCH,
        message="Tavily returned 50 results",
        provider="tavily",
        metrics={"duration_ms": 2500},
        output_summary={"returned_count": 50},
    )
    recorder.warning(
        sample_task.id, TraceStep.SEARCH_PROVIDER_FAILED, TracePhase.SEARCH,
        message="Google Books 429",
        provider="google_books",
        error_code="429",
        error_message="rate limited",
    )
    recorder.info(
        sample_task.id, TraceStep.DEDUPE_FINISHED, TracePhase.PROCESSING,
        message="Deduped 120 → 91",
        service="DedupeService",
        output_summary={"before_count": 120, "after_count": 91, "removed_count": 29},
    )
    recorder.info(
        sample_task.id, TraceStep.SCORING_FINISHED, TracePhase.PROCESSING,
        message="Scored 91 candidates",
        service="ScoringService",
        output_summary={"total_sources": 91, "level_counts": {"S": 3, "A": 12, "B": 44, "C": 28, "D": 4}},
    )
    recorder.info(
        sample_task.id, TraceStep.TASK_COMPLETED, TracePhase.PROCESSING,
        message="Research completed",
        metrics={"duration_ms": 15000},
    )

    yield

    _tasks.pop(sample_task.id, None)
    _source_items.pop(sample_task.id, None)
    recorder.clear(sample_task.id)


class TestGetTrace:
    def test_returns_events_list(self, client, _setup_task_with_trace) -> None:
        """GET /trace 返回事件列表。"""
        response = client.get("/research/tasks/trace-test-001/trace")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) == 8

    def test_filter_by_level(self, client, _setup_task_with_trace) -> None:
        """支持 level filter。"""
        response = client.get("/research/tasks/trace-test-001/trace", params={"level": "warning"})
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["step"] == TraceStep.SEARCH_PROVIDER_FAILED

    def test_filter_by_phase(self, client, _setup_task_with_trace) -> None:
        """支持 phase filter。"""
        response = client.get("/research/tasks/trace-test-001/trace", params={"phase": "search"})
        data = response.json()
        assert len(data["events"]) == 2  # tavily finished + google_books failed

    def test_no_api_key_in_response(self, client, _setup_task_with_trace) -> None:
        """API 返回不包含 api_key/token/secret。"""
        # 添加一个带敏感数据的事件
        recorder = get_recorder()
        recorder.info(
            "trace-test-001", TraceStep.LLM_CALL_FINISHED, TracePhase.LLM,
            provider="deepseek",
            input_summary={"api_key": "sk-secret", "model": "deepseek-chat"},
        )

        response = client.get("/research/tasks/trace-test-001/trace")
        text = response.text
        assert "sk-secret" not in text

    def test_task_not_found(self, client) -> None:
        response = client.get("/research/tasks/nonexistent/trace")
        assert response.status_code == 404


class TestGetTraceSummary:
    def test_returns_summary(self, client, _setup_task_with_trace) -> None:
        """GET /trace/summary 返回统计。"""
        response = client.get("/research/tasks/trace-test-001/trace/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 8
        assert data["warning_count"] == 1
        assert data["error_count"] == 0
        assert data["search_calls"] == 1
        assert "tavily" in data["providers_used"]
        assert "google_books" in data["providers_used"]

    def test_summary_has_source_counts(self, client, _setup_task_with_trace) -> None:
        response = client.get("/research/tasks/trace-test-001/trace/summary")
        data = response.json()
        assert data["source_counts"]["raw"] == 120
        assert data["source_counts"]["deduped"] == 91

    def test_summary_has_level_counts(self, client, _setup_task_with_trace) -> None:
        response = client.get("/research/tasks/trace-test-001/trace/summary")
        data = response.json()
        assert data["level_counts"]["S"] == 3
        assert data["level_counts"]["A"] == 12

    def test_task_not_found(self, client) -> None:
        response = client.get("/research/tasks/nonexistent/trace/summary")
        assert response.status_code == 404
