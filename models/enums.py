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
