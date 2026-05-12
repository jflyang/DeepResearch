"""Crawler API 路由 - 提供网页抓取和候选审查接口。

端点：
- POST /crawler/crawl-url       单个 URL 抓取
- POST /crawler/crawl-batch     批量 URL 抓取
- POST /crawler/review-candidates  候选相关性审查（不抓取）
- GET  /crawler/status          Crawlee 服务状态
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.crawlers.base import CrawlBatchResult, CrawlCandidate, CrawlRequest, CrawlResult
from app.crawlers.crawlee_service import CrawleeCrawlerService, is_crawlee_available, is_playwright_available
from app.crawlers.relevance_filter import RelevanceFilter
from models.enums import CrawlMode, SearchResultDepth

logger = logging.getLogger(__name__)

router = APIRouter()


# === Request/Response Models ===


class CrawlUrlRequest(BaseModel):
    """单个 URL 抓取请求。"""

    url: str
    topic: str | None = None
    mode: CrawlMode = CrawlMode.ADAPTIVE
    timeout_seconds: int = 30


class CrawlBatchRequest(BaseModel):
    """批量抓取请求。"""

    topic: str | None = None
    candidates: list[dict] = Field(default_factory=list)
    mode: CrawlMode = CrawlMode.ADAPTIVE
    max_pages: int = 30
    timeout_seconds: int = 30


class ReviewCandidatesRequest(BaseModel):
    """候选审查请求。"""

    topic: str
    canonical_topic: str | None = None
    candidates: list[dict] = Field(default_factory=list)
    depth: SearchResultDepth = SearchResultDepth.TOP30


class ReviewCandidatesResponse(BaseModel):
    """候选审查响应。"""

    candidates: list[CrawlCandidate]
    total: int = 0
    should_crawl_count: int = 0
    skipped_count: int = 0


class CrawlerStatusResponse(BaseModel):
    """Crawlee 服务状态。"""

    enabled: bool = False
    crawlee_installed: bool = False
    playwright_installed: bool = False
    default_mode: str = "adaptive"
    max_concurrency: int = 3
    message: str = ""


# === Endpoints ===


@router.post("/crawl-url", response_model=CrawlResult)
async def crawl_url(request: CrawlUrlRequest):
    """抓取单个 URL 并返回提取的正文。

    用于前端"提取正文"按钮或手动抓取。
    """
    service = CrawleeCrawlerService()

    if not service.enabled:
        raise HTTPException(status_code=503, detail="Crawlee service is disabled")

    crawl_request = CrawlRequest(
        urls=[request.url],
        topic=request.topic,
        mode=request.mode,
        timeout_seconds=request.timeout_seconds,
    )

    result = await service.crawl_url(request.url, crawl_request)

    # 不返回完整 HTML（除非配置了 save_html）
    if result.html and not service._crawlee_config.get("save_html", False):
        result.html = None

    return result


@router.post("/crawl-batch", response_model=CrawlBatchResult)
async def crawl_batch(request: CrawlBatchRequest):
    """批量抓取候选 URL。

    接受候选列表，对 should_crawl=true 的 URL 执行抓取。
    """
    service = CrawleeCrawlerService()

    if not service.enabled:
        raise HTTPException(status_code=503, detail="Crawlee service is disabled")

    # 构建 CrawlCandidate 列表
    candidates = [
        CrawlCandidate(
            url=c.get("url", ""),
            title=c.get("title"),
            snippet=c.get("snippet"),
            rank=c.get("rank"),
            should_crawl=c.get("should_crawl", True),
        )
        for c in request.candidates
        if c.get("url")
    ]

    crawl_request = CrawlRequest(
        topic=request.topic,
        mode=request.mode,
        max_pages=request.max_pages,
        timeout_seconds=request.timeout_seconds,
    )

    result = await service.crawl_many(candidates, crawl_request)

    # 清除 HTML
    for r in result.results:
        if r.html and not service._crawlee_config.get("save_html", False):
            r.html = None

    return result


@router.post("/review-candidates", response_model=ReviewCandidatesResponse)
async def review_candidates(request: ReviewCandidatesRequest):
    """对候选 URL 进行相关性审查，不执行抓取。

    返回每个候选的 relevance_score 和 should_crawl 判断。
    """
    relevance_filter = RelevanceFilter()

    candidates = await relevance_filter.filter_candidates(
        candidates=request.candidates,
        topic=request.topic,
        canonical_topic=request.canonical_topic,
        depth=request.depth,
    )

    should_crawl_count = sum(1 for c in candidates if c.should_crawl)

    return ReviewCandidatesResponse(
        candidates=candidates,
        total=len(candidates),
        should_crawl_count=should_crawl_count,
        skipped_count=len(candidates) - should_crawl_count,
    )


@router.get("/status", response_model=CrawlerStatusResponse)
async def crawler_status():
    """获取 Crawlee 服务状态。"""
    service = CrawleeCrawlerService()
    crawlee_installed = is_crawlee_available()
    playwright_installed = is_playwright_available()

    if not service.enabled:
        message = "Crawlee service is disabled in configuration"
    elif not crawlee_installed:
        message = "crawlee package not installed. Install with: pip install crawlee[beautifulsoup]"
    elif not playwright_installed:
        message = "Crawlee available (HTTP mode). Playwright not installed for browser fallback."
    else:
        message = "Crawlee fully available (HTTP + Browser mode)"

    return CrawlerStatusResponse(
        enabled=service.enabled,
        crawlee_installed=crawlee_installed,
        playwright_installed=playwright_installed,
        default_mode=service._crawlee_config.get("default_mode", "adaptive"),
        max_concurrency=service.max_concurrency,
        message=message,
    )
