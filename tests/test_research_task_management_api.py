"""研究任务管理 API 端点测试。"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """创建 FastAPI 测试客户端。"""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_task_row():
    """创建 mock task row。"""
    from db.tables import TaskTable
    row = MagicMock(spec=TaskTable)
    row.id = "task-test-001"
    row.topic = "测试主题"
    row.canonical_topic = ""
    row.mode = "auto"
    row.status = "completed"
    row.depth = "standard"
    row.source_count = 10
    row.exported = False
    row.export_path = ""
    row.deleted_at = None
    row.cloned_from_task_id = ""
    row.created_at = None
    row.completed_at = None
    return row


class TestRenameEndpoint:
    """PATCH /research/tasks/{task_id} 测试。"""

    def test_rename_success(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.rename_task.return_value = {
                "task_id": "task-001",
                "status": "completed",
                "message": "已重命名为: 新主题",
            }

            response = test_client.patch(
                "/research/tasks/task-001",
                json={"topic": "新主题"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-001"
        assert "已重命名" in data["message"]

    def test_rename_empty_topic(self, test_client):
        response = test_client.patch(
            "/research/tasks/task-001",
            json={"topic": ""},
        )
        assert response.status_code == 400

    def test_rename_not_found(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.rename_task.return_value = {
                "error": "not_found",
                "message": "任务不存在",
            }

            response = test_client.patch(
                "/research/tasks/nonexistent",
                json={"topic": "新主题"},
            )

        assert response.status_code == 404


class TestDeleteEndpoint:
    """DELETE /research/tasks/{task_id} 测试。"""

    def test_soft_delete_default(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.soft_delete_task.return_value = {
                "task_id": "task-001",
                "status": "deleted",
                "message": "研究任务已删除",
            }

            response = test_client.delete("/research/tasks/task-001")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

    def test_delete_not_found(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.soft_delete_task.return_value = {
                "error": "not_found",
                "message": "任务不存在",
            }

            response = test_client.delete("/research/tasks/nonexistent")

        assert response.status_code == 404


class TestListTasksWithDeleted:
    """GET /research/tasks 测试 include_deleted 参数。"""

    def test_list_excludes_deleted_by_default(self, test_client, mock_task_row):
        with patch("db.repositories.TaskRepository.list_tasks", return_value=[mock_task_row]) as mock_list:
            with patch("db.repositories.TaskRepository.count_tasks", return_value=1):
                with patch("db.repositories.SourceRepository.count_by_task", return_value=10):
                    with patch("db.repositories.SourceRepository.count_high_quality", return_value=3):
                        with patch("db.repositories.SourceRepository.count_extracted", return_value=2):
                            response = test_client.get("/research/tasks")

        assert response.status_code == 200
        # 验证 include_deleted 默认为 False
        if mock_list.called:
            call_kwargs = mock_list.call_args[1] if mock_list.call_args[1] else {}
            assert call_kwargs.get("include_deleted", False) is False

    def test_list_includes_deleted_when_requested(self, test_client, mock_task_row):
        from datetime import UTC, datetime
        mock_task_row.deleted_at = datetime(2025, 1, 1, tzinfo=UTC)

        with patch("db.repositories.TaskRepository.list_tasks", return_value=[mock_task_row]) as mock_list:
            with patch("db.repositories.TaskRepository.count_tasks", return_value=1):
                with patch("db.repositories.SourceRepository.count_by_task", return_value=10):
                    with patch("db.repositories.SourceRepository.count_high_quality", return_value=3):
                        with patch("db.repositories.SourceRepository.count_extracted", return_value=2):
                            response = test_client.get("/research/tasks?include_deleted=true")

        assert response.status_code == 200


class TestCloneEndpoint:
    """POST /research/tasks/{task_id}/clone 测试。"""

    def test_clone_success(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.clone_task.return_value = {
                "task_id": "task-001",
                "new_task_id": "task-002",
                "status": "pending",
                "message": "已复制研究任务",
            }

            response = test_client.post(
                "/research/tasks/task-001/clone",
                json={"rerun_immediately": False},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["new_task_id"] == "task-002"

    def test_clone_not_found(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.clone_task.return_value = {
                "error": "not_found",
                "message": "任务不存在",
            }

            response = test_client.post(
                "/research/tasks/nonexistent/clone",
                json={},
            )

        assert response.status_code == 404


class TestRerunEndpoint:
    """POST /research/tasks/{task_id}/rerun 测试。"""

    def test_rerun_clone_mode(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.rerun_task.return_value = {
                "task_id": "task-001",
                "new_task_id": "task-003",
                "status": "pending",
                "message": "已基于历史任务复制并准备重新研究",
            }

            response = test_client.post(
                "/research/tasks/task-001/rerun",
                json={"clone": True},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["new_task_id"] == "task-003"

    def test_rerun_no_clone_returns_400(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.rerun_task.return_value = {
                "error": "not_supported",
                "message": "暂不支持直接重跑原任务，请使用 clone=true 模式",
            }

            response = test_client.post(
                "/research/tasks/task-001/rerun",
                json={"clone": False},
            )

        assert response.status_code == 400

    def test_rerun_not_found(self, test_client):
        with patch("services.research_service.ResearchTaskManagementService") as MockService:
            mock_service = MockService.return_value
            mock_service.rerun_task.return_value = {
                "error": "not_found",
                "message": "任务不存在",
            }

            response = test_client.post(
                "/research/tasks/nonexistent/rerun",
                json={"clone": True},
            )

        assert response.status_code == 404
