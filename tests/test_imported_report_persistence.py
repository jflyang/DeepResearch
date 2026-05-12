"""外部报告导入持久化测试。"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.repositories import TaskRepository
from db.tables import Base, TaskTable
from models.enums import ResearchTaskType, TaskStatus
from models.schemas import ImportedReportCreate, ReportIngestionOptions


@pytest.fixture
def db_session():
    """创建内存 SQLite 数据库用于测试。"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tmp_reports_dir(tmp_path):
    """使用 pytest tmp_path 作为报告存储目录。"""
    reports_dir = tmp_path / "imported_reports"
    reports_dir.mkdir()
    return reports_dir


class TestCreateReportIngestionTask:
    def test_task_type_is_report_ingestion(self, db_session, tmp_reports_dir):
        """创建 report_ingestion task 后 DB 中 task_type=report_ingestion。"""
        repo = TaskRepository(db_session)
        request = ImportedReportCreate(
            topic="AI 发展报告",
            report_text="这是一份关于 AI 发展的研究报告...",
            report_source="https://example.com/report",
            output_language="zh",
        )
        task = repo.create_report_ingestion_task(
            request, task_id="ri-001", reports_dir=tmp_reports_dir
        )

        # 验证返回的 schema
        assert task.task_type == ResearchTaskType.REPORT_INGESTION
        assert task.topic == "AI 发展报告"
        assert task.status == TaskStatus.PENDING

        # 验证 DB 行
        row = repo.get_task("ri-001")
        assert row is not None
        assert row.task_type == ResearchTaskType.REPORT_INGESTION
        assert row.topic == "AI 发展报告"
        assert row.status == TaskStatus.PENDING

    def test_metadata_json_contains_expected_fields(self, db_session, tmp_reports_dir):
        """metadata_json 中保存 report_source/report_text_path/output_language/options。"""
        repo = TaskRepository(db_session)
        request = ImportedReportCreate(
            topic="量子计算",
            report_text="量子计算的最新进展...",
            report_source="https://example.com/quantum.pdf",
            output_language="en",
            options=ReportIngestionOptions(export_to_obsidian=True),
        )
        repo.create_report_ingestion_task(
            request, task_id="ri-002", reports_dir=tmp_reports_dir
        )

        metadata = repo.get_imported_report_metadata("ri-002")
        assert metadata["report_source"] == "https://example.com/quantum.pdf"
        assert "ri-002.md" in metadata["report_text_path"]
        assert metadata["output_language"] == "en"
        assert metadata["options"]["export_to_obsidian"] is True


class TestReportTextFile:
    def test_report_text_file_exists(self, db_session, tmp_reports_dir):
        """report_text 文件存在。"""
        repo = TaskRepository(db_session)
        request = ImportedReportCreate(
            topic="Test",
            report_text="报告内容 with UTF-8 中文",
        )
        repo.create_report_ingestion_task(
            request, task_id="ri-003", reports_dir=tmp_reports_dir
        )

        file_path = tmp_reports_dir / "ri-003.md"
        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == "报告内容 with UTF-8 中文"

    def test_load_imported_report_text(self, db_session, tmp_reports_dir):
        """load_imported_report_text 能读回。"""
        repo = TaskRepository(db_session)
        request = ImportedReportCreate(
            topic="Test",
            report_text="这是完整的报告文本内容",
        )
        repo.create_report_ingestion_task(
            request, task_id="ri-004", reports_dir=tmp_reports_dir
        )

        loaded = repo.load_imported_report_text("ri-004", reports_dir=tmp_reports_dir)
        assert loaded == "这是完整的报告文本内容"

    def test_load_nonexistent_returns_none(self, db_session, tmp_reports_dir):
        """不存在的 task_id 返回 None。"""
        repo = TaskRepository(db_session)
        loaded = repo.load_imported_report_text("nonexistent", reports_dir=tmp_reports_dir)
        assert loaded is None


class TestPersistenceAfterRebuild:
    def test_rebuild_repository_still_reads(self, db_session, tmp_reports_dir):
        """重建 repository 后仍能读回。"""
        repo1 = TaskRepository(db_session)
        request = ImportedReportCreate(
            topic="持久化测试",
            report_text="重启后仍能读取的内容",
        )
        repo1.create_report_ingestion_task(
            request, task_id="ri-005", reports_dir=tmp_reports_dir
        )

        # 模拟重建 repository
        repo2 = TaskRepository(db_session)

        # DB 数据仍在
        row = repo2.get_task("ri-005")
        assert row is not None
        assert row.task_type == ResearchTaskType.REPORT_INGESTION
        assert row.topic == "持久化测试"

        # 文件仍在
        loaded = repo2.load_imported_report_text("ri-005", reports_dir=tmp_reports_dir)
        assert loaded == "重启后仍能读取的内容"

        # metadata 仍在
        metadata = repo2.get_imported_report_metadata("ri-005")
        assert metadata["output_language"] == "zh"


class TestSearchResearchNotAffected:
    def test_normal_task_default_task_type(self, db_session):
        """普通 ResearchTask 不受影响，task_type 默认为 search_research。"""
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t-normal", topic="普通研究任务")

        row = repo.get_task("t-normal")
        assert row is not None
        assert row.task_type == "search_research"
        assert row.topic == "普通研究任务"

    def test_list_tasks_includes_both_types(self, db_session, tmp_reports_dir):
        """list_tasks 能同时列出两种类型的任务。"""
        repo = TaskRepository(db_session)

        # 创建普通任务
        repo.create_task(task_id="t-search", topic="搜索任务")

        # 创建报告导入任务
        request = ImportedReportCreate(
            topic="导入任务",
            report_text="报告内容",
        )
        repo.create_report_ingestion_task(
            request, task_id="t-import", reports_dir=tmp_reports_dir
        )

        tasks = repo.list_tasks(limit=10)
        assert len(tasks) == 2
        types = {t.task_type for t in tasks}
        assert "search_research" in types
        assert "report_ingestion" in types
