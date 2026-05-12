"""任务队列路由测试。"""

import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建测试客户端。"""
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_queue():
    """每个测试前重置队列。"""
    from services.task_queue_service import reset_queue_repo, reset_queue_service, get_queue_repo
    reset_queue_service()
    reset_queue_repo()
    # 确保新的 repo 是空的
    repo = get_queue_repo()
    repo._items = []
    yield
    reset_queue_service()
    reset_queue_repo()


class TestGetQueueStatus:
    """GET /tasks/queue 测试。"""

    def test_returns_queue_structure(self, client):
        """返回 running/queued/completed/failed 结构。"""
        r = client.get("/research/tasks/queue")
        assert r.status_code == 200
        data = r.json()
        assert "running" in data
        assert "queued" in data
        assert "completed_recent" in data
        assert "failed_recent" in data
        assert "worker_running" in data

    def test_empty_queue(self, client):
        """空队列返回空列表。"""
        r = client.get("/research/tasks/queue")
        data = r.json()
        assert data["running"] is None
        assert data["queued"] == []
        assert data["total_queued"] == 0


class TestEnqueue:
    """POST /tasks/enqueue 测试。"""

    def test_enqueue_success(self, client):
        """入队成功。"""
        # 先需要有 task 存在（但 enqueue 只是加入队列，不验证 task 存在）
        r = client.post("/research/tasks/enqueue", json={
            "task_ids": ["task-001", "task-002"],
            "priority": 100,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["enqueued"] == 2
        assert len(data["items"]) == 2

    def test_enqueue_shows_in_queue(self, client):
        """入队后出现在队列中。"""
        client.post("/research/tasks/enqueue", json={
            "task_ids": ["task-001"],
        })

        r = client.get("/research/tasks/queue")
        data = r.json()
        assert data["total_queued"] == 1
        assert data["queued"][0]["task_id"] == "task-001"


class TestCancel:
    """POST /tasks/{task_id}/cancel 测试。"""

    def test_cancel_queued_task(self, client):
        """取消排队中的任务。"""
        client.post("/research/tasks/enqueue", json={"task_ids": ["task-001"]})

        r = client.post("/research/tasks/task-001/cancel")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "cancelled"

    def test_cancel_nonexistent_fails(self, client):
        """取消不存在的任务返回 400。"""
        r = client.post("/research/tasks/nonexistent/cancel")
        assert r.status_code == 400


class TestRetry:
    """POST /tasks/{task_id}/retry 测试。"""

    def test_retry_failed_task(self, client):
        """重试失败的任务。"""
        from services.task_queue_service import get_queue_service

        # 入队并标记为失败
        client.post("/research/tasks/enqueue", json={"task_ids": ["task-001"]})
        service = get_queue_service()
        item = service._repo.get_by_task_id("task-001")
        service._repo.update_status(item.id, "failed", error_message="test error")

        r = client.post("/research/tasks/task-001/retry")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "queued"

    def test_retry_queued_task_fails(self, client):
        """重试排队中的任务返回 400。"""
        client.post("/research/tasks/enqueue", json={"task_ids": ["task-001"]})

        r = client.post("/research/tasks/task-001/retry")
        assert r.status_code == 400
