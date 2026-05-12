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
    ReferenceStatus,
    ReferenceType,
    ResearchTaskType,
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
    task_type: ResearchTaskType = ResearchTaskType.SEARCH_RESEARCH
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
    source_origin: str = "search_provider"
    # 语言元数据（不影响 DB，仅 runtime / markdown export 使用）
    query_language: LanguageCode | None = None
    source_language: LanguageCode | None = None
    matched_query: str | None = None
    canonical_topic: str | None = None
    original_topic: str | None = None


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
    # 语言元数据（不影响 DB，仅 runtime / markdown export 使用）
    original_language: LanguageCode | None = None
    summary_language: LanguageCode | None = None
    translated_title: str | None = None
    canonical_topic: str | None = None
    original_topic: str | None = None


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
    ACADEMIC = "academic"
    PAPER = "paper"
    CONCEPT = "concept"


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


# === Report Ingestion ===


class ReportIngestionOptions(BaseModel):
    """外部报告导入选项。"""

    extract_urls: bool = True
    enrich_books: bool = True
    enrich_papers: bool = True
    analyze_documents: bool = True
    export_to_obsidian: bool = False


class ImportedReportCreate(BaseModel):
    """创建外部报告导入请求。"""

    topic: str
    report_text: str = Field(min_length=1)
    report_source: str | None = None
    output_language: str = "zh"
    options: ReportIngestionOptions = Field(default_factory=ReportIngestionOptions)


class ExtractedUrlReference(BaseModel):
    """从报告中提取的 URL 引用。"""

    url: str
    title_hint: str | None = None
    surrounding_text: str | None = None
    citation_marker: str | None = None


class ExtractedBookReference(BaseModel):
    """从报告中提取的书籍引用。"""

    title: str
    author_hint: str | None = None
    year_hint: str | None = None
    surrounding_text: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractedPaperReference(BaseModel):
    """从报告中提取的论文引用。"""

    title: str
    author_hint: str | None = None
    year_hint: str | None = None
    doi_hint: str | None = None
    arxiv_id: str | None = None
    surrounding_text: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ParsedReport(BaseModel):
    """报告解析结果 - 包含所有提取的引用和实体。"""

    urls: list[ExtractedUrlReference] = Field(default_factory=list)
    books: list[ExtractedBookReference] = Field(default_factory=list)
    papers: list[ExtractedPaperReference] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    raw_citations: list[str] = Field(default_factory=list)


class ReferenceCandidate(BaseModel):
    """引用候选 - 统一表示待处理的引用。"""

    type: ReferenceType
    value: str
    title_hint: str | None = None
    source_url: str | None = None
    status: ReferenceStatus = ReferenceStatus.PARSED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class ReportIngestionResult(BaseModel):
    """报告导入结果摘要。"""

    task_id: str
    parsed_url_count: int = 0
    parsed_book_count: int = 0
    parsed_paper_count: int = 0
    extracted_document_count: int = 0
    enriched_source_count: int = 0
    enriched_book_count: int = 0
    enriched_paper_count: int = 0
    failed_count: int = 0
    source_count: int = 0
    exported_path: str | None = None
