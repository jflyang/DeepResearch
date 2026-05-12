"""研究资料包输出测试 - 验证完整资料包生成。

验证：
1. index.md 有真实摘要（不只是来源列表）
2. A/S 来源有 source note
3. 图书资料有中文解释
4. 时间线/人物/重点名词不再为空
5. filtered_noise.md 生成
6. trace_summary.md 生成
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.ai.schemas import DocumentAnalysisOutput
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
        id="test-pkg-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sources():
    return [
        SourceItem(
            id="s1",
            task_id="test-pkg-001",
            title="Tim Cook Biography - Early Life",
            url="https://example.com/cook-bio",
            domain="example.com",
            snippet="Tim Cook grew up in Robertsdale, Alabama",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.S,
            relevance_score=0.95,
            authority_score=0.9,
            reason_to_read="Detailed biography",
        ),
        SourceItem(
            id="s2",
            task_id="test-pkg-001",
            title="Interview with Tim Cook at Duke",
            url="https://duke.edu/cook-interview",
            domain="duke.edu",
            snippet="Cook discusses his childhood and values",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.A,
            relevance_score=0.85,
            authority_score=0.8,
            reason_to_read="First-hand interview",
        ),
        SourceItem(
            id="s3",
            task_id="test-pkg-001",
            title="Random Celebrity Gossip",
            url="https://gossip.example.com/random",
            domain="gossip.example.com",
            snippet="Unverified claims",
            source_type=SourceType.BLOG,
            source_level=SourceLevel.D,
            relevance_score=0.2,
            gossip_score=0.6,
            reason_to_read="Gossip",
        ),
    ]


@pytest.fixture
def mock_extraction_service():
    """Mock extraction that returns rich content."""
    service = MagicMock()

    async def mock_extract(source_item):
        source_item.download_status = DownloadStatus.EXTRACTED
        if "Biography" in source_item.title:
            return ExtractedDocument(
                source_item_id=source_item.id,
                title=source_item.title,
                author="John Smith",
                content="Tim Cook was born in 1960 in Robertsdale, Alabama. He grew up in a modest family. His father worked at a shipyard. Cook attended Robertsdale High School before going to Auburn University. " * 20,
                summary="Tim Cook 出生于 1960 年的 Alabama 州 Robertsdale 小镇。",
                people=["Tim Cook", "Steve Jobs", "Donald Cook"],
                places=["Robertsdale", "Alabama", "Auburn University"],
                concepts=["Apple", "Leadership", "Supply Chain"],
                key_quotes=["Cook grew up in a small town in Alabama"],
                events=["1960 年出生", "Auburn University 毕业"],
            )
        else:
            return ExtractedDocument(
                source_item_id=source_item.id,
                title=source_item.title,
                author="Duke University",
                content="In this interview, Tim Cook reflects on his childhood values and the importance of his upbringing in shaping his leadership style at Apple. " * 15,
                summary="Cook 在访谈中回忆了童年价值观对其领导风格的影响。",
                people=["Tim Cook"],
                places=["Duke University"],
                concepts=["Leadership", "Values"],
                key_quotes=["My parents taught me the value of hard work"],
            )

    service.extract_source = AsyncMock(side_effect=mock_extract)
    return service


class TestResearchPackageStructure:
    """资料包结构测试。"""

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
        index_path = Path(result.index_path)
        assert index_path.exists()
        assert index_path.name == "index.md"

    @pytest.mark.asyncio
    async def test_generates_source_notes(self, task, sources, mock_extraction_service, tmp_path):
        """A/S 来源有 source note。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        assert result.source_note_count == 2
        sources_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "sources"
        assert sources_dir.exists()
        md_files = list(sources_dir.glob("*.md"))
        assert len(md_files) == 2

    @pytest.mark.asyncio
    async def test_generates_filtered_noise(self, task, sources, mock_extraction_service, tmp_path):
        """生成 filtered_noise.md。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        await service.run(task=task, sources=sources, vault_path=tmp_path)

        noise_path = tmp_path / "Research" / "Tim_Cook_童年故事" / "filtered_noise.md"
        assert noise_path.exists()
        content = noise_path.read_text(encoding="utf-8")
        assert "被过滤" in content
        assert "Random Celebrity Gossip" in content

    @pytest.mark.asyncio
    async def test_generates_trace_summary(self, task, sources, mock_extraction_service, tmp_path):
        """生成 trace_summary.md。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        trace_path = tmp_path / "Research" / "Tim_Cook_童年故事" / "trace_summary.md"
        assert trace_path.exists()
        content = trace_path.read_text(encoding="utf-8")
        assert "执行摘要" in content
        assert "成功抓取" in content


class TestIndexContentQuality:
    """index.md 内容质量测试。"""

    @pytest.mark.asyncio
    async def test_index_has_real_overview(self, task, sources, mock_extraction_service, tmp_path):
        """index.md 有真实摘要（不只是来源列表）。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        content = Path(result.index_path).read_text(encoding="utf-8")
        assert "研究概览" in content
        assert "Tim Cook" in content
        # 应该有实质内容
        assert "已抓取并分析" in content or "共收集" in content

    @pytest.mark.asyncio
    async def test_index_people_not_empty(self, task, sources, mock_extraction_service, tmp_path):
        """人物不再为空。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        content = Path(result.index_path).read_text(encoding="utf-8")
        assert "关键人物" in content
        # 应该有从正文提取的人物
        assert "Tim Cook" in content
        assert "Steve Jobs" in content

    @pytest.mark.asyncio
    async def test_index_concepts_not_empty(self, task, sources, mock_extraction_service, tmp_path):
        """重点名词不再为空。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        content = Path(result.index_path).read_text(encoding="utf-8")
        assert "重点名词" in content
        assert "Apple" in content or "Leadership" in content

    @pytest.mark.asyncio
    async def test_index_places_from_extraction(self, task, sources, mock_extraction_service, tmp_path):
        """地点从正文提取。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        content = Path(result.index_path).read_text(encoding="utf-8")
        # 应该有从正文提取的地点
        assert "Robertsdale" in content or "Alabama" in content or "Auburn" in content

    @pytest.mark.asyncio
    async def test_index_not_just_source_list(self, task, sources, mock_extraction_service, tmp_path):
        """index.md 不只是来源列表。"""
        policy = _default_policy()
        policy["auto_analyze"]["enabled"] = False

        service = AutoFetchExportService(
            ai_gateway=None,
            extraction_service=mock_extraction_service,
            policy=policy,
        )

        result = await service.run(task=task, sources=sources, vault_path=tmp_path)

        content = Path(result.index_path).read_text(encoding="utf-8")

        # 应该有多个实质性部分
        sections = ["研究概览", "关键人物", "重点名词", "下一步深挖方向"]
        found = sum(1 for s in sections if s in content)
        assert found >= 3, f"Only {found}/4 sections found"

        # 内容应该足够丰富
        assert len(content) > 500
