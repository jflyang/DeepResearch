"""Crawlee 模块数据结构定义。

所有 Crawlee 相关的请求/响应模型集中在此，避免循环依赖。
"""

from pydantic import BaseModel, Field

from models.enums import CrawlMode, CrawlStatus, CrawlSkipReason


class CrawlCandidate(BaseModel):
    """搜索结果候选 URL，经过相关性判断后决定是否抓取。"""

    url: str
    title: str | None = None
    snippet: str | None = None
    source_provider: str | None = None
    matched_query: str | None = None
    rank: int | None = None
    source_hint: str | None = None
    relevance_score: float | None = None
    should_crawl: bool = True
    skip_reason: CrawlSkipReason | None = None


class CrawlRequest(BaseModel):
    """抓取请求参数。"""

    urls: list[str] = Field(default_factory=list)
    topic: str | None = None
    mode: CrawlMode = CrawlMode.ADAPTIVE
    max_pages: int = 30
    timeout_seconds: int = 30
    use_browser: bool = False
    respect_robots_txt: bool = True


class CrawlResult(BaseModel):
    """单个 URL 的抓取结果。"""

    url: str
    final_url: str | None = None
    title: str | None = None
    text: str | None = None
    html: str | None = None
    content_chars: int = 0
    status: CrawlStatus = CrawlStatus.PENDING
    http_status: int | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    metadata: dict = Field(default_factory=dict)


class CrawlBatchResult(BaseModel):
    """批量抓取结果汇总。"""

    requested_count: int = 0
    crawled_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    results: list[CrawlResult] = Field(default_factory=list)
