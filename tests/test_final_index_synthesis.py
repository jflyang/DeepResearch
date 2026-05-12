"""final_index_synthesis 测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from models.enums import SourceLevel, SourceType
from models.schemas import SourceItem


@pytest.fixture
def sample_sources():
    return [
        SourceItem(
            id="s1", task_id="t1", title="High Quality Source",
            url="https://example.com/1", source_level=SourceLevel.S,
            source_type=SourceType.NEWS, reason_to_read="Important source",
        ),
        SourceItem(
            id="s2", task_id="t1", title="Good Source",
            url="https://example.com/2", source_level=SourceLevel.A,
            source_type=SourceType.BOOK, reason_to_read="Book source",
        ),
        SourceItem(
            id="s3", task_id="t1", title="Average Source",
            url="https://example.com/3", source_level=SourceLevel.B,
            source_type=SourceType.BLOG, reason_to_read="Blog",
        ),
    ]


class TestFinalIndexSynthesis:
    """final_index_synthesis 测试。"""

    @pytest.mark.asyncio
    async def test_generates_with_gateway(self, sample_sources):
        """有 AI Gateway 时应调用 LLM 生成概览。"""
        from services.markdown_service import generate_index_synthesis

        mock_gateway = MagicMock()
        mock_gateway.run_text = AsyncMock(return_value="## 研究概览\n\n这是 LLM 生成的研究概览。")

        result = await generate_index_synthesis(
            topic="Test Topic",
            mode="person",
            sources=sample_sources,
            ai_gateway=mock_gateway,
        )

        assert "研究概览" in result
        mock_gateway.run_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_without_gateway(self, sample_sources):
        """没有 AI Gateway 时返回规则生成的概览。"""
        from services.markdown_service import generate_index_synthesis

        result = await generate_index_synthesis(
            topic="Test Topic",
            mode="person",
            sources=sample_sources,
            ai_gateway=None,
        )

        assert "研究概览" in result
        assert "Test Topic" in result
        assert "3" in result  # total sources

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self, sample_sources):
        """LLM 失败时返回规则生成的概览。"""
        from services.markdown_service import generate_index_synthesis

        mock_gateway = MagicMock()
        mock_gateway.run_text = AsyncMock(side_effect=Exception("API error"))

        result = await generate_index_synthesis(
            topic="Test Topic",
            mode="person",
            sources=sample_sources,
            ai_gateway=mock_gateway,
        )

        # 应返回 fallback
        assert "研究概览" in result
        assert "Test Topic" in result

    @pytest.mark.asyncio
    async def test_rule_based_includes_stats(self, sample_sources):
        """规则生成的概览应包含统计信息。"""
        from services.markdown_service import _rule_based_index_synthesis

        result = _rule_based_index_synthesis("Test Topic", "person", sample_sources)

        assert "Test Topic" in result
        assert "3" in result  # total
        assert "2" in result  # high quality (S + A)
