"""导出 API 路由测试。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from models.enums import DownloadStatus, SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ResearchTask, SourceItem


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_task():
    return ResearchTask(
        id="test-task-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sample_sources():
    return [
        SourceItem(
            id="src-1",
            task_id="test-task-001",
            title="Apple Leadership: Tim Cook",
            url="https://apple.com/leadership/tim-cook",
            domain="apple.com",
            snippet="Tim Cook is the CEO of Apple.",
            source_type=SourceType.DOCUMENTATION,
            source_level=SourceLevel.S,
            relevance_score=0.9,
            authority_score=0.95,
            reason_to_read="Official biography",
        ),
        SourceItem(
            id="src-2",
            task_id="test-task-001",
            title="Tim Cook Biography Book",
            url="https://books.example.com/tim-cook",
            domain="books.example.com",
            snippet="A comprehensive biography.",
            source_type=SourceType.BOOK,
            source_level=SourceLevel.A,
            relevance_score=0.8,
            authority_score=0.7,
            reason_to_read="Detailed biography",
        ),
        SourceItem(
            id="src-3",
            task_id="test-task-001",
            title="Rumors about Tim Cook",
            url="https://gossip.example.com/cook",
            domain="gossip.example.com",
            snippet="Unverified claims.",
            source_type=SourceType.BLOG,
            source_level=SourceLevel.C,
            gossip_score=0.6,
            reason_to_read="Gossip",
        ),
    ]


@pytest.fixture
def _setup_task(sample_task, sample_sources):
    """注入测试任务到 DB 和内存。"""
    from tests.conftest_db import inject_task_to_db, inject_sources_to_db, remove_task_from_db
    from api.routes_research import _source_items

    inject_task_to_db(sample_task.id, sample_task.topic, status="completed")
    _source_items[sample_task.id] = sample_sources

    yield

    _source_items.pop(sample_task.id, None)
    remove_task_from_db(sample_task.id)


class TestExportIndex:
    def test_vault_not_configured_returns_error(self, client, _setup_task) -> None:
        """Vault 未配置时返回明确错误。"""
        with patch("core.config._load_runtime_settings", return_value={}):
            with patch.dict("os.environ", {"OBSIDIAN_VAULT_PATH": ""}, clear=False):
                from core.config import reset_settings
                reset_settings()
                response = client.post("/research/tasks/test-task-001/export-index")
                reset_settings()

        assert response.status_code == 400
        data = response.json()
        assert "Vault" in data["detail"] or "配置" in data["detail"]

    def test_export_success_with_valid_vault(self, client, _setup_task, tmp_path) -> None:
        """Vault 配置到 tmp_path 时 export-index 成功。"""
        from db.repositories import TaskRepository
        from db.session import get_session
        session = get_session()
        TaskRepository(session).update_task_metadata("test-task-001", obsidian_path=str(tmp_path))
        session.close()

        response = client.post("/research/tasks/test-task-001/export-index")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "exported"
        assert "path" in data
        assert data["source_count"] == 3

    def test_index_file_exists_after_export(self, client, _setup_task, tmp_path) -> None:
        """成功后 index.md 文件存在。"""
        from db.repositories import TaskRepository
        from db.session import get_session
        session = get_session()
        TaskRepository(session).update_task_metadata("test-task-001", obsidian_path=str(tmp_path))
        session.close()

        response = client.post("/research/tasks/test-task-001/export-index")
        assert response.status_code == 200

        data = response.json()
        index_path = Path(data["path"])
        assert index_path.exists()

    def test_index_file_not_empty(self, client, _setup_task, tmp_path) -> None:
        """index.md 不为空。"""
        from db.repositories import TaskRepository
        from db.session import get_session
        session = get_session()
        TaskRepository(session).update_task_metadata("test-task-001", obsidian_path=str(tmp_path))
        session.close()

        client.post("/research/tasks/test-task-001/export-index")

        # 找到生成的文件
        index_files = list(tmp_path.rglob("index.md"))
        assert len(index_files) == 1
        content = index_files[0].read_text(encoding="utf-8")
        assert len(content) > 100

    def test_index_contains_source_titles(self, client, _setup_task, tmp_path) -> None:
        """index.md 包含来源标题。"""
        from db.repositories import TaskRepository
        from db.session import get_session
        session = get_session()
        TaskRepository(session).update_task_metadata("test-task-001", obsidian_path=str(tmp_path))
        session.close()

        client.post("/research/tasks/test-task-001/export-index")

        index_files = list(tmp_path.rglob("index.md"))
        content = index_files[0].read_text(encoding="utf-8")
        assert "Apple Leadership" in content or "Tim Cook" in content

    def test_api_returns_path(self, client, _setup_task, tmp_path) -> None:
        """API 返回导出路径。"""
        from db.repositories import TaskRepository
        from db.session import get_session
        session = get_session()
        TaskRepository(session).update_task_metadata("test-task-001", obsidian_path=str(tmp_path))
        session.close()

        response = client.post("/research/tasks/test-task-001/export-index")
        data = response.json()
        assert "path" in data
        assert "index.md" in data["path"]

    def test_task_not_found(self, client) -> None:
        """不存在的 task 返回 404。"""
        response = client.post("/research/tasks/nonexistent/export-index")
        assert response.status_code == 404


class TestGetSourcesEnhanced:
    """测试增强后的 GET /research/tasks/{task_id}/sources。"""

    def test_returns_items_field(self, client, _setup_task) -> None:
        """返回 items 字段（全部来源完整列表）。"""
        response = client.get("/research/tasks/test-task-001/sources")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 3

    def test_items_have_full_fields(self, client, _setup_task) -> None:
        """items 包含完整字段。"""
        response = client.get("/research/tasks/test-task-001/sources")
        data = response.json()
        item = data["items"][0]

        assert "id" in item
        assert "title" in item
        assert "url" in item
        assert "domain" in item
        assert "snippet" in item
        assert "source_level" in item
        assert "source_type" in item
        assert "relevance_score" in item
        assert "authority_score" in item
        assert "originality_score" in item
        assert "gossip_score" in item
        assert "downloadable" in item
        assert "download_status" in item
        assert "reason_to_read" in item

    def test_categories_still_present(self, client, _setup_task) -> None:
        """仍然返回 categories 分类。"""
        response = client.get("/research/tasks/test-task-001/sources")
        data = response.json()
        assert "categories" in data
        assert "total" in data
        assert data["total"] == 3
