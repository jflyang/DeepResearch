"""markdown_summary_generation 测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestMarkdownSummaryGeneration:
    """markdown_summary_generation 测试。"""

    @pytest.mark.asyncio
    async def test_generates_summary_with_gateway(self):
        """有 AI Gateway 时应调用 LLM 生成摘要。"""
        from services.markdown_service import generate_markdown_summary

        mock_gateway = MagicMock()
        mock_gateway.run_text = AsyncMock(return_value="## 摘要\n\n这是 LLM 生成的摘要。\n\n## 关键要点\n\n- 要点1")

        result = await generate_markdown_summary(
            title="Test Article",
            content="A" * 500,
            topic="Test Topic",
            level="A",
            ai_gateway=mock_gateway,
        )

        assert "LLM 生成的摘要" in result
        mock_gateway.run_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_without_gateway(self):
        """没有 AI Gateway 时返回截取摘要。"""
        from services.markdown_service import generate_markdown_summary

        content = "Hello world " * 50  # 600 chars
        result = await generate_markdown_summary(
            title="Test",
            content=content,
            topic="Test",
            ai_gateway=None,
        )

        assert len(result) <= 210  # 200 + "..."
        assert result.endswith("...")

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self):
        """LLM 失败时返回截取摘要。"""
        from services.markdown_service import generate_markdown_summary

        mock_gateway = MagicMock()
        mock_gateway.run_text = AsyncMock(side_effect=Exception("timeout"))

        content = "Content " * 100
        result = await generate_markdown_summary(
            title="Test",
            content=content,
            topic="Test",
            ai_gateway=mock_gateway,
        )

        # 应返回 fallback（截取）
        assert len(result) <= 210

    @pytest.mark.asyncio
    async def test_short_content_no_truncation(self):
        """短内容不截断。"""
        from services.markdown_service import generate_markdown_summary

        result = await generate_markdown_summary(
            title="Test",
            content="Short content",
            topic="Test",
            ai_gateway=None,
        )

        assert result == "Short content"
