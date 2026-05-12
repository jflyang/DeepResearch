"""研究任务列表 API 测试（DB 持久化版）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from db.repositories import TaskRepository, SourceRepository
from db.session import get_session
from db.tables import TaskTable, SourceTable


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def _setup_multiple_tasks():
    """注入多个测试任务到 DB。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        src_repo = SourceRepository(session)

        repo.create_task(task_id="list-t1", topic="Tim Cook 童年故事", mode="person")
        repo.mark_completed("list-t1", source_count=4)
        repo.create_task(task_id="list-t2", topic="OpenAI 宫斗", mode="event")
        repo.mark_completed("list-t2", source_count=1)
        repo.mark_exported("list-t2", "/tmp/vault/Research/OpenAI/index.md")
        repo.create_task(task_id="list-t3", topic="黄仁勋创业", mode="person")
        repo.update_task_status("list-t3", "running")
        repo.create_task(task_id="list-t4", topic="Tesla 收购争议", mode="company")
        repo.update_task_status("list-t4", "failed")

        # 给 t1 添加 sources
        src_repo.bulk_create([
            {"id": "ls1", "task_id": "list-t1", "url": "https://a.com", "source_level": "S"},
            {"id": "ls2", "task_id": "list-t1", "url": "https://b.com", "source_level": "A"},
            {"id": "ls3", "task_id": "list-t1", "url": "https://c.com", "source_level": "B"},
            {"id": "ls4", "task_id": "list-t1", "url": "https://d.com", "source_level": "C", "download_status": "extracted"},
        ])
        src_repo.bulk_create([
            {"id": "ls5", "task_id": "list-t2", "url": "https://e.com", "source_level": "A"},
        ])
    finally:
        session.close()

    yield

    # Cleanup
    session = get_session()
    try:
        for tid in ["list-t1", "list-t2", "list-t3", "list-t4"]:
            session.query(SourceTable).filter(SourceTable.task_id == tid).delete()
            session.query(TaskTable).filter(TaskTable.id == tid).delete()
        session.commit()
    finally:
        session.close()


class TestListTasks:
    def test_returns_list(self, client, _setup_multiple_tasks) -> None:
        """GET /research/tasks 返回任务列表。"""
        response = client.get("/research/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 4

    def test_limit_offset(self, client, _setup_multiple_tasks) -> None:
        """limit/offset 分页生效。"""
        response = client.get("/research/tasks", params={"limit": 2, "offset": 0})
        data = response.json()
        assert len(data["items"]) == 2

    def test_status_filter(self, client, _setup_multiple_tasks) -> None:
        """status filter 生效。"""
        response = client.get("/research/tasks", params={"status": "completed"})
        data = response.json()
        assert all(i["status"] == "completed" for i in data["items"])
        assert data["total"] >= 2

    def test_q_search_topic(self, client, _setup_multiple_tasks) -> None:
        """q 搜索 topic 生效。"""
        response = client.get("/research/tasks", params={"q": "Cook"})
        data = response.json()
        assert data["total"] >= 1
        assert any("Cook" in i["topic"] for i in data["items"])

    def test_returns_source_count(self, client, _setup_multiple_tasks) -> None:
        """返回 source_count。"""
        response = client.get("/research/tasks")
        data = response.json()
        t1 = next((i for i in data["items"] if i["task_id"] == "list-t1"), None)
        assert t1 is not None
        assert t1["source_count"] == 4
        assert t1["high_quality_count"] == 2  # S + A
        assert t1["extracted_count"] == 1

    def test_returns_export_status(self, client, _setup_multiple_tasks) -> None:
        """返回导出状态。"""
        response = client.get("/research/tasks")
        data = response.json()
        t2 = next((i for i in data["items"] if i["task_id"] == "list-t2"), None)
        assert t2 is not None
        assert t2["exported"] is True
        assert t2["export_path"] is not None

    def test_does_not_return_sources_content(self, client, _setup_multiple_tasks) -> None:
        """不返回 sources 全量内容。"""
        response = client.get("/research/tasks")
        data = response.json()
        for item in data["items"]:
            assert "sources" not in item

    def test_task_not_found_returns_404(self, client) -> None:
        """不存在的 task 返回 404。"""
        response = client.get("/research/tasks/nonexistent-id-xyz")
        assert response.status_code == 404
