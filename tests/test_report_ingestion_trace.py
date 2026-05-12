"""Report Ingestion Trace 完整性测试。"""

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.schemas import ReportReferenceExtractionOutput, ReportUnderstandingOutput
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
            source_item_id=source_item.id, title=source_item.title, content="content"
        )

    service.extract_source = _extract
    return service


def _make_failing_extraction():
    service = AsyncMock()

    async def _extract(source_item: SourceItem) -> ExtractedDocument:
        raise RuntimeError(f"Network error for {source_item.url}")

    service.extract_source = _extract
    return service


def _create_task(task_repo, tmp_reports_dir, report_text, task_id="trace-test"):
    request = ImportedReportCreate(topic="Trace Test", report_text=report_text)
    task_repo.create_report_ingestion_task(request, task_id=task_id, reports_dir=tmp_reports_dir)
    return task_id


REPORT = """
# 研究报告

根据 [Article](https://example.com/article) 的报道。

在《深度学习》中描述了基础理论。

参考 arXiv:1706.03762 的方法。
"""


class TestReportIngestionTraceEvents:
    @pytest.mark.asyncio
    async def test_task_created_trace(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """parse 完成后记录 url_count/book_count/paper_count。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

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
        steps = [e.step for e in events]

        # 解析阶段
        assert "report_parse_started" in steps
        assert "report_parse_finished" in steps

        # 解析完成事件包含计数
        parse_finished = next(e for e in events if e.step == "report_parse_finished")
        assert parse_finished.output_summary["url_count"] >= 1
        assert parse_finished.output_summary["book_count"] >= 1
        assert parse_finished.output_summary["paper_count"] >= 1

    @pytest.mark.asyncio
    async def test_llm_enhancement_with_llm(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """LLM 增强成功时记录 used_llm。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

        analyzer = AsyncMock(spec=ReportLLMAnalyzer)
        analyzer.available = True
        analyzer.understand_report = AsyncMock(return_value=ReportUnderstandingOutput(
            main_entities=["Test Entity"]
        ))
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

        finished = next(e for e in events if e.step == "report_understanding_finished")
        assert finished.output_summary["status"] == "used_llm"

    @pytest.mark.asyncio
    async def test_llm_disabled_records_skipped(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """LLM disabled 时记录 skipped。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=None,
        )

        await service.run_import_task(task_id)

        events = trace_recorder.get_events(task_id)
        steps = [e.step for e in events]
        assert "llm_enhancement_skipped" in steps

    @pytest.mark.asyncio
    async def test_url_extraction_success_trace(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """URL extraction 成功记录。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

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
        steps = [e.step for e in events]
        assert "url_extraction_started" in steps
        assert "url_extraction_finished" in steps

        finished = next(e for e in events if e.step == "url_extraction_finished")
        assert finished.output_summary["extracted_count"] >= 1

    @pytest.mark.asyncio
    async def test_url_extraction_failure_trace(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """URL extraction 失败记录 error，但任务继续。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_failing_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
        )

        await service.run_import_task(task_id)

        events = trace_recorder.get_events(task_id)
        steps = [e.step for e in events]
        # 任务仍然完成
        assert "report_ingestion_completed" in steps
        # 失败计数
        finished = next(e for e in events if e.step == "url_extraction_finished")
        assert finished.output_summary["failed_count"] >= 1

    @pytest.mark.asyncio
    async def test_reference_merge_trace(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """reference_merge_finished 包含总计数。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

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
        merge = next((e for e in events if e.step == "reference_merge_finished"), None)
        assert merge is not None
        assert "rule_reference_count" in merge.output_summary
        assert "merged_reference_count" in merge.output_summary

    @pytest.mark.asyncio
    async def test_report_ingestion_completed_trace(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """report_ingestion_completed 包含总计数。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

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
        completed = next(e for e in events if e.step == "report_ingestion_completed")
        assert "source_count" in completed.output_summary
        assert "extracted_document_count" in completed.output_summary

    @pytest.mark.asyncio
    async def test_trace_no_report_text(self, task_repo, source_repo, trace_recorder, tmp_reports_dir):
        """trace payload 不包含完整 report_text。"""
        long_text = "SENSITIVE " * 5000
        request = ImportedReportCreate(topic="Secret", report_text=long_text)
        task_repo.create_report_ingestion_task(
            request, task_id="no-leak", reports_dir=tmp_reports_dir
        )

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
        )

        await service.run_import_task("no-leak")

        events = trace_recorder.get_events("no-leak")
        for event in events:
            if event.input_summary:
                serialized = str(event.input_summary)
                assert len(serialized) < 10000
            if event.output_summary:
                serialized = str(event.output_summary)
                # 不应包含大量 SENSITIVE 文本
                assert serialized.count("SENSITIVE") < 5


class TestTraceSummaryReportIngestion:
    @pytest.mark.asyncio
    async def test_summary_includes_report_ingestion_data(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """trace summary 包含 report_ingestion 专用数据。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT)

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

        summary = trace_recorder.get_summary(task_id)
        assert summary["task_type"] == "report_ingestion"
        assert "report_ingestion" in summary
        assert summary["report_ingestion"]["source_count"] >= 1
        assert "references" in summary
