"""研究任务管理服务测试。"""

import pytest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from db.tables import TaskTable
from models.enums import TaskStatus


@pytest.fixture
def mock_session():
    """创建 mock session。"""
    session = MagicMock()
    return session


@pytest.fixture
def sample_task_row():
    """创建示例 TaskTable 行。"""
    row = MagicMock(spec=TaskTable)
    row.id = "task-001"
    row.topic = "原始主题"
    row.canonical_topic = ""
    row.mode = "auto"
    row.language = "mixed"
    row.depth = "standard"
    row.include_gossip = False
    row.include_books = True
    row.include_video = False
    row.status = TaskStatus.COMPLETED
    row.obsidian_path = "/vault/path"
    row.task_type = "search_research"
    row.user_language = "zh"
    row.working_language = "en"
    row.output_language = "zh"
    row.search_strategy = "bilingual"
    row.metadata_json = "{}"
    row.cloned_from_task_id = ""
    row.deleted_at = None
    row.renamed_at = None
    row.exported = True
    row.export_path = "/vault/path/Research/原始主题/index.md"
    row.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    row.completed_at = datetime(2025, 1, 1, 0, 5, tzinfo=UTC)
    row.updated_at = datetime(2025, 1, 1, 0, 5, tzinfo=UTC)
    return row


class TestRenameTask:
    """重命名任务测试。"""

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_rename_task_success(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session, sample_task_row):
        from services.research_service import ResearchTaskManagementService

        mock_get_session.return_value = mock_session
        mock_session.get.return_value = sample_task_row

        # rename_task 在 repo 中会修改 row
        def mock_rename(task_id, topic, canonical_topic=None):
            sample_task_row.topic = topic
            sample_task_row.renamed_at = datetime.now(UTC)
            return sample_task_row

        with patch("db.repositories.TaskRepository.rename_task", side_effect=mock_rename):
            with patch("db.repositories.TaskRepository.get_task", return_value=sample_task_row):
                service = ResearchTaskManagementService()
                result = service.rename_task("task-001", "新主题名称")

        assert result["task_id"] == "task-001"
        assert "已重命名" in result["message"]
        assert "error" not in result

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_rename_task_not_found(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session):
        from services.research_service import ResearchTaskManagementService

        mock_get_session.return_value = mock_session
        mock_session.get.return_value = None

        with patch("db.repositories.TaskRepository.get_task", return_value=None):
            service = ResearchTaskManagementService()
            result = service.rename_task("nonexistent", "新主题")

        assert result["error"] == "not_found"

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_rename_deleted_task_rejected(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session, sample_task_row):
        from services.research_service import ResearchTaskManagementService

        sample_task_row.deleted_at = datetime.now(UTC)
        mock_get_session.return_value = mock_session
        mock_session.get.return_value = sample_task_row

        with patch("db.repositories.TaskRepository.get_task", return_value=sample_task_row):
            service = ResearchTaskManagementService()
            result = service.rename_task("task-001", "新主题")

        assert result["error"] == "deleted"


class TestSoftDeleteTask:
    """软删除任务测试。"""

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_soft_delete_sets_deleted_at(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session, sample_task_row):
        from services.research_service import ResearchTaskManagementService

        mock_get_session.return_value = mock_session
        mock_session.get.return_value = sample_task_row

        def mock_soft_delete(task_id):
            sample_task_row.deleted_at = datetime.now(UTC)
            return sample_task_row

        with patch("db.repositories.TaskRepository.get_task", return_value=sample_task_row):
            with patch("db.repositories.TaskRepository.soft_delete_task", side_effect=mock_soft_delete):
                service = ResearchTaskManagementService()
                result = service.soft_delete_task("task-001")

        assert result["status"] == "deleted"
        assert "已删除" in result["message"]

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_soft_delete_already_deleted(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session, sample_task_row):
        from services.research_service import ResearchTaskManagementService

        sample_task_row.deleted_at = datetime.now(UTC)
        mock_get_session.return_value = mock_session
        mock_session.get.return_value = sample_task_row

        with patch("db.repositories.TaskRepository.get_task", return_value=sample_task_row):
            service = ResearchTaskManagementService()
            result = service.soft_delete_task("task-001")

        assert result["error"] == "already_deleted"


class TestListTasksFiltering:
    """列表过滤测试。"""

    def test_list_tasks_default_excludes_deleted(self, mock_session):
        from db.repositories import TaskRepository

        repo = TaskRepository(mock_session)

        # 模拟 query chain
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        repo.list_tasks(include_deleted=False)

        # 验证 filter 被调用（过滤 deleted_at IS NULL）
        mock_query.filter.assert_called()

    def test_list_tasks_include_deleted(self, mock_session):
        from db.repositories import TaskRepository

        repo = TaskRepository(mock_session)

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        repo.list_tasks(include_deleted=True)

        # include_deleted=True 时不应过滤 deleted_at
        # query chain 直接到 order_by
        mock_query.order_by.assert_called()


class TestCloneTask:
    """复制任务测试。"""

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_clone_creates_new_task(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session, sample_task_row):
        from services.research_service import ResearchTaskManagementService

        mock_get_session.return_value = mock_session
        mock_session.get.return_value = sample_task_row

        new_row = MagicMock(spec=TaskTable)
        new_row.id = "task-002"
        new_row.topic = sample_task_row.topic
        new_row.status = TaskStatus.PENDING

        with patch("db.repositories.TaskRepository.get_task", return_value=sample_task_row):
            with patch("db.repositories.TaskRepository.clone_task", return_value=new_row):
                service = ResearchTaskManagementService()
                result = service.clone_task("task-001")

        assert result["new_task_id"] == "task-002"
        assert result["status"] == "pending"

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_clone_with_topic_override(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session, sample_task_row):
        from services.research_service import ResearchTaskManagementService

        mock_get_session.return_value = mock_session
        mock_session.get.return_value = sample_task_row

        new_row = MagicMock(spec=TaskTable)
        new_row.id = "task-003"
        new_row.topic = "覆盖的主题"
        new_row.status = TaskStatus.PENDING

        with patch("db.repositories.TaskRepository.get_task", return_value=sample_task_row):
            with patch("db.repositories.TaskRepository.clone_task", return_value=new_row) as mock_clone:
                service = ResearchTaskManagementService()
                result = service.clone_task("task-001", topic_override="覆盖的主题")

        mock_clone.assert_called_once_with("task-001", "覆盖的主题")
        assert result["new_task_id"] == "task-003"

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_clone_not_found(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session):
        from services.research_service import ResearchTaskManagementService

        mock_get_session.return_value = mock_session
        mock_session.get.return_value = None

        with patch("db.repositories.TaskRepository.get_task", return_value=None):
            with patch("db.repositories.TaskRepository.clone_task", return_value=None):
                service = ResearchTaskManagementService()
                result = service.clone_task("nonexistent")

        assert result["error"] == "not_found"


class TestRerunTask:
    """重新发起任务测试。"""

    @patch("services.research_service.get_recorder")
    @patch("services.research_service.log_event")
    @patch("db.session.get_session")
    def test_rerun_clone_mode(self, mock_get_session, mock_log_event, mock_get_recorder, mock_session, sample_task_row):
        from services.research_service import ResearchTaskManagementService

        mock_get_session.return_value = mock_session
        mock_session.get.return_value = sample_task_row

        new_row = MagicMock(spec=TaskTable)
        new_row.id = "task-004"
        new_row.topic = sample_task_row.topic
        new_row.status = TaskStatus.PENDING

        with patch("db.repositories.TaskRepository.get_task", return_value=sample_task_row):
            with patch("db.repositories.TaskRepository.clone_task", return_value=new_row):
                service = ResearchTaskManagementService()
                result = service.rerun_task("task-001", clone=True)

        assert result["new_task_id"] == "task-004"
        assert result["status"] == "pending"

    def test_rerun_no_clone_not_supported(self):
        from services.research_service import ResearchTaskManagementService

        service = ResearchTaskManagementService()
        result = service.rerun_task("task-001", clone=False)

        assert result["error"] == "not_supported"
