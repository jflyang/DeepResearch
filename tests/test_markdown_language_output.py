"""Markdown 导出语言元数据和双语结构测试。"""

import yaml
import pytest

from models.enums import (
    DownloadStatus,
    LanguageCode,
    SourceLevel,
    SourceType,
)
from models.schemas import ExtractedDocument, SourceItem
from services.markdown_service import export_source_note


@pytest.fixture
def tmp_vault(tmp_path):
    return tmp_path / "vault"


@pytest.fixture
def en_source_item():
    """英文来源 SourceItem，带语言元数据。"""
    return SourceItem(
        task_id="task-1",
        title="Tim Cook's Early Life in Alabama",
        url="https://example.com/tim-cook-early-life",
        domain="example.com",
        snippet="Tim Cook grew up in Robertsdale...",
        source_type=SourceType.NEWS,
        source_level=SourceLevel.A,
        relevance_score=0.9,
        reason_to_read="一手传记资料，描述 Tim Cook 童年细节",
        download_status=DownloadStatus.EXTRACTED,
        # 语言元数据
        query_language=LanguageCode.EN,
        source_language=LanguageCode.EN,
        matched_query="Tim Cook childhood Robertsdale Alabama",
        canonical_topic="Tim Cook childhood story",
        original_topic="库克的童年故事",
    )


@pytest.fixture
def en_extracted_doc(en_source_item):
    """英文提取文档，带中文摘要语言标记。"""
    return ExtractedDocument(
        source_item_id=en_source_item.id,
        title="Tim Cook's Early Life in Alabama",
        author="John Doe",
        content=(
            "Tim Cook grew up in Robertsdale, Alabama, a small town in the southern part "
            "of the state. His father, Donald Cook, worked at a shipyard, and his mother, "
            "Geraldine Cook, worked at a pharmacy. Cook attended Robertsdale High School "
            "where he was valedictorian of his class in 1978."
        ),
        summary="Tim Cook 在阿拉巴马州小镇 Robertsdale 长大，父亲在船厂工作，母亲在药房工作。他是 1978 年高中毕业班的第一名。",
        key_quotes=["Cook attended Robertsdale High School where he was valedictorian"],
        people=["Tim Cook", "Donald Cook", "Geraldine Cook"],
        places=["Robertsdale", "Alabama"],
        organizations=["Robertsdale High School"],
        concepts=["valedictorian"],
        # 语言元数据
        original_language=LanguageCode.EN,
        summary_language=LanguageCode.ZH,
        canonical_topic="Tim Cook childhood story",
        original_topic="库克的童年故事",
    )


@pytest.fixture
def legacy_source_item():
    """旧版 SourceItem，无语言字段。"""
    return SourceItem(
        task_id="task-2",
        title="Quantum Computing Overview",
        url="https://example.com/quantum",
        domain="example.com",
        source_type=SourceType.ACADEMIC,
        source_level=SourceLevel.B,
        reason_to_read="Good overview",
        download_status=DownloadStatus.EXTRACTED,
    )


@pytest.fixture
def legacy_extracted_doc(legacy_source_item):
    """旧版 ExtractedDocument，无语言字段。"""
    return ExtractedDocument(
        source_item_id=legacy_source_item.id,
        title="Quantum Computing Basics",
        content="Quantum computing uses qubits instead of classical bits.",
        summary="",
        key_quotes=["qubits instead of classical bits"],
        people=["Richard Feynman"],
        places=["MIT"],
        concepts=["qubit", "superposition"],
    )


class TestBilingualOutput:
    """英文 source + 中文 output 双语结构测试。"""

    def test_generates_bilingual_structure(self, tmp_vault, en_source_item, en_extracted_doc):
        """生成"中文摘要"和"原文正文"章节。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")

        assert "# 中文摘要" in content
        assert "# 原文正文" in content

    def test_chinese_summary_present(self, tmp_vault, en_source_item, en_extracted_doc):
        """中文摘要内容存在。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")

        # 中文摘要应包含中文内容
        assert "Tim Cook 在阿拉巴马州" in content

    def test_original_content_preserved(self, tmp_vault, en_source_item, en_extracted_doc):
        """原文正文没有被翻译覆盖。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")

        # 英文原文完整保留
        assert "Tim Cook grew up in Robertsdale, Alabama" in content
        assert "Donald Cook, worked at a shipyard" in content
        assert "valedictorian of his class in 1978" in content

    def test_has_source_info_section(self, tmp_vault, en_source_item, en_extracted_doc):
        """包含原文信息章节。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")

        assert "# 原文信息" in content
        assert "原文语言" in content
        assert "匹配 query" in content


class TestFrontmatterLanguageMetadata:
    """Frontmatter 语言元数据测试。"""

    def test_contains_source_language(self, tmp_vault, en_source_item, en_extracted_doc):
        """frontmatter 包含 source_language=en。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert fm["source_language"] == "en"

    def test_contains_output_language(self, tmp_vault, en_source_item, en_extracted_doc):
        """frontmatter 包含 output_language=zh。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert fm["output_language"] == "zh"

    def test_contains_query_language(self, tmp_vault, en_source_item, en_extracted_doc):
        """frontmatter 包含 query_language。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert fm["query_language"] == "en"

    def test_contains_original_topic(self, tmp_vault, en_source_item, en_extracted_doc):
        """frontmatter 包含 original_topic。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert fm["original_topic"] == "库克的童年故事"

    def test_contains_canonical_topic(self, tmp_vault, en_source_item, en_extracted_doc):
        """frontmatter 包含 canonical_topic。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert fm["canonical_topic"] == "Tim Cook childhood story"

    def test_contains_matched_query(self, tmp_vault, en_source_item, en_extracted_doc):
        """frontmatter 包含 matched_query。"""
        path = export_source_note(
            en_source_item, en_extracted_doc, "库克的童年故事", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert fm["matched_query"] == "Tim Cook childhood Robertsdale Alabama"


class TestBackwardCompatibility:
    """旧文档无语言字段时仍通过。"""

    def test_legacy_source_generates_file(self, tmp_vault, legacy_source_item, legacy_extracted_doc):
        """旧版 SourceItem 仍能正常导出。"""
        path = export_source_note(
            legacy_source_item, legacy_extracted_doc, "Quantum Computing", vault_path=tmp_vault
        )
        assert path.exists()

    def test_legacy_uses_old_structure(self, tmp_vault, legacy_source_item, legacy_extracted_doc):
        """旧版使用原有结构（# 摘要 / # 正文）。"""
        path = export_source_note(
            legacy_source_item, legacy_extracted_doc, "Quantum Computing", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")

        assert "# 摘要" in content
        assert "# 正文" in content
        # 不应出现双语结构
        assert "# 中文摘要" not in content
        assert "# 原文正文" not in content

    def test_legacy_frontmatter_no_language_fields(self, tmp_vault, legacy_source_item, legacy_extracted_doc):
        """旧版 frontmatter 不包含语言字段。"""
        path = export_source_note(
            legacy_source_item, legacy_extracted_doc, "Quantum Computing", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert "source_language" not in fm
        assert "output_language" not in fm
        assert "query_language" not in fm

    def test_legacy_valid_yaml(self, tmp_vault, legacy_source_item, legacy_extracted_doc):
        """旧版 frontmatter 仍是合法 YAML。"""
        path = export_source_note(
            legacy_source_item, legacy_extracted_doc, "Quantum Computing", vault_path=tmp_vault
        )
        content = path.read_text(encoding="utf-8")
        parts = content.split("---")
        fm = yaml.safe_load(parts[1])

        assert isinstance(fm, dict)
        assert fm["title"] == "Quantum Computing Basics"
