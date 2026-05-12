"""研究任务列表 API 测试。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from models.enums import SourceLevel, SourceType, TaskMode, TaskStatus, DownloadStatus
from models.schemas import ResearchTask, SourceItem


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def _setup_multiple_tasks():
    """注入多个测试任务。"""
    from api.routes_research import _tasks, _source_items

    # 保存现有状态
    saved_tasks = dict(_tasks)
    saved_items = dict(_source_items)
    _tasks.clear()
    _source_items.clear()

    tasks = [
        ResearchTask(id="list-t1", topic="Tim Cook 童年故事", mode=TaskMode.PERSON, status=TaskStatus.COMPLETED),
        ResearchTask(id="list-t2", topic="OpenAI 宫斗", mode=TaskMode.EVENT, status=TaskStatus.COMPLETED),
        ResearchTask(id="list-t3", topic="黄仁勋创业", mode=TaskMode.PERSON, status=TaskStatus.RUNNING),
        ResearchTask(id="list-t4", topic="Tesla 收购争议", mode=TaskMode.COMPANY, status=TaskStatus.FAILED),
    ]

    for t in tasks:
        _tasks[t.id] = {"task": t, "obsidian_path": ""}

    # 给 t1 添加 sources
    _source_items["list-t1"] = [
        SourceItem(id="s1", task_id="list-t1", url="https://a.com", source_level=SourceLevel.S, source_type=SourceType.NEWS),
        SourceItem(id="s2", task_id="list-t1", url="https://b.com", source_level=SourceLevel.A, source_type=SourceType.BOOK),
        SourceItem(id="s3", task_id="list-t1", url="https://c.com", source_level=SourceLevel.B, source_type=SourceType.BLOG),
        SourceItem(id="s4", task_id="list-t1", url="https://d.com", source_level=SourceLevel.C, source_type=SourceType.FORUM, download_status=DownloadStatus.EXTRACTED),
    ]

    # 给 t2 添加 sources
    _source_items["list-t2"] = [
        SourceItem(id="s5", task_id="list-t2", url="https://e.com", source_level=SourceLevel.A, source_type=SourceType.NEWS),
    ]

    # 标记 t2 已导出
    _tasks["list-t2"]["exported"] = True
    _tasks["list-t2"]["export_path"] = "/tmp/vault/Research/OpenAI/index.md"

    yield

    # 恢复原始状态
    _tasks.clear()
    _tasks.update(saved_tasks)
    _source_items.clear()
    _source_items.update(saved_items)


class TestListTasks:
    def test_returns_list(self, client, _setup_multiple_tasks) -> None:
        """GET /research/tasks 返回任务列表。"""
        response = client.get("/research/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 4

    def test_default_order_desc(self, client, _setup_multiple_tasks) -> None:
        """默认按 created_at desc 排序。"""
        response = client.get("/research/tasks")
        data = response.json()
        items = data["items"]
        # 后创建的在前
        dates = [i["created_at"] for i in items]
        assert dates == sorted(dates, reverse=True)

    def test_limit_offset(self, client, _setup_multiple_tasks) -> None:
        """limit/offset 分页生效。"""
        response = client.get("/research/tasks", params={"limit": 2, "offset": 0})
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 4

        response2 = client.get("/research/tasks", params={"limit": 2, "offset": 2})
        data2 = response2.json()
        assert len(data2["items"]) == 2

    def test_status_filter(self, client, _setup_multiple_tasks) -> None:
        """status filter 生效。"""
        response = client.get("/research/tasks", params={"status": "completed"})
        data = response.json()
        assert all(i["status"] == "completed" for i in data["items"])
        assert data["total"] == 2

    def test_q_search_topic(self, client, _setup_multiple_tasks) -> None:
        """q 搜索 topic 生效。"""
        response = client.get("/research/tasks", params={"q": "Cook"})
        data = response.json()
        assert data["total"] == 1
        assert "Cook" in data["items"][0]["topic"]

    def test_returns_source_count(self, client, _setup_multiple_tasks) -> None:
        """返回 source_count。"""
        response = client.get("/research/tasks")
        data = response.json()
        t1 = next(i for i in data["items"] if i["task_id"] == "list-t1")
        assert t1["source_count"] == 4
        assert t1["high_quality_count"] == 2  # S + A
        assert t1["extracted_count"] == 1

    def test_returns_export_status(self, client, _setup_multiple_tasks) -> None:
        """返回导出状态。"""
        response = client.get("/research/tasks")
        data = response.json()
        t2 = next(i for i in data["items"] if i["task_id"] == "list-t2")
        assert t2["exported"] is True
        assert t2["export_path"] is not None

    def test_does_not_return_sources_content(self, client, _setup_multiple_tasks) -> None:
        """不返回 sources 全量内容。"""
        response = client.get("/research/tasks")
        data = response.json()
        for item in data["items"]:
            assert "sources" not in item
            assert "items" not in item

    def test_empty_when_no_tasks(self, client) -> None:
        """无任务时返回空列表。"""
        from api.routes_research import _tasks
        # 保存并清空
        saved = dict(_tasks)
        _tasks.clear()
        try:
            response = client.get("/research/tasks")
            data = response.json()
            assert data["total"] == 0
            assert data["items"] == []
        finally:
            _tasks.update(saved)
