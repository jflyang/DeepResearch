"""自动抓取与导出流程测试 - 验证完整 auto_fetch → analyze → export 流程。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.schemas import DocumentAnalysisOutput
from models.enums import DownloadStatus, SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from services.auto_fetch_service import (
    AutoFetchExportService,
    AutoFetchResult,
    _default_policy,
    _reset_policy_cache,
)


@pytest.fixture(autouse=True)
def reset_policy():
    _reset_policy_cache()
    yield
    _reset_policy_cache()


@pytest.fixture
def task():
    return ResearchTask(
        id="test-auto-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sources():
    return [
        SourceItem(
            id="s1",
            task_id="test-auto-001",
            title="Tim Cook Biography",
            url="https://example.com/cook-bio",
            domain="example.com",
            snippet="A detailed biography",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.S,
            relevance_score=0.95,
            authority_score=0.9,
            reason_to_read="Official biography",
        ),
        SourceItem(
            id="s2",
            task_id="test-auto-001",
            title="Apple Leadership Interview",
            url="https://apple.com/interview",
            domain="apple.com",
            snippet="Interview with Tim Cook",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.A,
            relevance_score=0.85,
            authority_score=0.8,
            reason_to_read="First-hand interview",
        ),
        SourceItem(
            id="s3",
            task_id="test-auto-001",
            title="Random Blog Post",
            url="https://blog.example.com/post",
            domain="blog.example.com",
            snippet="Some blog",
            source_type=SourceType.BLOG,
            source_level=SourceLevel.C,
            relevance_score=0.4,
            reason_to_read="Blog post",
        ),
    ]


@pytest.fixture
def mock_extraction_service():
    """Mock extraction service that returns content."""
    service = MagicMock()

    async def mock_extract(source_item):
        source_item.download_status = DownloadStatus.EXTRACTED
        return ExtractedDocument(
            source_item_id=source_item.id,
            title=source_item.title,
            author="Test Author",
            content=f"Full text content for {source_item.title}. " * 50,
            summary="",
            people=["Tim Cook"],
            concepts=["Apple"],
        )

    service.extract_source = AsyncMock(side_effect=mock_extract)
    return service


@pytest.fixture
def mock_failing_extraction_service():
    """Mock extraction service that fails."""
    service = MagicMock()

    async def mock_extract(source_item):
        source_item.download_status = DownloadStatus.FAILED
        return ExtractedDocument(
            source_item_id=source_item.id,
            title=source_item.title,
            content="",
        )

    service.extract_source = AsyncMock(side_effect=mock_extract)
    return service


class TestAutoFetchTriggered:
    """研究流程 scoring 后触发 auto_fetch。"""

    @pytest.mark.asyncio
    async def test_auto_fetch_selects_sa_sources(self, task, sources, mock_extraction_service):
        """auto_fetch 选择 S/A 来源。"""
        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=_default_policy(),
        )

        # 禁用导出（没有 vault）
        policy = _default_policy()
        policy["auto_export"]["enabled"] = False
        service._policy = policy

        result = await service.run(task=task, sources=sources)

        assert result.selected_count == 2  # S + A
        assert result.skipped_count == 1  # C level

    @pytest.mark.asyncio
    async def test_extraction_called_for_selected(self, task, sources, mock_extraction_service):
        """mock extraction 成功后保存文档。"""
        policy = _default_policy()
        policy["auto_export"]["enabled"] = False
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources)

        assert result.fetched_count == 2
        assert len(result.extracted_docs) == 2
        # 验证 extraction service 被调用了 2 次
        assert mock_extraction_service.extract_source.call_count == 2

    @pytest.mark.asyncio
    async def test_extraction_failure_does_not_fail_task(self, task, sources, mock_failing_extraction_service):
        """extraction 失败不导致任务失败。"""
        policy = _default_policy()
        policy["auto_export"]["enabled"] = False
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_failing_extraction_service,
            policy=policy,
        )

        # 不应抛出异常
        result = await service.run(task=task, sources=sources)

        assert result.failed_count == 2
        assert result.fetched_count == 0
        # 任务本身没有失败（AutoFetchResult 正常返回）
        assert isinstance(result, AutoFetchResult)


class TestDocumentAnalysis:
    """DocumentAnalysisService 被调用。"""

    @pytest.mark.asyncio
    async def test_analysis_called_with_llm(self, task, sources, mock_extraction_service):
        """有 LLM 时调用 DocumentAnalysisService。"""
        mock_gateway = MagicMock()
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="这是一篇关于 Tim Cook 的传记文章。",
            people=["Tim Cook", "Steve Jobs"],
            places=["Alabama"],
            concepts=["Apple", "Leadership"],
            key_points=["Cook 出生于 Alabama"],
            story_points=["小镇成长经历"],
        ))

        policy = _default_policy()
        policy["auto_export"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=mock_gateway,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources)

        assert result.analyzed_count == 2
        # 验证分析结果写回了 ExtractedDocument
        for doc in result.extracted_docs.values():
            assert doc.summary != "" or doc.people != []

    @pytest.mark.asyncio
    async def test_analysis_skipped_without_llm(self, task, sources, mock_extraction_service):
        """没有 LLM 时跳过分析。"""
        policy = _default_policy()
        policy["auto_export"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources)

        assert result.analyzed_count == 0
        assert result.fetched_count == 2  # 抓取仍然成功


class TestTraceRecording:
    """Trace 记录 selected/fetched/failed。"""

    @pytest.mark.asyncio
    async def test_trace_records_auto_fetch_events(self, task, sources, mock_extraction_service):
        """Trace 记录自动抓取事件。"""
        from app.tracing.recorder import get_recorder

        policy = _default_policy()
        policy["auto_export"]["enabled"] = False
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources)

        # 验证 trace 记录了事件
        recorder = get_recorder()
        events = recorder.get_events(task.id)

        steps = [e.step for e in events]
        assert "auto_fetch_started" in steps
        assert "auto_fetch_source_started" in steps
        assert "auto_fetch_source_finished" in steps
        assert "auto_fetch_finished" in steps

    @pytest.mark.asyncio
    async def test_trace_records_failure(self, task, sources):
        """Trace 记录抓取失败。"""
        from app.tracing.recorder import get_recorder

        # 创建一个会抛异常的 extraction service
        failing_service = MagicMock()
        failing_service.extract_source = AsyncMock(side_effect=Exception("Network error"))

        policy = _default_policy()
        policy["auto_export"]["enabled"] = False
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=failing_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources)

        assert result.failed_count == 2

        recorder = get_recorder()
        events = recorder.get_events(task.id)
        steps = [e.step for e in events]
        assert "auto_fetch_source_failed" in steps
