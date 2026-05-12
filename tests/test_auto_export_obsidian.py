"""自动导出到 Obsidian 测试 - 验证 index.md 和 source notes 生成。"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from models.enums import DownloadStatus, SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from services.auto_fetch_service import (
    AutoFetchExportService,
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
        id="test-export-auto-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sources():
    return [
        SourceItem(
            id="s1",
            task_id="test-export-auto-001",
            title="Tim Cook Official Bio",
            url="https://apple.com/leadership/cook",
            domain="apple.com",
            snippet="Official biography of Tim Cook",
            source_type=SourceType.DOCUMENTATION,
            source_level=SourceLevel.S,
            relevance_score=0.95,
            authority_score=0.99,
            reason_to_read="Official source",
        ),
        SourceItem(
            id="s2",
            task_id="test-export-auto-001",
            title="Interview with Tim Cook at Stanford",
            url="https://stanford.edu/interview-cook",
            domain="stanford.edu",
            snippet="Q&A about early life",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.A,
            relevance_score=0.85,
            authority_score=0.8,
            reason_to_read="First-hand account",
        ),
        SourceItem(
            id="s3",
            task_id="test-export-auto-001",
            title="Random Blog",
            url="https://blog.example.com/random",
            domain="blog.example.com",
            snippet="Random content",
            source_type=SourceType.BLOG,
            source_level=SourceLevel.C,
            relevance_score=0.3,
            reason_to_read="Blog",
        ),
    ]


@pytest.fixture
def mock_extraction_service():
    """Mock extraction service."""
    service = MagicMock()

    async def mock_extract(source_item):
        source_item.download_status = DownloadStatus.EXTRACTED
        return ExtractedDocument(
            source_item_id=source_item.id,
            title=source_item.title,
            author="Test Author",
            content=f"This is the full text content for {source_item.title}. " * 100,
            summary="A comprehensive article about Tim Cook.",
            people=["Tim Cook", "Steve Jobs"],
            places=["Alabama", "Cupertino"],
            concepts=["Apple", "Leadership", "Supply Chain"],
            key_quotes=["Cook said: 'I grew up in a small town.'"],
        )

    service.extract_source = AsyncMock(side_effect=mock_extract)
    return service


class TestAutoExportWithVault:
    """auto_export enabled 且 Vault 可用时生成文件。"""

    @pytest.mark.asyncio
    async def test_generates_index_md(self, task, sources, mock_extraction_service, tmp_path):
        """生成 index.md。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        assert result.exported
        assert result.index_path
        index_path = Path(result.index_path)
        assert index_path.exists()
        assert index_path.name == "index.md"

    @pytest.mark.asyncio
    async def test_generates_source_notes(self, task, sources, mock_extraction_service, tmp_path):
        """生成 source notes。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        assert result.source_note_count == 2  # S + A sources
        # 验证 source notes 文件存在
        sources_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "sources"
        if sources_dir.exists():
            md_files = list(sources_dir.glob("*.md"))
            assert len(md_files) == 2

    @pytest.mark.asyncio
    async def test_index_contains_fetch_results(self, task, sources, mock_extraction_service, tmp_path):
        """index.md 包含抓取和分析结果。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        index_path = Path(result.index_path)
        content = index_path.read_text(encoding="utf-8")

        # index.md 应包含来源信息
        assert "Tim Cook" in content
        assert "研究概览" in content or "必读资料" in content


class TestAutoExportWithoutVault:
    """Vault 不可用时的行为。"""

    @pytest.mark.asyncio
    async def test_no_vault_does_not_fail(self, task, sources, mock_extraction_service):
        """Vault 不可用时记录 warning，不导致研究失败。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        # 传入不存在的路径
        fake_vault = Path("/nonexistent/vault/path")
        result = await service.run(task=task, sources=sources, vault_path=fake_vault)

        # 抓取仍然成功
        assert result.fetched_count == 2
        # 导出失败但不抛异常
        assert not result.exported

    @pytest.mark.asyncio
    async def test_export_disabled_still_fetches(self, task, sources, mock_extraction_service, tmp_path):
        """auto_export disabled 时仍然抓取。"""
        policy = _default_policy()
        policy["auto_export"]["enabled"] = False
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        assert result.fetched_count == 2
        assert not result.exported
        assert result.source_note_count == 0


class TestAutoExportContent:
    """导出内容质量测试。"""

    @pytest.mark.asyncio
    async def test_source_note_has_content(self, task, sources, mock_extraction_service, tmp_path):
        """source note 包含正文内容。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        # 找到 source notes
        sources_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "sources"
        if sources_dir.exists():
            md_files = list(sources_dir.glob("*.md"))
            assert len(md_files) > 0
            # 检查第一个 source note 内容
            content = md_files[0].read_text(encoding="utf-8")
            assert len(content) > 100
            assert "Tim Cook" in content

    @pytest.mark.asyncio
    async def test_index_has_extracted_info(self, task, sources, mock_extraction_service, tmp_path):
        """index.md 包含从正文提取的信息。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        index_path = Path(result.index_path)
        content = index_path.read_text(encoding="utf-8")

        # 应该有从 extracted docs 获取的人物信息
        assert "Tim Cook" in content
        # 应该标记内容已提取（frontmatter）
        assert "content_extracted: True" in content
        # 应该有从 extracted docs 获取的概念
        assert "Steve Jobs" in content or "Apple" in content
