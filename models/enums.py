"""枚举定义 - 所有业务枚举集中管理。"""

from enum import StrEnum


# === Report Ingestion ===


class ResearchTaskType(StrEnum):
    """研究任务类型。"""

    SEARCH_RESEARCH = "search_research"
    REPORT_INGESTION = "report_ingestion"


class ReferenceType(StrEnum):
    """外部报告中引用的类型。"""

    URL = "url"
    BOOK = "book"
    PAPER = "paper"
    ARTICLE = "article"
    INTERVIEW = "interview"
    VIDEO = "video"
    UNKNOWN = "unknown"


class ReferenceStatus(StrEnum):
    """引用处理状态。"""

    PARSED = "parsed"
    ENRICHED = "enriched"
    EXTRACTED = "extracted"
    FAILED = "failed"
    SKIPPED = "skipped"


class SourceOrigin(StrEnum):
    """来源的来源渠道。"""

    SEARCH_PROVIDER = "search_provider"
    IMPORTED_REPORT = "imported_report"
    IMPORTED_REPORT_ENRICHED = "imported_report_enriched"
    MANUAL = "manual"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskMode(StrEnum):
    PERSON = "person"
    COMPANY = "company"
    EVENT = "event"
    CONCEPT = "concept"
    AUTO = "auto"


class Language(StrEnum):
    ZH = "zh"
    EN = "en"
    MIXED = "mixed"


class LanguageCode(StrEnum):
    """研究语言规划用语言代码。"""

    ZH = "zh"
    EN = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SearchStrategy(StrEnum):
    """搜索语言策略。"""

    ENGLISH_FIRST = "english_first"
    CHINESE_FIRST = "chinese_first"
    BILINGUAL = "bilingual"


class Depth(StrEnum):
    SHALLOW = "shallow"
    STANDARD = "standard"
    DEEP = "deep"


class SearchSource(StrEnum):
    TAVILY = "tavily"
    BRAVE = "brave"
    GOOGLE_BOOKS = "google_books"
    YOUTUBE = "youtube"
    ARCHIVE = "archive"
    SEARXNG = "searxng"
    OPEN_LIBRARY = "open_library"
    CROSSREF = "crossref"
    ARXIV = "arxiv"
    WIKIPEDIA = "wikipedia"
    GOOGLE_CUSTOM_SEARCH = "google_custom_search"
    SERPAPI = "serpapi"


class SourceLevel(StrEnum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class DownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTED = "extracted"
    EXPORTED = "exported"
    FAILED = "failed"
    SKIPPED = "skipped"


class SourceType(StrEnum):
    ACADEMIC = "academic"
    NEWS = "news"
    BLOG = "blog"
    BOOK = "book"
    DOCUMENTATION = "documentation"
    FORUM = "forum"
    VIDEO = "video"
    SOCIAL = "social"
    GOVERNMENT = "government"
    REFERENCE = "reference"
    PAPER = "paper"
    WEB = "web"
    OTHER = "other"


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    CONCEPT = "concept"
    EVENT = "event"
    PRODUCT = "product"
    OTHER = "other"


class Confidence(StrEnum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    RUMOR = "rumor"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"


class CardType(StrEnum):
    FACT = "fact"
    TIMELINE = "timeline"
    RELATIONSHIP = "relationship"
    CONTROVERSY = "controversy"
    QUOTE = "quote"
    SUMMARY = "summary"
    OTHER = "other"


# === Crawlee 模块枚举 ===


class CrawlMode(StrEnum):
    """抓取模式。"""

    HTTP = "http"
    BROWSER = "browser"
    ADAPTIVE = "adaptive"


class CrawlStatus(StrEnum):
    """抓取状态。"""

    PENDING = "pending"
    CRAWLING = "crawling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class CrawlSkipReason(StrEnum):
    """跳过抓取的原因。"""

    LOW_RELEVANCE = "low_relevance"
    DUPLICATE_URL = "duplicate_url"
    BLOCKED_DOMAIN = "blocked_domain"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    ROBOTS_DISALLOWED = "robots_disallowed"
    ALREADY_FETCHED = "already_fetched"
    NO_URL = "no_url"
    MAX_LIMIT_REACHED = "max_limit_reached"


class SearchResultDepth(StrEnum):
    """搜索结果候选深度。"""

    TOP30 = "top30"
    TOP50 = "top50"
    TOP100 = "top100"


# === Content Normalization & Research Synthesis ===


class NormalizedClaimType(StrEnum):
    """归一化事实条目类型。"""

    FACT = "fact"
    BACKGROUND = "background"
    TIMELINE_EVENT = "timeline_event"
    QUOTE = "quote"
    STORY_POINT = "story_point"
    CONTROVERSY = "controversy"
    INTERPRETATION = "interpretation"
    UNKNOWN = "unknown"


class ClaimConfidence(StrEnum):
    """事实条目置信度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"


class SynthesisSectionType(StrEnum):
    """研究合成文档章节类型。"""

    OVERVIEW = "overview"
    CONFIRMED_FACTS = "confirmed_facts"
    TIMELINE = "timeline"
    KEY_PEOPLE = "key_people"
    KEY_PLACES = "key_places"
    KEY_CONCEPTS = "key_concepts"
    STORY_POINTS = "story_points"
    BOOKS_AND_SOURCES = "books_and_sources"
    CONTROVERSIES = "controversies"
    VERIFICATION_NEEDED = "verification_needed"
    SOURCE_NOTES = "source_notes"
