"""Markdown 研究索引导出测试。"""

from pathlib import Path

import pytest

from models.enums import SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from services.markdown_service import export_research_index


@pytest.fixture
def task():
    return ResearchTask(
        id="test-export-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sources():
    return [
        SourceItem(
            id="s1",
            task_id="test-export-001",
            title="Apple Leadership Tim Cook",
            url="https://apple.com/leadership",
            domain="apple.com",
            snippet="Official bio",
            source_type=SourceType.DOCUMENTATION,
            source_level=SourceLevel.S,
            relevance_score=0.95,
            authority_score=0.99,
            reason_to_read="Official source",
        ),
        SourceItem(
            id="s2",
            task_id="test-export-001",
            title="Tim Cook: The Genius Who Took Apple to the Next Level",
            url="https://books.example.com/cook",
            domain="books.example.com",
            snippet="A biography book",
            source_type=SourceType.BOOK,
            source_level=SourceLevel.A,
            relevance_score=0.8,
            authority_score=0.7,
            reason_to_read="Comprehensive biography",
        ),
        SourceItem(
            id="s3",
            task_id="test-export-001",
            title="Unverified rumors about Cook childhood",
            url="https://gossip.example.com/cook",
            domain="gossip.example.com",
            snippet="Unverified claims about early life",
            source_type=SourceType.BLOG,
            source_level=SourceLevel.C,
            gossip_score=0.7,
            reason_to_read="Gossip lead",
        ),
        SourceItem(
            id="s4",
            task_id="test-export-001",
            title="Interview with Tim Cook at Stanford",
            url="https://stanford.edu/interview",
            domain="stanford.edu",
            snippet="Q&A session about his early life",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.A,
            relevance_score=0.85,
            authority_score=0.8,
            reason_to_read="First-hand account",
        ),
    ]


class TestExportResearchIndex:
    def test_generates_index_file(self, task, sources, tmp_path) -> None:
        """生成 index.md 文件。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        assert path.exists()
        assert path.name == "index.md"

    def test_index_not_empty(self, task, sources, tmp_path) -> None:
        """index.md 不为空。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert len(content) > 100

    def test_s_a_sources_in_must_read(self, task, sources, tmp_path) -> None:
        """S/A 来源出现在必读资料。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "必读资料" in content
        assert "Apple Leadership" in content

    def test_book_sources_in_books(self, task, sources, tmp_path) -> None:
        """book 来源出现在图书资料。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "图书资料" in content
        assert "Genius" in content or "Tim Cook" in content

    def test_gossip_sources_in_gossip(self, task, sources, tmp_path) -> None:
        """C/gossip 来源出现在八卦与旁证。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "八卦" in content or "gossip" in content.lower()

    def test_yaml_frontmatter_present(self, task, sources, tmp_path) -> None:
        """YAML frontmatter 存在。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---")
        # 找到第二个 ---
        second_dash = content.index("---", 3)
        assert second_dash > 3

    def test_frontmatter_has_required_fields(self, task, sources, tmp_path) -> None:
        """frontmatter 包含必要字段。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "title:" in content
        assert "status:" in content
        assert "total_sources:" in content

    def test_topic_in_title(self, task, sources, tmp_path) -> None:
        """主题出现在标题中。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "Tim Cook" in content

    def test_interview_in_interviews(self, task, sources, tmp_path) -> None:
        """interview 来源出现在访谈资料。"""
        path = export_research_index(task, sources, {}, vault_path=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "访谈" in content or "Interview" in content
