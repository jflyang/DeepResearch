"""AI 模块数据模型。"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# === Gateway 层模型 ===


class LLMRequest(BaseModel):
    """LLM 调用请求。"""

    task: str
    prompt: str
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    response_format: str = "text"  # "text" | "json"
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """LLM 调用响应。"""

    task: str
    content: str
    model: str
    tokens_used: int = 0
    cached: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskConfig(BaseModel):
    """单个 LLM 任务配置。"""

    name: str
    prompt_template: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    response_format: str = "text"


# === LLM 输出 Schema ===


class TopicUnderstandingOutput(BaseModel):
    """主题理解输出。"""

    mode: str = Field(default="", max_length=50)
    main_entity: str = Field(default="", max_length=200)
    normalized_topic: str = Field(default="", max_length=200)
    language: str = Field(default="zh", max_length=10)
    aliases: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    suggested_focus: list[str] = Field(default_factory=list)


class SourceHint(str, Enum):
    """搜索来源提示。"""

    web = "web"
    book = "book"
    video = "video"
    archive = "archive"
    general = "general"


class ExpandedQueryItem(BaseModel):
    """单条扩展查询。"""

    query: str = Field(max_length=500)
    purpose: str = Field(default="", max_length=200)
    source_hint: SourceHint = SourceHint.general
    priority: int = Field(default=1, ge=1, le=10)


class QueryExpansionOutput(BaseModel):
    """查询扩展输出。"""

    queries: list[ExpandedQueryItem] = Field(default_factory=list)


class EntityType(str, Enum):
    """实体类型。"""

    person = "person"
    company = "company"
    place = "place"
    concept = "concept"
    event = "event"
    product = "product"
    book = "book"
    paper = "paper"
    legal_document = "legal_document"
    interview = "interview"


class ExtractedEntity(BaseModel):
    """提取的实体。"""

    name: str = Field(max_length=200)
    type: EntityType
    description: str = Field(default="", max_length=500)
    relation_to_topic: str = Field(default="", max_length=300)
    should_expand: bool = False


class EntityExtractionOutput(BaseModel):
    """实体提取输出。"""

    entities: list[ExtractedEntity] = Field(default_factory=list)


class Confidence(str, Enum):
    """置信度。"""

    high = "high"
    medium = "medium"
    low = "low"


class SourceReviewOutput(BaseModel):
    """来源评审输出。"""

    relevance_note: str = Field(default="", max_length=500)
    quality_warning: str | None = Field(default=None, max_length=500)
    likely_source_type: str = Field(default="", max_length=50)
    suggested_category: str = Field(default="", max_length=50)
    reason_to_read: str = Field(default="", max_length=500)
    should_download: bool = False
    confidence: Confidence = Confidence.medium


class DocumentAnalysisOutput(BaseModel):
    """文档分析输出。"""

    summary: str = Field(default="", max_length=2000)
    reason_to_read: str = Field(default="", max_length=500)
    key_points: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    story_points: list[str] = Field(default_factory=list)
    gossip_or_unverified_claims: list[str] = Field(default_factory=list)
    verification_notes: list[str] = Field(default_factory=list)
