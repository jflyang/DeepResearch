"""SourceItem / ExtractedDocument 语言元数据测试。"""

import pytest

from models.enums import LanguageCode
from models.schemas import ExtractedDocument, SourceItem


class TestSourceItemLanguageMetadata:
    """SourceItem 语言元数据字段测试。"""

    def test_query_language_en(self):
        """SourceItem 可包含 query_language=en。"""
        item = SourceItem(
            task_id="task-1",
            url="https://example.com/article",
            query_language=LanguageCode.EN,
        )
        assert item.query_language == LanguageCode.EN

    def test_source_language_en(self):
        item = SourceItem(
            task_id="task-1",
            url="https://example.com",
            source_language=LanguageCode.EN,
        )
        assert item.source_language == LanguageCode.EN

    def test_source_language_zh(self):
        item = SourceItem(
            task_id="task-1",
            url="https://example.cn",
            source_language=LanguageCode.ZH,
        )
        assert item.source_language == LanguageCode.ZH

    def test_matched_query(self):
        item = SourceItem(
            task_id="task-1",
            url="https://example.com",
            matched_query="Tim Cook childhood Robertsdale",
            query_language=LanguageCode.EN,
        )
        assert item.matched_query == "Tim Cook childhood Robertsdale"

    def test_canonical_and_original_topic(self):
        item = SourceItem(
            task_id="task-1",
            url="https://example.com",
            canonical_topic="Tim Cook childhood story",
            original_topic="库克的童年故事",
        )
        assert item.canonical_topic == "Tim Cook childhood story"
        assert item.original_topic == "库克的童年故事"

    def test_defaults_are_none(self):
        """新字段默认为 None，不影响旧构造方式。"""
        item = SourceItem(task_id="task-1", url="https://example.com")
        assert item.query_language is None
        assert item.source_language is None
        assert item.matched_query is None
        assert item.canonical_topic is None
        assert item.original_topic is None

    def test_backward_compatible_construction(self):
        """旧代码构造方式不受影响。"""
        item = SourceItem(
            task_id="task-1",
            title="Some Article",
            url="https://example.com/article",
            domain="example.com",
            snippet="A snippet",
            relevance_score=0.8,
        )
        assert item.title == "Some Article"
        assert item.relevance_score == 0.8
        # 新字段全部为 None
        assert item.query_language is None
        assert item.source_language is None

    def test_full_construction_with_language(self):
        """完整构造包含语言元数据。"""
        item = SourceItem(
            task_id="task-1",
            title="Tim Cook's Early Life",
            url="https://example.com/tim-cook",
            domain="example.com",
            snippet="Tim Cook grew up in Robertsdale...",
            relevance_score=0.9,
            query_language=LanguageCode.EN,
            source_language=LanguageCode.EN,
            matched_query="Tim Cook childhood Robertsdale Alabama",
            canonical_topic="Tim Cook childhood story",
            original_topic="库克的童年故事",
        )
        assert item.query_language == LanguageCode.EN
        assert item.source_language == LanguageCode.EN
        assert "Tim Cook" in item.matched_query


class TestExtractedDocumentLanguageMetadata:
    """ExtractedDocument 语言元数据字段测试。"""

    def test_original_language_en_summary_zh(self):
        """ExtractedDocument 可包含 original_language=en, summary_language=zh。"""
        doc = ExtractedDocument(
            source_item_id="item-1",
            original_language=LanguageCode.EN,
            summary_language=LanguageCode.ZH,
        )
        assert doc.original_language == LanguageCode.EN
        assert doc.summary_language == LanguageCode.ZH

    def test_translated_title(self):
        doc = ExtractedDocument(
            source_item_id="item-1",
            title="Tim Cook's Early Life in Alabama",
            translated_title="蒂姆·库克在阿拉巴马的早年生活",
            original_language=LanguageCode.EN,
        )
        assert doc.translated_title == "蒂姆·库克在阿拉巴马的早年生活"

    def test_canonical_and_original_topic(self):
        doc = ExtractedDocument(
            source_item_id="item-1",
            canonical_topic="Tim Cook childhood story",
            original_topic="库克的童年故事",
        )
        assert doc.canonical_topic == "Tim Cook childhood story"
        assert doc.original_topic == "库克的童年故事"

    def test_defaults_are_none(self):
        """新字段默认为 None，不影响旧构造方式。"""
        doc = ExtractedDocument(source_item_id="item-1")
        assert doc.original_language is None
        assert doc.summary_language is None
        assert doc.translated_title is None
        assert doc.canonical_topic is None
        assert doc.original_topic is None

    def test_backward_compatible_construction(self):
        """旧代码构造方式不受影响。"""
        doc = ExtractedDocument(
            source_item_id="item-1",
            title="Some Document",
            author="Author Name",
            content="Document content...",
            summary="A summary",
            people=["Person A"],
        )
        assert doc.title == "Some Document"
        assert doc.people == ["Person A"]
        # 新字段全部为 None
        assert doc.original_language is None
        assert doc.summary_language is None

    def test_inherits_language_from_source(self):
        """演示 original_language 可从 SourceItem.source_language 继承。"""
        source = SourceItem(
            task_id="task-1",
            url="https://example.com",
            source_language=LanguageCode.EN,
        )
        doc = ExtractedDocument(
            source_item_id=source.id,
            original_language=source.source_language,
            summary_language=LanguageCode.ZH,
        )
        assert doc.original_language == LanguageCode.EN
        assert doc.summary_language == LanguageCode.ZH


class TestNoDatabaseMigrationRequired:
    """验证不需要数据库迁移。"""

    def test_new_fields_are_optional(self):
        """所有新字段都是 Optional，默认 None。"""
        # SourceItem 只需 task_id + url
        item = SourceItem(task_id="t", url="http://x.com")
        assert item.query_language is None

        # ExtractedDocument 只需 source_item_id
        doc = ExtractedDocument(source_item_id="s")
        assert doc.original_language is None

    def test_serialization_excludes_none(self):
        """序列化时 None 字段可被排除（不影响 DB 写入）。"""
        item = SourceItem(task_id="t", url="http://x.com")
        data = item.model_dump(exclude_none=True)
        assert "query_language" not in data
        assert "source_language" not in data
        assert "matched_query" not in data

    def test_serialization_includes_when_set(self):
        """设置后序列化时包含。"""
        item = SourceItem(
            task_id="t",
            url="http://x.com",
            query_language=LanguageCode.EN,
        )
        data = item.model_dump(exclude_none=True)
        assert data["query_language"] == "en"
