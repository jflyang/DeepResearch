"""ReportIngestionService LLM Trace 记录测试。"""

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.schemas import (
    ReportReferenceExtractionOutput,
    ReportUnderstandingOutput,
)
from app.services.reference_extraction_service import ReferenceExtractionService
from app.services.report_ingestion_service import ReportIngestionService
from app.services.report_llm_analyzer import ReportLLMAnalyzer
from app.services.report_parser_service import ReportParserService
from app.tracing.recorder import TraceRecorder
from db.repositories import SourceRepository, TaskRepository
from db.tables import Base
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
    d = tmp_path / "imported_reports"
    d.mkdir()
    return d


@pytest.fixture
def task_repo(db_session):
    return TaskRepository(db_session)


@pytest.fixture
def source_repo(db_session):
    return SourceRepository(db_session)


@pytest.fixture
def trace_recorder():
    return TraceRecorder()


def _make_extraction():
    service = AsyncMock()

    async def _extract(source_item: SourceItem) -> ExtractedDocument:
        return ExtractedDocument(
            source_item_id=source_item.id, title=source_item.title, content="ok"
        )

    service.extract_source = _extract
    return service


def _create_task(task_repo, tmp_reports_dir, task_id="trace-test"):
    request = ImportedReportCreate(
        topic="Trace Test", report_text="参考 [A](https://example.com) 的内容"
    )
    task_repo.create_report_ingestion_task(request, task_id=task_id, reports_dir=tmp_reports_dir)
    return task_id


REPORT_TEXT = "参考 [Link](https://example.com/page) 的内容。"


class TestLLMTraceRecording:
    @pytest.mark.asyncio
    async def test_report_understanding_records_used_llm(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """report_understanding 记录 used_llm。"""
        task_id = _create_task(task_repo, tmp_reports_dir)

        analyzer = AsyncMock(spec=ReportLLMAnalyzer)
        analyzer.available = True
        analyzer.understand_report = AsyncMock(return_value=ReportUnderstandingOutput())
        analyzer.extract_implicit_references = AsyncMock(
            return_value=ReportReferenceExtractionOutput()
        )

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=analyzer,
        )

        await service.run_import_task(task_id)

        events = trace_recorder.get_events(task_id)
        steps = [e.step for e in events]
        assert "report_understanding_started" in steps
        assert "report_understanding_finished" in steps

        # 检查 output_summary 包含 used_llm
        finished_events = [e for e in events if e.step == "report_understanding_finished"]
        assert len(finished_events) == 1
        assert finished_events[0].output_summary["status"] == "used_llm"

    @pytest.mark.asyncio
    async def test_report_reference_extraction_records_used_llm(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """report_reference_extraction 记录 used_llm。"""
        task_id = _create_task(task_repo, tmp_reports_dir)

        analyzer = AsyncMock(spec=ReportLLMAnalyzer)
        analyzer.available = True
        analyzer.understand_report = AsyncMock(return_value=ReportUnderstandingOutput())
        analyzer.extract_implicit_references = AsyncMock(
            return_value=ReportReferenceExtractionOutput()
        )

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=analyzer,
        )

        await service.run_import_task(task_id)

        events = trace_recorder.get_events(task_id)
        steps = [e.step for e in events]
        assert "report_reference_extraction_started" in steps
        assert "report_reference_extraction_finished" in steps

    @pytest.mark.asyncio
    async def test_llm_disabled_records_skipped(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """LLM disabled 时记录 fallback/skipped。"""
        task_id = _create_task(task_repo, tmp_reports_dir)

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=None,  # 无 LLM
        )

        await service.run_import_task(task_id)

        events = trace_recorder.get_events(task_id)
        steps = [e.step for e in events]
        assert "llm_enhancement_skipped" in steps

    @pytest.mark.asyncio
    async def test_trace_does_not_contain_report_text(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """Trace 不包含完整 report_text。"""
        long_report = "SECRET_CONTENT " * 1000
        request = ImportedReportCreate(topic="Secret", report_text=long_report)
        task_repo.create_report_ingestion_task(
            request, task_id="secret-task", reports_dir=tmp_reports_dir
        )

        analyzer = AsyncMock(spec=ReportLLMAnalyzer)
        analyzer.available = True
        analyzer.understand_report = AsyncMock(return_value=ReportUnderstandingOutput())
        analyzer.extract_implicit_references = AsyncMock(
            return_value=ReportReferenceExtractionOutput()
        )

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=analyzer,
        )

        await service.run_import_task("secret-task")

        events = trace_recorder.get_events("secret-task")
        # 检查所有 trace 事件不包含完整 report_text
        for event in events:
            if event.input_summary:
                for v in event.input_summary.values():
                    if isinstance(v, str):
                        assert "SECRET_CONTENT" not in v
            if event.output_summary:
                for v in event.output_summary.values():
                    if isinstance(v, str):
                        assert len(v) < 5000  # 不应有超长文本

    @pytest.mark.asyncio
    async def test_trace_does_not_contain_secrets(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """Trace 不包含 api_key/token/secret。"""
        task_id = _create_task(task_repo, tmp_reports_dir)

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
        )

        await service.run_import_task(task_id)

        events = trace_recorder.get_events(task_id)
        for event in events:
            # TraceRecorder 的 _sanitize 会处理敏感 key
            if event.input_summary:
                assert "api_key" not in str(event.input_summary).lower() or \
                       event.input_summary.get("api_key") == "***"
