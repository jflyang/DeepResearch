"""source_reason_generation 测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.enums import DownloadStatus, SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ResearchTask, SourceItem


@pytest.fixture
def sample_task():
    return ResearchTask(
        id="task-reason-001",
        topic="Tim Cook childhood",
        mode=TaskMode.PERSON,
        status=TaskStatus.RUNNING,
    )


@pytest.fixture
def sample_sources():
    return [
        SourceItem(
            id="s1", task_id="task-reason-001", title="Tim Cook Early Life",
            url="https://example.com/1", source_level=SourceLevel.S,
            source_type=SourceType.NEWS, snippet="Article about Tim Cook",
            reason_to_read="[S] Official source",
        ),
        SourceItem(
            id="s2", task_id="task-reason-001", title="Apple CEO Biography",
            url="https://example.com/2", source_level=SourceLevel.A,
            source_type=SourceType.BOOK, snippet="Book about Apple",
            reason_to_read="[A] Book source",
        ),
        SourceItem(
            id="s3", task_id="task-reason-001", title="Low quality blog",
            url="https://example.com/3", source_level=SourceLevel.D,
            source_type=SourceType.BLOG, snippet="Random blog",
            reason_to_read="[D] Low quality",
        ),
    ]


class TestSourceReasonGeneration:
    """source_reason_generation 测试。"""

    @pytest.mark.asyncio
    async def test_generates_reasons_for_top_sources(self, sample_task, sample_sources):
        """应为 S/A/B 级来源生成 reason。"""
        from services.research_service import ResearchService

        mock_gateway = MagicMock()

        # Mock run_json 返回
        from pydantic import BaseModel, Field

        class MockResult:
            reasons = [
                {"url": "https://example.com/1", "reason": "LLM 生成的理由1"},
                {"url": "https://example.com/2", "reason": "LLM 生成的理由2"},
            ]

        mock_gateway.run_json = AsyncMock(return_value=MockResult())

        service = ResearchService(ai_gateway=mock_gateway)
        await service._generate_source_reasons(sample_task, sample_sources)

        # S 级来源应被更新
        assert sample_sources[0].reason_to_read == "LLM 生成的理由1"
        # A 级来源应被更新
        assert sample_sources[1].reason_to_read == "LLM 生成的理由2"
        # D 级来源不应被处理
        assert sample_sources[2].reason_to_read == "[D] Low quality"

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self, sample_task, sample_sources):
        """LLM 失败时保留原有 reason。"""
        from services.research_service import ResearchService

        mock_gateway = MagicMock()
        mock_gateway.run_json = AsyncMock(side_effect=Exception("LLM timeout"))

        service = ResearchService(ai_gateway=mock_gateway)
        original_reasons = [s.reason_to_read for s in sample_sources]

        await service._generate_source_reasons(sample_task, sample_sources)

        # 所有 reason 应保持不变
        for i, item in enumerate(sample_sources):
            assert item.reason_to_read == original_reasons[i]

    @pytest.mark.asyncio
    async def test_no_gateway_skips(self, sample_task, sample_sources):
        """没有 AI Gateway 时跳过。"""
        from services.research_service import ResearchService

        service = ResearchService(ai_gateway=None)
        original_reasons = [s.reason_to_read for s in sample_sources]

        await service._generate_source_reasons(sample_task, sample_sources)

        for i, item in enumerate(sample_sources):
            assert item.reason_to_read == original_reasons[i]
