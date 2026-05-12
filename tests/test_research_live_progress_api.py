"""研究任务实时进度 API 测试。"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """创建 FastAPI 测试客户端。"""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_pending_task():
    """创建 pending 状态的 mock task。"""
    from db.tables import TaskTable
    row = MagicMock(spec=TaskTable)
    row.id = "task-live-001"
    row.topic = "实时进度测试"
    row.canonical_topic = ""
    row.mode = "auto"
    row.status = "pending"
    row.depth = "standard"
    row.include_gossip = False
    row.include_books = True
    row.include_video = False
    row.source_count = 0
    row.exported = False
    row.export_path = ""
    row.deleted_at = None
    row.cloned_from_task_id = ""
    row.created_at = None
    row.completed_at = None
    row.expanded_queries = "[]"
    row.error_message = ""
    row.task_type = "search_research"
    return row


class TestRunEndpointNonBlocking:
    """POST /research/tasks/{task_id}/run 非阻塞测试。"""

    def test_run_returns_immediately_with_running(self, test_client, mock_pending_task):
        """run 应立即返回 running 状态，不阻塞到 completed。"""
        with patch("db.repositories.TaskRepository.get_task", return_value=mock_pending_task):
            with patch("db.repositories.TaskRepository.update_task_status"):
                # 不 mock _run_research_background，让它被 create_task 调度
                # 但由于 TestClient 是同步的，background task 不会真正执行
                response = test_client.post(f"/research/tasks/{mock_pending_task.id}/run")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["task_id"] == mock_pending_task.id
        assert "已启动" in data["message"]

    def test_run_not_found(self, test_client):
        """不存在的任务返回 404。"""
        with patch("db.repositories.TaskRepository.get_task", return_value=None):
            response = test_client.post("/research/tasks/nonexistent/run")
        assert response.status_code == 404

    def test_run_already_running(self, test_client, mock_pending_task):
        """已在运行的任务返回 400。"""
        mock_pending_task.status = "running"
        with patch("db.repositories.TaskRepository.get_task", return_value=mock_pending_task):
            response = test_client.post(f"/research/tasks/{mock_pending_task.id}/run")
        assert response.status_code == 400


class TestTraceSummaryProgress:
    """Trace summary 进度信息测试。"""

    def test_summary_includes_current_step(self, test_client, mock_pending_task):
        """trace summary 应包含 current_step。"""
        from app.tracing.recorder import get_recorder
        from app.tracing.models import TraceStep, TracePhase

        recorder = get_recorder()
        task_id = "task-progress-001"

        # 模拟一些事件
        recorder.info(task_id, TraceStep.TASK_CREATED, TracePhase.PLANNING, message="Created")
        recorder.info(task_id, TraceStep.LANGUAGE_PLANNING_FINISHED, TracePhase.PLANNING, message="Done")
        recorder.info(task_id, TraceStep.QUERY_EXPANSION_FINISHED, TracePhase.PLANNING, message="24 queries")

        mock_pending_task.id = task_id
        mock_pending_task.status = "running"

        with patch("db.repositories.TaskRepository.get_task", return_value=mock_pending_task):
            response = test_client.get(f"/research/tasks/{task_id}/trace/summary")

        assert response.status_code == 200
        data = response.json()
        assert "current_step" in data
        assert data["current_step"] == "query_expansion"
        assert "progress_percent" in data
        assert data["progress_percent"] >= 30

        # 清理
        recorder.clear(task_id)

    def test_summary_progress_increases(self, test_client, mock_pending_task):
        """进度应随事件增加。"""
        from app.tracing.recorder import get_recorder
        from app.tracing.models import TraceStep, TracePhase

        recorder = get_recorder()
        task_id = "task-progress-002"

        # 初始状态
        recorder.info(task_id, TraceStep.TASK_CREATED, TracePhase.PLANNING)
        summary1 = recorder.get_summary(task_id)
        p1 = summary1.get("progress_percent", 0)

        # 搜索完成后
        recorder.info(task_id, TraceStep.LANGUAGE_PLANNING_FINISHED, TracePhase.PLANNING)
        recorder.info(task_id, TraceStep.QUERY_EXPANSION_FINISHED, TracePhase.PLANNING)
        recorder.info(task_id, TraceStep.SEARCH_PROVIDER_FINISHED, TracePhase.SEARCH)
        summary2 = recorder.get_summary(task_id)
        p2 = summary2.get("progress_percent", 0)

        # 完成后
        recorder.info(task_id, TraceStep.DEDUPE_FINISHED, TracePhase.PROCESSING)
        recorder.info(task_id, TraceStep.SCORING_FINISHED, TracePhase.PROCESSING)
        recorder.info(task_id, TraceStep.TASK_COMPLETED, TracePhase.PROCESSING)
        summary3 = recorder.get_summary(task_id)
        p3 = summary3.get("progress_percent", 0)

        assert p1 < p2 < p3
        assert p3 == 100

        # 清理
        recorder.clear(task_id)


class TestTraceNoSecrets:
    """Trace API 不应返回敏感信息。"""

    def test_trace_events_no_api_key(self, test_client, mock_pending_task):
        """trace 事件不应包含 API key。"""
        from app.tracing.recorder import get_recorder
        from app.tracing.models import TracePhase

        recorder = get_recorder()
        task_id = "task-secret-001"

        # 模拟包含敏感信息的事件（recorder 应自动脱敏）
        recorder.info(
            task_id, "test_step", TracePhase.PLANNING,
            input_summary={"api_key": "sk-12345", "query": "test"},
        )

        mock_pending_task.id = task_id
        with patch("db.repositories.TaskRepository.get_task", return_value=mock_pending_task):
            response = test_client.get(f"/research/tasks/{task_id}/trace")

        assert response.status_code == 200
        data = response.json()
        events = data.get("events", [])
        assert len(events) > 0

        # 检查脱敏
        for event in events:
            input_summary = event.get("input_summary") or {}
            if "api_key" in input_summary:
                assert input_summary["api_key"] == "***"

        # 清理
        recorder.clear(task_id)


class TestTaskFailedState:
    """任务失败状态测试。"""

    def test_failed_task_has_error_in_trace(self, test_client, mock_pending_task):
        """失败任务的 trace 应包含 task_failed 事件。"""
        from app.tracing.recorder import get_recorder
        from app.tracing.models import TraceStep, TracePhase

        recorder = get_recorder()
        task_id = "task-failed-001"

        recorder.info(task_id, TraceStep.TASK_CREATED, TracePhase.PLANNING)
        recorder.error(
            task_id, TraceStep.TASK_FAILED, TracePhase.PROCESSING,
            message="Research failed: timeout",
            error_message="Connection timeout after 30s",
        )

        mock_pending_task.id = task_id
        mock_pending_task.status = "failed"

        with patch("db.repositories.TaskRepository.get_task", return_value=mock_pending_task):
            response = test_client.get(f"/research/tasks/{task_id}/trace")

        assert response.status_code == 200
        data = response.json()
        events = data.get("events", [])
        steps = [e["step"] for e in events]
        assert TraceStep.TASK_FAILED in steps

        # 清理
        recorder.clear(task_id)
