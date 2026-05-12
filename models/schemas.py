"""Pydantic 业务层数据模型 - 模块间数据契约。"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from models.enums import (
    CardType,
    Confidence,
    Depth,
    DownloadStatus,
    EntityType,
    Language,
    LanguageCode,
    SearchSource,
    SearchStrategy,
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


# === Research Language Planning ===


class ResearchLanguagePlan(BaseModel):
    """研究语言规划 - 决定一个研究主题的语言策略。"""

    user_language: LanguageCode = LanguageCode.ZH
    working_language: LanguageCode = LanguageCode.EN
    output_language: LanguageCode = LanguageCode.ZH
    original_topic: str
    canonical_topic: str = ""
    main_entity_original: str | None = None
    main_entity_canonical: str | None = None
    aliases: list[str] = Field(default_factory=list)
    search_languages: list[LanguageCode] = Field(default_factory=list)
    search_strategy: SearchStrategy = SearchStrategy.ENGLISH_FIRST
    translation_notes: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# === ExpandedQuery ===


class SourceHint(StrEnum):
    """搜索来源提示。"""

    WEB = "web"
    BOOK = "book"
    VIDEO = "video"
    ARCHIVE = "archive"
    FORUM = "forum"
    LEGAL = "legal"
    GENERAL = "general"


class ExpandedQuery(BaseModel):
    """单条扩展查询 - 带语言和实体追溯信息。"""

    query: str
    purpose: str = ""
    source_hint: SourceHint = SourceHint.GENERAL
    priority: int = Field(default=5, ge=1, le=10)
    round: int = 1
    language: LanguageCode = LanguageCode.EN
    canonical_entity: str | None = None
    original_user_term: str | None = None
