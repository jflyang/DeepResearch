"""枚举定义 - 所有业务枚举集中管理。"""

from enum import StrEnum


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
