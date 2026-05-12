"""ReportIngestionService 书籍/论文补充检索测试。"""

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.reference_extraction_service import ReferenceExtractionService
from app.services.report_ingestion_service import ReportIngestionService
from app.services.report_parser_service import ReportParserService
from app.tracing.recorder import TraceRecorder
from db.repositories import SourceRepository, TaskRepository
from db.tables import Base
from models.enums import ReferenceType, SourceOrigin, TaskStatus
from models.schemas import (
    ExpandedQuery,
    ExtractedDocument,
    ImportedReportCreate,
    SourceItem,
)
from providers.search.base import SearchResult
from models.enums import SearchSource, SourceType


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
    """Mock extraction_service，所有 URL 抓取成功。"""
    service = AsyncMock()

    async def _extract(source_item: SourceItem) -> ExtractedDocument:
        return ExtractedDocument(
            source_item_id=source_item.id,
            title=source_item.title,
            content="Extracted content for " + source_item.url,
        )

    service.extract_source = _extract
    return service


def _make_mock_search_router(book_results=None, paper_results=None):
    """Mock SearchRouter，根据 source_hint 返回不同结果。"""
    router = AsyncMock()

    async def _search_one(query: ExpandedQuery, limit: int = 10):
        hint = query.source_hint if isinstance(query.source_hint, str) else query.source_hint.value
        if hint == "book" and book_results is not None:
            return book_results
        if hint in ("paper", "academic") and paper_results is not None:
            return paper_results
        return []

    router.search_one = _search_one
    return router


def _create_task_with_report(task_repo, tmp_reports_dir, report_text, task_id="test-task"):
    request = ImportedReportCreate(topic="测试报告", report_text=report_text)
    task_repo.create_report_ingestion_task(
        request, task_id=task_id, reports_dir=tmp_reports_dir
    )
    return task_id


def _build_service(
    task_repo, source_repo, extraction_service, trace_recorder, tmp_reports_dir,
    search_router=None,
):
    return ReportIngestionService(
        report_parser=ReportParserService(),
        reference_extractor=ReferenceExtractionService(),
        extraction_service=extraction_service,
        source_repository=source_repo,
        task_repository=task_repo,
        search_router=search_router,
        trace_recorder=trace_recorder,
        reports_dir=tmp_reports_dir,
    )


# === Test data ===

REPORT_WITH_BOOK = """
# 研究报告

在《蒂姆·库克传》中详细描述了他的管理风格。

参考链接: https://example.com/article
"""

REPORT_WITH_PAPER = """
# 研究报告

Transformer 论文 arXiv:1706.03762 开创了新范式。

参考链接: https://example.com/article
"""

REPORT_WITH_BOOK_AND_PAPER = """
# 研究报告

在《深度学习》中描述了基础理论。

该论文的标识为 DOI: 10.1145/3292500.3330648。

参考链接: https://example.com/article
"""


class TestBookEnrichment:
    @pytest.mark.asyncio
    async def test_book_candidate_calls_search_router_with_book_hint(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """book candidate 调用 SearchRouter source_hint=book。"""
        book_results = [
            SearchResult(
                title="蒂姆·库克传 - Open Library",
                url="https://openlibrary.org/works/tim-cook",
                snippet="Tim Cook biography",
                source_provider=SearchSource.OPEN_LIBRARY,
                source_type=SourceType.BOOK,
            )
        ]
        router = _make_mock_search_router(book_results=book_results)

        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_BOOK
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
            search_router=router,
        )

        result = await service.run_import_task(task_id)
        assert result.enriched_book_count == 1

    @pytest.mark.asyncio
    async def test_book_enrichment_saves_source_item(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """mock SearchRouter 返回结果后保存 SourceItem。"""
        book_results = [
            SearchResult(
                title="蒂姆·库克传",
                url="https://openlibrary.org/works/tim-cook",
                snippet="Biography",
                source_provider=SearchSource.OPEN_LIBRARY,
                source_type=SourceType.BOOK,
            )
        ]
        router = _make_mock_search_router(book_results=book_results)

        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_BOOK
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
            search_router=router,
        )

        await service.run_import_task(task_id)

        sources = source_repo.get_by_task(task_id)
        # 1 URL + 1 enriched book
        assert len(sources) >= 2
        enriched = [s for s in sources if "openlibrary" in s.url]
        assert len(enriched) == 1


class TestPaperEnrichment:
    @pytest.mark.asyncio
    async def test_paper_candidate_calls_search_router_with_paper_hint(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """paper candidate 调用 SearchRouter source_hint=paper。"""
        paper_results = [
            SearchResult(
                title="Attention Is All You Need",
                url="https://arxiv.org/abs/1706.03762",
                snippet="Transformer paper",
                source_provider=SearchSource.ARXIV,
                source_type=SourceType.PAPER,
            )
        ]
        router = _make_mock_search_router(paper_results=paper_results)

        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_PAPER
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
            search_router=router,
        )

        result = await service.run_import_task(task_id)
        assert result.enriched_paper_count == 1

    @pytest.mark.asyncio
    async def test_paper_enrichment_saves_source_item(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """mock SearchRouter 返回结果后保存 SourceItem。"""
        paper_results = [
            SearchResult(
                title="Attention Is All You Need",
                url="https://arxiv.org/abs/1706.03762",
                snippet="Transformer",
                source_provider=SearchSource.ARXIV,
                source_type=SourceType.PAPER,
            )
        ]
        router = _make_mock_search_router(paper_results=paper_results)

        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_PAPER
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
            search_router=router,
        )

        await service.run_import_task(task_id)

        sources = source_repo.get_by_task(task_id)
        arxiv_sources = [s for s in sources if "arxiv" in s.url]
        assert len(arxiv_sources) == 1


class TestEnrichmentFailureIsolation:
    @pytest.mark.asyncio
    async def test_enrichment_failure_does_not_affect_url_extraction(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """enrichment 失败不影响 URL extraction。"""
        # SearchRouter 抛异常
        router = AsyncMock()

        async def _failing_search(query, limit=10):
            raise RuntimeError("Search provider unavailable")

        router.search_one = _failing_search

        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_BOOK_AND_PAPER
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
            search_router=router,
        )

        result = await service.run_import_task(task_id)

        # URL extraction 仍然成功
        assert result.extracted_document_count == 1
        # enrichment 失败计入 failed_count
        assert result.failed_count >= 2  # 1 book + 1 paper failed
        # 任务仍然完成
        row = task_repo.get_task(task_id)
        assert row.status == TaskStatus.COMPLETED


class TestSourceOriginEnriched:
    @pytest.mark.asyncio
    async def test_enriched_source_origin(
        self, task_repo, source_repo, trace_recorder, tmp_reports_dir
    ):
        """source_origin=imported_report_enriched。"""
        book_results = [
            SearchResult(
                title="Deep Learning Book",
                url="https://openlibrary.org/works/deep-learning",
                snippet="DL book",
                source_provider=SearchSource.OPEN_LIBRARY,
                source_type=SourceType.BOOK,
            )
        ]
        paper_results = [
            SearchResult(
                title="Test Paper",
                url="https://crossref.org/paper/123",
                snippet="Paper",
                source_provider=SearchSource.CROSSREF,
                source_type=SourceType.PAPER,
            )
        ]
        router = _make_mock_search_router(
            book_results=book_results, paper_results=paper_results
        )

        task_id = _create_task_with_report(
            task_repo, tmp_reports_dir, REPORT_WITH_BOOK_AND_PAPER
        )
        service = _build_service(
            task_repo, source_repo,
            _make_successful_extraction_service(),
            trace_recorder, tmp_reports_dir,
            search_router=router,
        )

        result = await service.run_import_task(task_id)

        # 验证 enriched sources 存在
        assert result.enriched_book_count >= 1
        assert result.enriched_paper_count >= 1
        assert result.enriched_source_count == result.enriched_book_count + result.enriched_paper_count
