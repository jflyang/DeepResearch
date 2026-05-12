"""Pydantic 业务层数据模型 - 模块间数据契约。"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

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


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


# === ResearchTask ===


class ResearchTask(BaseModel):
    model_config = {"validate_assignment": True}

    id: str = Field(default_factory=_uuid)
    topic: str
    mode: TaskMode = TaskMode.AUTO
    language: Language = Language.MIXED
    depth: Depth = Depth.STANDARD
    include_gossip: bool = False
    include_books: bool = True
    include_video: bool = False
    status: TaskStatus = TaskStatus.PENDING
    obsidian_path: str = ""
    expanded_queries: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None


# === SearchQuery ===


class SearchQuery(BaseModel):
    id: str = Field(default_factory=_uuid)
    task_id: str
    query: str
    source: SearchSource = SearchSource.TAVILY
    round: int = 1
    purpose: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# === SourceItem ===


class SourceItem(BaseModel):
    id: str = Field(default_factory=_uuid)
    task_id: str
    title: str = ""
    url: str
    domain: str = ""
    snippet: str = ""
    published_at: datetime | None = None
    source_type: SourceType = SourceType.OTHER
    source_level: SourceLevel = SourceLevel.C
    relevance_score: float = 0.0
    authority_score: float = 0.0
    originality_score: float = 0.0
    gossip_score: float = 0.0
    downloadable: bool = True
    download_status: DownloadStatus = DownloadStatus.PENDING
    reason_to_read: str = ""


# === ExtractedDocument ===


class ExtractedDocument(BaseModel):
    id: str = Field(default_factory=_uuid)
    source_item_id: str
    title: str = ""
    author: str = ""
    content: str = ""
    markdown_path: str = ""
    summary: str = ""
    key_quotes: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


# === Entity ===


class Entity(BaseModel):
    id: str = Field(default_factory=_uuid)
    name: str
    type: EntityType = EntityType.OTHER
    description: str = ""
    related_task_id: str = ""
    importance_score: float = 0.0
    should_expand: bool = False


# === ResearchCard ===


class ResearchCard(BaseModel):
    id: str = Field(default_factory=_uuid)
    task_id: str
    type: CardType = CardType.FACT
    title: str = ""
    content: str = ""
    linked_sources: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.UNVERIFIED
    markdown_path: str = ""
