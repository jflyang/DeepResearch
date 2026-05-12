"""Pydantic 业务层数据模型 - 模块间数据契约。"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from models.enums import (
    CardType,
    ClaimConfidence,
    Confidence,
    Depth,
    DownloadStatus,
    EntityType,
    Language,
    LanguageCode,
    NormalizedClaimType,
    ReferenceStatus,
    ReferenceType,
    ResearchTaskType,
    SearchSource,
    SearchStrategy,
    SourceLevel,
    SourceType,
    SynthesisSectionType,
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


# === Task Management ===


class ResearchTaskRenameRequest(BaseModel):
    """重命名研究任务请求。"""

    topic: str = Field(min_length=1, max_length=500)
    canonical_topic: str | None = None


class ResearchTaskDeleteRequest(BaseModel):
    """删除研究任务请求。"""

    hard_delete: bool = False
    delete_obsidian_files: bool = False


class ResearchTaskCloneRequest(BaseModel):
    """复制研究任务请求。"""

    rerun_immediately: bool = False
    topic_override: str | None = None
    reset_status: bool = True


class ResearchTaskRerunRequest(BaseModel):
    """重新发起研究任务请求。"""

    clone: bool = True


class ResearchTaskManagementResponse(BaseModel):
    """任务管理操作响应。"""

    task_id: str
    status: str
    message: str
    new_task_id: str | None = None


# === Content Normalization & Research Synthesis ===


class NormalizedContentUnit(BaseModel):
    """归一化内容单元 - 从已抓取正文中提取的单条结构化事实。"""

    id: str | None = None
    document_id: str
    source_id: str
    source_title: str
    source_url: str | None = None
    source_level: str | None = None
    claim_type: NormalizedClaimType = NormalizedClaimType.UNKNOWN
    claim: str
    normalized_claim: str
    evidence_text: str | None = None
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    confidence: ClaimConfidence = ClaimConfidence.MEDIUM
    source_language: str | None = None
    output_language: str = "zh"
    importance: int = Field(default=3, ge=1, le=5)
    needs_verification: bool = False
    verification_reason: str | None = None


class NormalizedDocumentAnalysis(BaseModel):
    """归一化文档分析结果 - 单篇已抓取文档的结构化分析。"""

    document_id: str
    source_id: str
    source_title: str
    source_url: str | None = None
    summary: str = ""
    main_claims: list[NormalizedContentUnit] = Field(default_factory=list)
    timeline_events: list[NormalizedContentUnit] = Field(default_factory=list)
    story_points: list[NormalizedContentUnit] = Field(default_factory=list)
    key_people: list[str] = Field(default_factory=list)
    key_places: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    quotes: list[NormalizedContentUnit] = Field(default_factory=list)
    verification_needed: list[NormalizedContentUnit] = Field(default_factory=list)


class DeduplicatedClaimGroup(BaseModel):
    """去重合并后的事实组 - 跨来源合并同一事实的不同表述。"""

    group_id: str | None = None
    normalized_claim: str
    claim_type: str = "fact"
    merged_claim: str
    supporting_sources: list[dict] = Field(default_factory=list)
    conflicting_sources: list[dict] = Field(default_factory=list)
    evidence_texts: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    confidence: ClaimConfidence = ClaimConfidence.MEDIUM
    importance: int = Field(default=3, ge=1, le=5)
    needs_verification: bool = False

    @model_validator(mode="after")
    def confirmed_must_have_sources(self):
        """confidence=high 时必须有 supporting_sources。"""
        if self.confidence == ClaimConfidence.HIGH and not self.supporting_sources:
            raise ValueError(
                "confirmed fact (confidence=high) must have at least one supporting_source"
            )
        return self


class SynthesizedResearchDocument(BaseModel):
    """合成研究文档 - 最终输出的结构化研究成果。"""

    task_id: str
    topic: str
    canonical_topic: str | None = None
    overview: str = ""
    executive_summary: str = ""
    confirmed_facts: list[DeduplicatedClaimGroup] = Field(default_factory=list)
    timeline: list[DeduplicatedClaimGroup] = Field(default_factory=list)
    key_people: list[dict] = Field(default_factory=list)
    key_places: list[dict] = Field(default_factory=list)
    key_concepts: list[dict] = Field(default_factory=list)
    story_points: list[DeduplicatedClaimGroup] = Field(default_factory=list)
    controversies: list[DeduplicatedClaimGroup] = Field(default_factory=list)
    verification_needed: list[DeduplicatedClaimGroup] = Field(default_factory=list)
    source_map: list[dict] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d %H:%M"))
