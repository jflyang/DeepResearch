"""测试核心数据模型：枚举、schema 创建、默认值。"""

from datetime import UTC, datetime

import pytest

from models.enums import (
    CardType,
    Confidence,
    Depth,
    DownloadStatus,
    EntityType,
    Language,
    SearchSource,
    SourceLevel,
    SourceType,
    TaskMode,
    TaskStatus,
)
from models.schemas import (
    Entity,
    ExtractedDocument,
    ResearchCard,
    ResearchTask,
    SearchQuery,
    SourceItem,
)


# === Enum Tests ===


class TestEnums:
    def test_task_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_task_mode_values(self):
        assert set(TaskMode) == {"person", "company", "event", "concept", "auto"}

    def test_language_values(self):
        assert set(Language) == {"zh", "en", "mixed"}

    def test_depth_values(self):
        assert set(Depth) == {"shallow", "standard", "deep"}

    def test_search_source_values(self):
        assert "tavily" in set(SearchSource)
        assert "brave" in set(SearchSource)
        assert "google_books" in set(SearchSource)
        assert "youtube" in set(SearchSource)
        assert "archive" in set(SearchSource)

    def test_source_level_ordering(self):
        levels = list(SourceLevel)
        assert levels == ["S", "A", "B", "C", "D"]

    def test_download_status_values(self):
        assert DownloadStatus.PENDING == "pending"
        assert DownloadStatus.EXTRACTED == "extracted"
        assert DownloadStatus.SKIPPED == "skipped"

    def test_source_type_values(self):
        assert SourceType.ACADEMIC == "academic"
        assert SourceType.GOVERNMENT == "government"

    def test_entity_type_values(self):
        assert EntityType.PERSON == "person"
        assert EntityType.ORGANIZATION == "organization"

    def test_confidence_values(self):
        assert set(Confidence) == {
            "confirmed", "likely", "rumor", "unverified", "conflicting"
        }

    def test_card_type_values(self):
        assert CardType.FACT == "fact"
        assert CardType.TIMELINE == "timeline"


# === Schema Creation Tests ===


class TestResearchTask:
    def test_minimal_creation(self):
        task = ResearchTask(topic="量子计算")
        assert task.topic == "量子计算"
        assert task.id  # UUID 自动生成
        assert len(task.id) == 36

    def test_defaults(self):
        task = ResearchTask(topic="test")
        assert task.mode == TaskMode.AUTO
        assert task.language == Language.MIXED
        assert task.depth == Depth.STANDARD
        assert task.include_gossip is False
        assert task.include_books is True
        assert task.include_video is False
        assert task.status == TaskStatus.PENDING
        assert task.obsidian_path == ""
        assert task.completed_at is None

    def test_created_at_is_utc(self):
        task = ResearchTask(topic="test")
        assert task.created_at.tzinfo is not None

    def test_full_creation(self):
        task = ResearchTask(
            topic="Elon Musk",
            mode=TaskMode.PERSON,
            language=Language.EN,
            depth=Depth.DEEP,
            include_gossip=True,
            include_video=True,
        )
        assert task.mode == TaskMode.PERSON
        assert task.include_gossip is True


class TestSearchQuery:
    def test_minimal_creation(self):
        q = SearchQuery(task_id="abc-123", query="quantum computing basics")
        assert q.task_id == "abc-123"
        assert q.query == "quantum computing basics"

    def test_defaults(self):
        q = SearchQuery(task_id="x", query="test")
        assert q.source == SearchSource.TAVILY
        assert q.round == 1
        assert q.purpose == ""


class TestSourceItem:
    def test_minimal_creation(self):
        s = SourceItem(task_id="t1", url="https://example.com/article")
        assert s.url == "https://example.com/article"
        assert s.task_id == "t1"

    def test_defaults(self):
        s = SourceItem(task_id="t1", url="https://x.com")
        assert s.source_level == SourceLevel.C
        assert s.relevance_score == 0.0
        assert s.authority_score == 0.0
        assert s.originality_score == 0.0
        assert s.gossip_score == 0.0
        assert s.downloadable is True
        assert s.download_status == DownloadStatus.PENDING
        assert s.source_type == SourceType.OTHER

    def test_score_fields(self):
        s = SourceItem(
            task_id="t1",
            url="https://arxiv.org/abs/123",
            relevance_score=0.9,
            authority_score=0.95,
            source_level=SourceLevel.S,
        )
        assert s.relevance_score == 0.9
        assert s.source_level == SourceLevel.S


class TestExtractedDocument:
    def test_minimal_creation(self):
        doc = ExtractedDocument(source_item_id="s1")
        assert doc.source_item_id == "s1"

    def test_list_defaults(self):
        doc = ExtractedDocument(source_item_id="s1")
        assert doc.key_quotes == []
        assert doc.people == []
        assert doc.places == []
        assert doc.organizations == []
        assert doc.concepts == []
        assert doc.events == []

    def test_list_fields(self):
        doc = ExtractedDocument(
            source_item_id="s1",
            people=["Alice", "Bob"],
            concepts=["quantum entanglement"],
        )
        assert len(doc.people) == 2
        assert "quantum entanglement" in doc.concepts


class TestEntity:
    def test_minimal_creation(self):
        e = Entity(name="OpenAI")
        assert e.name == "OpenAI"

    def test_defaults(self):
        e = Entity(name="test")
        assert e.type == EntityType.OTHER
        assert e.importance_score == 0.0
        assert e.should_expand is False


class TestResearchCard:
    def test_minimal_creation(self):
        card = ResearchCard(task_id="t1")
        assert card.task_id == "t1"

    def test_defaults(self):
        card = ResearchCard(task_id="t1")
        assert card.type == CardType.FACT
        assert card.confidence == Confidence.UNVERIFIED
        assert card.linked_sources == []

    def test_full_creation(self):
        card = ResearchCard(
            task_id="t1",
            type=CardType.CONTROVERSY,
            title="争议点",
            content="内容",
            linked_sources=["s1", "s2"],
            confidence=Confidence.CONFLICTING,
        )
        assert card.confidence == Confidence.CONFLICTING
        assert len(card.linked_sources) == 2


# === ID Uniqueness ===


class TestIdUniqueness:
    def test_tasks_have_unique_ids(self):
        t1 = ResearchTask(topic="a")
        t2 = ResearchTask(topic="b")
        assert t1.id != t2.id

    def test_source_items_have_unique_ids(self):
        s1 = SourceItem(task_id="t", url="https://a.com")
        s2 = SourceItem(task_id="t", url="https://b.com")
        assert s1.id != s2.id
