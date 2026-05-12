"""测试研究合成 API 路由逻辑。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.research_service import synthesize_research_task


# === Fixtures ===


def _mock_task_row(status="completed", topic="测试主题"):
    row = MagicMock()
    row.id = "task-001"
    row.topic = topic
    row.canonical_topic = None
    row.mode = "person"
    row.status = status
    row.obsidian_path = "/vault"
    return row


def _mock_source_rows(count=3, extracted_count=2):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.id = f"src-{i}"
        row.task_id = "task-001"
        row.download_status = "extracted" if i < extracted_count else "pending"
        row.source_level = "A"
        rows.append(row)
    return rows


# === Tests ===


class TestNoExtractedDocuments:
    """没有 ExtractedDocument 时 synthesize 返回明确错误。"""

    @pytest.mark.asyncio
    async def test_no_extracted_returns_error(self):
        """没有已抓取文档时返回错误信息。"""
        with patch("app.services.research_service._get_task_and_sources") as mock_get:
            mock_get.return_value = (_mock_task_row(), _mock_source_rows(count=3, extracted_count=0))

            result = await synthesize_research_task("task-001")

        assert result.get("error") is not None
        assert "抓取" in result["error"]
        assert result.get("synthesized") is not True

    @pytest.mark.asyncio
    async def test_task_not_found_returns_error(self):
        """task 不存在时返回错误。"""
        with patch("app.services.research_service._get_task_and_sources") as mock_get:
            mock_get.return_value = (None, [])

            result = await synthesize_research_task("nonexistent")

        assert result.get("error") is not None


class TestWithExtractedDocuments:
    """有 ExtractedDocument 时调用 synthesis service。"""

    @pytest.mark.asyncio
    async def test_calls_synthesis_service(self):
        """有已抓取文档时调用 ResearchSynthesisService。"""
        from models.schemas import SynthesizedResearchDocument

        mock_synthesis = SynthesizedResearchDocument(
            task_id="task-001",
            topic="测试主题",
            overview="研究概览",
            executive_summary="核心摘要",
            generated_at="2025-01-15 10:00",
        )

        with patch("app.services.research_service._get_task_and_sources") as mock_get, \
             patch("app.services.research_service._run_synthesis") as mock_run, \
             patch("app.services.research_service._write_index") as mock_write:

            mock_get.return_value = (_mock_task_row(), _mock_source_rows(count=3, extracted_count=2))
            mock_run.return_value = mock_synthesis
            mock_write.return_value = "/vault/Research/测试主题/index.md"

            result = await synthesize_research_task("task-001")

        assert result["synthesized"] is True
        mock_run.assert_called_once()


class TestSuccessReturnsIndexPath:
    """成功返回 index_path。"""

    @pytest.mark.asyncio
    async def test_returns_index_path(self):
        """成功时返回 index_path。"""
        from models.schemas import SynthesizedResearchDocument

        mock_synthesis = SynthesizedResearchDocument(
            task_id="task-001",
            topic="测试主题",
            generated_at="2025-01-15 10:00",
        )

        with patch("app.services.research_service._get_task_and_sources") as mock_get, \
             patch("app.services.research_service._run_synthesis") as mock_run, \
             patch("app.services.research_service._write_index") as mock_write:

            mock_get.return_value = (_mock_task_row(), _mock_source_rows(extracted_count=2))
            mock_run.return_value = mock_synthesis
            mock_write.return_value = "/vault/Research/测试主题/index.md"

            result = await synthesize_research_task("task-001")

        assert result["index_path"] == "/vault/Research/测试主题/index.md"
        assert result["task_id"] == "task-001"


class TestSynthesisFailure:
    """synthesis 失败时返回错误但不破坏 task。"""

    @pytest.mark.asyncio
    async def test_synthesis_failure_returns_error(self):
        """合成失败时返回错误信息。"""
        with patch("app.services.research_service._get_task_and_sources") as mock_get, \
             patch("app.services.research_service._run_synthesis") as mock_run:

            mock_get.return_value = (_mock_task_row(), _mock_source_rows(extracted_count=2))
            mock_run.side_effect = RuntimeError("LLM 全部失败")

            result = await synthesize_research_task("task-001")

        assert result.get("error") is not None
        assert result.get("synthesized") is not True


class TestNoFullContentInResponse:
    """API 不返回完整正文。"""

    @pytest.mark.asyncio
    async def test_no_content_in_result(self):
        """返回结果中不包含完整正文。"""
        from models.schemas import SynthesizedResearchDocument

        mock_synthesis = SynthesizedResearchDocument(
            task_id="task-001",
            topic="测试主题",
            overview="概览" * 100,
            generated_at="2025-01-15 10:00",
        )

        with patch("app.services.research_service._get_task_and_sources") as mock_get, \
             patch("app.services.research_service._run_synthesis") as mock_run, \
             patch("app.services.research_service._write_index") as mock_write:

            mock_get.return_value = (_mock_task_row(), _mock_source_rows(extracted_count=2))
            mock_run.return_value = mock_synthesis
            mock_write.return_value = "/vault/Research/测试主题/index.md"

            result = await synthesize_research_task("task-001")

        # 结果中不应有 overview 全文或 content 字段
        assert "content" not in result
        assert len(str(result)) < 2000  # 结果应该是摘要性的
