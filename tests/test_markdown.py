"""Markdown 导出模块测试。"""

import tempfile
from pathlib import Path

import pytest
import yaml

from core.config import Settings, reset_settings
from core.errors import ResearchError
from models.enums import DownloadStatus, SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from services.markdown_service import export_research_index, export_source_note
from utils.filesystem import ensure_unique_path, sanitize_filename


# === 文件名清洗测试 ===


class TestSanitizeFilename:
    def test_removes_illegal_chars(self):
        assert sanitize_filename('file<>:"/\\|?*name') == "filename"

    def test_replaces_spaces_with_underscore(self):
        assert sanitize_filename("hello world test") == "hello_world_test"

    def test_limits_length(self):
        long_name = "a" * 200
        result = sanitize_filename(long_name, max_length=120)
        assert len(result) <= 120

    def test_strips_dots_and_underscores(self):
        assert sanitize_filename("...test___") == "test"

    def test_empty_returns_untitled(self):
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("***") == "untitled"

    def test_collapses_multiple_spaces(self):
        assert sanitize_filename("hello   world") == "hello_world"

    def test_preserves_unicode(self):
        result = sanitize_filename("量子计算研究")
        assert "量子计算研究" in result

    def test_custom_max_length(self):
        result = sanitize_filename("a" * 50, max_length=30)
        assert len(result) <= 30


class TestEnsureUniquePath:
    def test_returns_same_if_not_exists(self, tmp_path):
        path = tmp_path / "new_file.md"
        assert ensure_unique_path(path) == path

    def test_adds_suffix_if_exists(self, tmp_path):
        path = tmp_path / "existing.md"
        path.write_text("content")

        unique = ensure_unique_path(path)
        assert unique != path
        assert unique.stem == "existing_1"
        assert unique.suffix == ".md"

    def test_increments_suffix(self, tmp_path):
        path = tmp_path / "file.md"
        path.write_text("v1")
        (tmp_path / "file_1.md").write_text("v2")

        unique = ensure_unique_path(path)
        assert unique.stem == "file_2"


# === Fixtures ===


@pytest.fixture
def tmp_vault(tmp_path):
    return tmp_path / "vault"


@pytest.fixture
def source_item():
    return SourceItem(
        task_id="task-1",
        title="Quantum Computing Overview",
        url="https://arxiv.org/abs/2301.00001",
        domain="arxiv.org",
        snippet="A comprehensive overview",
        source_type=SourceType.ACADEMIC,
        source_level=SourceLevel.S,
        relevance_score=0.9,
        authority_score=0.95,
        originality_score=0.9,
        gossip_score=0.0,
        reason_to_read="[S] Primary academic source",
        download_status=DownloadStatus.EXTRACTED,
    )


@pytest.fixture
def extracted_doc(source_item):
    return ExtractedDocument(
        source_item_id=source_item.id,
        title="The History of Quantum Computing",
        author="Dr. Alice Smith",
        content="Quantum computing represents a fundamentally different approach. "
        "The field originated in the early 1980s when physicist Richard Feynman "
        "proposed that quantum systems could simulate other quantum systems.",
        summary="Overview of quantum computing history.",
        key_quotes=["quantum systems could simulate other quantum systems"],
        people=["Richard Feynman", "Peter Shor"],
        places=["MIT", "Caltech"],
        organizations=["IBM", "Google"],
        concepts=["qubit", "superposition", "quantum supremacy"],
        events=["Shor's algorithm 1994"],
    )


@pytest.fixture
def research_task():
    return ResearchTask(
        topic="Quantum Computing",
        mode=TaskMode.CONCEPT,
        status=TaskStatus.COMPLETED,
    )


# === 单篇导出测试 ===


class TestExportSourceNote:
    def test_creates_file(self, tmp_vault, source_item, extracted_doc):
        path = export_source_note(source_item, extracted_doc, "Quantum Computing", vault_path=tmp_vault)
        assert path.exists()
        assert path.suffix == ".md"

    def test_file_in_correct_directory(self, tmp_vault, source_item, extracted_doc):
        path = export_source_note(source_item, extracted_doc, "Quantum Computing", vault_path=tmp_vault)
        assert "Research" in str(path)
        assert "sources" in str(path)

    def test_frontmatter_is_valid_yaml(self, tmp_vault, source_item, extracted_doc):
        path = export_source_note(source_item, extracted_doc, "Quantum Computing", vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        # 提取 frontmatter
        parts = content.split("---")
        assert len(parts) >= 3, "Should have YAML frontmatter delimiters"
        frontmatter_str = parts[1]

        # 验证是合法 YAML
        fm = yaml.safe_load(frontmatter_str)
        assert isinstance(fm, dict)
        assert fm["title"] == "The History of Quantum Computing"
        assert fm["url"] == "https://arxiv.org/abs/2301.00001"
        assert fm["source_level"] == "S"
        assert fm["source_type"] == "academic"
        assert fm["topic"] == "Quantum Computing"

    def test_contains_content_sections(self, tmp_vault, source_item, extracted_doc):
        path = export_source_note(source_item, extracted_doc, "Quantum Computing", vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        assert "# 摘要" in content
        assert "# 为什么值得看" in content
        assert "# 关键摘录" in content
        assert "# 相关人物" in content
        assert "# 正文" in content
        assert "# 原始链接" in content

    def test_contains_extracted_content(self, tmp_vault, source_item, extracted_doc):
        path = export_source_note(source_item, extracted_doc, "Quantum Computing", vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        assert "Richard Feynman" in content
        assert "quantum systems" in content

    def test_updates_markdown_path(self, tmp_vault, source_item, extracted_doc):
        path = export_source_note(source_item, extracted_doc, "Quantum Computing", vault_path=tmp_vault)
        assert extracted_doc.markdown_path == str(path)

    def test_updates_download_status(self, tmp_vault, source_item, extracted_doc):
        export_source_note(source_item, extracted_doc, "Quantum Computing", vault_path=tmp_vault)
        assert source_item.download_status == DownloadStatus.EXPORTED

    def test_no_vault_path_raises_error(self, source_item, extracted_doc):
        """未配置 vault 路径时报明确错误。"""
        from unittest.mock import patch

        with patch("services.markdown_service.get_settings") as mock_settings:
            mock_settings.return_value.obsidian_configured = False
            with pytest.raises(ResearchError, match="Obsidian vault path not configured"):
                export_source_note(source_item, extracted_doc, "Test")

    def test_duplicate_filename_gets_suffix(self, tmp_vault, source_item, extracted_doc):
        # 导出两次相同标题
        path1 = export_source_note(source_item, extracted_doc, "Test", vault_path=tmp_vault)
        path2 = export_source_note(source_item, extracted_doc, "Test", vault_path=tmp_vault)
        assert path1 != path2
        assert path2.exists()


# === 研究索引页测试 ===


class TestExportResearchIndex:
    def test_creates_index_file(self, tmp_vault, research_task, source_item, extracted_doc):
        sources = [source_item]
        docs = {source_item.id: extracted_doc}

        path = export_research_index(research_task, sources, docs, vault_path=tmp_vault)
        assert path.exists()
        assert path.name == "index.md"

    def test_index_contains_topic(self, tmp_vault, research_task, source_item, extracted_doc):
        sources = [source_item]
        docs = {source_item.id: extracted_doc}

        path = export_research_index(research_task, sources, docs, vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        assert "Quantum Computing" in content
        assert "研究索引" in content

    def test_index_has_valid_frontmatter(self, tmp_vault, research_task, source_item, extracted_doc):
        sources = [source_item]
        docs = {source_item.id: extracted_doc}

        path = export_research_index(research_task, sources, docs, vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        parts = content.split("---")
        assert len(parts) >= 3
        fm = yaml.safe_load(parts[1])
        assert fm["total_sources"] == 1
        assert "research-index" in fm["tags"]

    def test_index_lists_must_read(self, tmp_vault, research_task, source_item, extracted_doc):
        sources = [source_item]
        docs = {source_item.id: extracted_doc}

        path = export_research_index(research_task, sources, docs, vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        assert "## 必读资料" in content
        assert "Quantum_Computing_Overview" in content or "Quantum Computing Overview" in content

    def test_index_lists_people(self, tmp_vault, research_task, source_item, extracted_doc):
        sources = [source_item]
        docs = {source_item.id: extracted_doc}

        path = export_research_index(research_task, sources, docs, vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        assert "Richard Feynman" in content
        assert "Peter Shor" in content

    def test_index_lists_concepts(self, tmp_vault, research_task, source_item, extracted_doc):
        sources = [source_item]
        docs = {source_item.id: extracted_doc}

        path = export_research_index(research_task, sources, docs, vault_path=tmp_vault)
        content = path.read_text(encoding="utf-8")

        assert "qubit" in content
        assert "superposition" in content

    def test_empty_sources(self, tmp_vault, research_task):
        path = export_research_index(research_task, [], {}, vault_path=tmp_vault)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "total_sources: 0" in content
