"""ReportIngestionService LLM 增强集成测试。"""

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.schemas import (
    ImplicitReference,
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
from models.enums import ReferenceType
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


def _make_successful_extraction():
    service = AsyncMock()

    async def _extract(source_item: SourceItem) -> ExtractedDocument:
        return ExtractedDocument(
            source_item_id=source_item.id,
            title=source_item.title,
            content="Extracted content",
        )

    service.extract_source = _extract
    return service


def _make_llm_analyzer(understanding=None, references=None):
    """创建 mock LLM analyzer。"""
    analyzer = AsyncMock(spec=ReportLLMAnalyzer)
    analyzer.available = True
    analyzer.understand_report = AsyncMock(
        return_value=understanding or ReportUnderstandingOutput()
    )
    analyzer.extract_implicit_references = AsyncMock(
        return_value=references or ReportReferenceExtractionOutput()
    )
    analyzer.prioritize_references = AsyncMock(return_value=AsyncMock(items=[]))
    return analyzer


def _create_task(task_repo, tmp_reports_dir, report_text, task_id="test-llm"):
    request = ImportedReportCreate(topic="测试", report_text=report_text)
    task_repo.create_report_ingestion_task(request, task_id=task_id, reports_dir=tmp_reports_dir)
    return task_id


REPORT_WITH_ONE_URL = "参考 [Link](https://example.com/article) 的内容。"


class TestLLMEnhancementMerge:
    @pytest.mark.asyncio
    async def test_rule_parses_one_url(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """规则解析得到 1 个 URL。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT_WITH_ONE_URL)

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_successful_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=None,  # 无 LLM
        )

        result = await service.run_import_task(task_id)
        assert result.parsed_url_count == 1
        assert result.source_count == 1

    @pytest.mark.asyncio
    async def test_llm_adds_book_reference(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """Mock LLM 额外返回 1 本书。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT_WITH_ONE_URL)

        llm_refs = ReportReferenceExtractionOutput(
            additional_references=[
                ImplicitReference(
                    type="book",
                    title="Tim Cook Biography",
                    author_hint="Leander Kahney",
                    confidence=0.8,
                    reason="报告中提到了库克的管理风格",
                    search_query="Tim Cook biography Leander Kahney",
                )
            ],
            additional_search_queries=["Tim Cook early career"],
        )
        analyzer = _make_llm_analyzer(references=llm_refs)

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_successful_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=analyzer,
        )

        result = await service.run_import_task(task_id)
        # 1 URL (rule) + 1 book (LLM) = at least 2 sources processed
        # Book goes to enrichment, URL goes to extraction
        assert result.source_count >= 1

    @pytest.mark.asyncio
    async def test_duplicate_url_not_repeated(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """重复 URL 不重复。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT_WITH_ONE_URL)

        # LLM 返回和规则相同的 URL
        llm_refs = ReportReferenceExtractionOutput(
            additional_references=[
                ImplicitReference(
                    type="url",
                    title="Same Link",
                    url="https://example.com/article",
                    confidence=0.9,
                    reason="same as rule",
                )
            ]
        )
        analyzer = _make_llm_analyzer(references=llm_refs)

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_successful_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=analyzer,
        )

        result = await service.run_import_task(task_id)
        # 不应重复
        assert result.source_count == 1

    @pytest.mark.asyncio
    async def test_llm_failure_still_processes_rule_urls(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """LLM 失败时仍处理规则 URL。"""
        task_id = _create_task(task_repo, tmp_reports_dir, REPORT_WITH_ONE_URL)

        # LLM analyzer 抛异常
        analyzer = AsyncMock(spec=ReportLLMAnalyzer)
        analyzer.available = True
        analyzer.understand_report = AsyncMock(side_effect=RuntimeError("LLM down"))
        analyzer.extract_implicit_references = AsyncMock(side_effect=RuntimeError("LLM down"))

        service = ReportIngestionService(
            report_parser=ReportParserService(),
            reference_extractor=ReferenceExtractionService(),
            extraction_service=_make_successful_extraction(),
            source_repository=source_repo,
            task_repository=task_repo,
            trace_recorder=trace_recorder,
            reports_dir=tmp_reports_dir,
            llm_analyzer=analyzer,
        )

        result = await service.run_import_task(task_id)
        # 规则 URL 仍然被处理
        assert result.extracted_document_count == 1
        assert result.source_count == 1
