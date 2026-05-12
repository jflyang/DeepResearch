"""ReportIngestionService MVP 集成测试。"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.reference_extraction_service import ReferenceExtractionService
from app.services.report_ingestion_service import ReportIngestionService
from app.services.report_parser_service import ReportParserService
from app.tracing.recorder import TraceRecorder
from db.repositories import SourceRepository, TaskRepository
from db.tables import Base
from models.enums import DownloadStatus, ResearchTaskType, TaskStatus
from models.schemas import ExtractedDocument, ImportedReportCreate, SourceItem


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tmp_reports_dir(tmp_path):
    reports_dir = tmp_path / "imported_reports"
    reports_dir.mkdir()
    return reports_dir


@pytest.fixture
def task_repo(db_session):
    return TaskRepository(db_session)


@pytest.fixture
def source_repo(db_session):
    return SourceRepository(db_session)


@pytest.fixture
def trace_recorder():
    return TraceRecorder()


def _make_successful_extraction_service():
    """创建一个 mock extraction_service，所有 URL 抓取成功。"""
    service = AsyncMock()

    async def _extract(source_item: SourceItem) -> ExtractedDocument:
        return ExtractedDocument(
            source_item_id=source_item.id,
            title=source_item.title,
            content="Extracted content for " + source_item.url,
        )

    service.extract_source = _extract
    return service


def _make_failing_extraction_service():
    """创建一个 mock extraction_service，所有 URL 抓取失败。"""
    service = AsyncMock()

    async def _extract(source_item: SourceItem) -> ExtractedDocument:
        raise RuntimeError(f"Network error for {source_item.url}")

    service.extract_source = _extract
    return service


def _make_partial_extraction_service():
    """创建一个 mock extraction_service，第一个成功，第二个失败。"""
    service = AsyncMock()
    call_count = {"n": 0}

    async def _extract(source_item: SourceItem) -> ExtractedDocument:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ExtractedDocument(
                source_item_id=source_item.id,
                title=source_item.title,
                content="Success content",
            )
        else:
            raise RuntimeError("Simulated failure")

    service.extract_source = _extract
    return service


def _create_task_with_report(task_repo, tmp_reports_dir, report_text: str, task_id: str = "test-task"):
    """创建一个 report_ingestion task 并保存 report_text。"""
    request = ImportedReportCreate(
        topic="测试报告",
        report_text=report_text,
    )
    task_repo.create_report_ingestion_task(
        request, task_id=task_id, reports_dir=tmp_reports_dir
    )
    return task_id


def _build_service(
    task_repo, source_repo, extraction_service, trace_recorder, tmp_reports_dir
):
    return ReportIngestionService(
        report_parser=ReportParserService(),
        reference_extractor=ReferenceExtractionService(),
        extraction_service=extraction_service,
        source_repository=source_repo,
        task_repository=task_repo,
        trace_recorder=trace_recorder,
        reports_dir=tmp_reports_dir,
    )


REPORT_WITH_TWO_URLS = """
# 研究报告

根据 [Article A](https://example.com/article-a) 的报道，
以及 [Article B](https://example.com/article-b) 的分析。
"""


class TestRunImportTaskBasic:
    @pytest.mark.asyncio
    async def test_parses_two_urls(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """run_import_task 解析两个 URL。"""
        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_TWO_URLS
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
        )

        result = await service.run_import_task(task_id)
        assert result.parsed_url_count == 2

    @pytest.mark.asyncio
    async def test_saves_two_source_items(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """保存两个 SourceItem。"""
        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_TWO_URLS
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
        )

        result = await service.run_import_task(task_id)
        assert result.source_count == 2

        # 验证 DB 中有 2 条 source
        sources = source_repo.get_by_task(task_id)
        assert len(sources) == 2

    @pytest.mark.asyncio
    async def test_extraction_success_count(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """mock extraction 成功计数正确。"""
        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_TWO_URLS
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
        )

        result = await service.run_import_task(task_id)
        assert result.extracted_document_count == 2
        assert result.failed_count == 0


class TestPartialFailure:
    @pytest.mark.asyncio
    async def test_one_failure_does_not_affect_other(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """一个 URL extraction 失败不影响另一个。"""
        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_TWO_URLS
        )
        service = _build_service(
            task_repo, source_repo,
            _make_partial_extraction_service(),
            trace_recorder, tmp_reports_dir,
        )

        result = await service.run_import_task(task_id)
        assert result.extracted_document_count == 1
        assert result.failed_count == 1
        # 任务仍然完成（不是 failed）
        row = task_repo.get_task(task_id)
        assert row.status == TaskStatus.COMPLETED


class TestReportIngestionResult:
    @pytest.mark.asyncio
    async def test_returns_report_ingestion_result(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """返回 ReportIngestionResult。"""
        from models.schemas import ReportIngestionResult

        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_TWO_URLS
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
        )

        result = await service.run_import_task(task_id)
        assert isinstance(result, ReportIngestionResult)
        assert result.task_id == task_id
        assert result.parsed_url_count == 2
        assert result.source_count == 2
        assert result.extracted_document_count == 2


class TestTraceRecording:
    @pytest.mark.asyncio
    async def test_trace_records_parse_and_extraction(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """trace 记录 parse 和 extraction。"""
        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_TWO_URLS
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
        )

        await service.run_import_task(task_id)

        events = trace_recorder.get_events(task_id)
        steps = [e.step for e in events]

        assert "report_parse_started" in steps
        assert "report_parse_finished" in steps
        assert "url_extraction_started" in steps
        assert "url_extraction_finished" in steps
        assert "report_ingestion_completed" in steps
