"""CrawleeCrawlerService - 使用 Crawlee for Python 访问 URL 并提取网页内容。

职责：
- 使用 HTTP crawler (BeautifulSoupCrawler) 抓取普通网页
- 需要 JS 渲染时 fallback 到 PlaywrightCrawler
- 支持批量抓取，单个 URL 失败不影响其他
- 不写 DB、不调用 LLM、不写 Obsidian

使用方式：
    service = CrawleeCrawlerService()
    result = await service.crawl_url("https://example.com", request)
    batch = await service.crawl_many(candidates, request)
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.crawlers.base import (
    CrawlBatchResult,
    CrawlCandidate,
    CrawlRequest,
    CrawlResult,
)
from app.crawlers.content_extractor import ContentExtractor
from models.enums import CrawlMode, CrawlStatus

logger = logging.getLogger(__name__)

# === Configuration ===

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CRAWLING_POLICY_PATH = _PROJECT_ROOT / "config" / "crawling_policy.yaml"


@lru_cache
def _load_crawling_policy() -> dict:
    """加载抓取策略配置。"""
    if not _CRAWLING_POLICY_PATH.exists():
        return _default_crawling_policy()
    try:
        with open(_CRAWLING_POLICY_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or _default_crawling_policy()
    except Exception as e:
        logger.warning("crawling_policy_load_failed error=%s", e)
        return _default_crawling_policy()


def _default_crawling_policy() -> dict:
    return {
        "crawlee": {
            "enabled": True,
            "default_mode": "adaptive",
            "max_pages_per_task": 30,
            "max_pages_deep": 100,
            "timeout_seconds": 30,
            "max_concurrency": 3,
            "respect_robots_txt": True,
            "user_agent": "ResearchCollectorBot/0.1",
            "browser_fallback": True,
            "save_html": False,
            "save_screenshot": False,
            "min_content_chars_for_success": 200,
        }
    }


def reset_crawling_policy_cache() -> None:
    """清除策略缓存（测试用）。"""
    _load_crawling_policy.cache_clear()


# === Crawlee Availability Check ===


def is_crawlee_available() -> bool:
    """检查 crawlee 是否已安装。"""
    try:
        import crawlee  # noqa: F401
        return True
    except ImportError:
        return False


def is_playwright_available() -> bool:
    """检查 playwright 是否已安装且浏览器可用。"""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


# === Service ===


class CrawleeCrawlerService:
    """使用 Crawlee for Python 抓取网页内容的服务。

    优先使用 HTTP 抓取（BeautifulSoupCrawler），
    如果内容太少且 mode=adaptive/browser，fallback 到 PlaywrightCrawler。
    """

    def __init__(self, policy: dict | None = None):
        self._policy = policy or _load_crawling_policy()
        self._crawlee_config = self._policy.get("crawlee", {})
        self._content_extractor = ContentExtractor()
        self._semaphore: asyncio.Semaphore | None = None

    @property
    def enabled(self) -> bool:
        return self._crawlee_config.get("enabled", True)

    @property
    def max_concurrency(self) -> int:
        return self._crawlee_config.get("max_concurrency", 3)

    @property
    def min_content_chars(self) -> int:
        return self._crawlee_config.get("min_content_chars_for_success", 200)

    async def crawl_url(self, url: str, request: CrawlRequest) -> CrawlResult:
        """抓取单个 URL。

        Args:
            url: 目标 URL
            request: 抓取参数

        Returns:
            CrawlResult 包含抓取结果或错误信息
        """
        if not self.enabled:
            return CrawlResult(
                url=url,
                status=CrawlStatus.FAILED,
                error_message="Crawlee service is disabled",
            )

        if not is_crawlee_available():
            return CrawlResult(
                url=url,
                status=CrawlStatus.FAILED,
                error_message="crawlee package not installed. Install with: pip install crawlee[beautifulsoup]",
            )

        start_time = time.perf_counter()
        mode = request.mode

        # Step 1: HTTP 抓取
        if mode in (CrawlMode.HTTP, CrawlMode.ADAPTIVE):
            result = await self._crawl_http(url, request)

            # 如果 adaptive 模式下内容太少，尝试 browser fallback
            if (
                mode == CrawlMode.ADAPTIVE
                and result.content_chars < self.min_content_chars
                and self._crawlee_config.get("browser_fallback", True)
                and is_playwright_available()
            ):
                logger.info(
                    "crawlee_browser_fallback url=%s http_chars=%d",
                    url, result.content_chars,
                )
                browser_result = await self._crawl_browser(url, request)
                if browser_result.content_chars > result.content_chars:
                    result = browser_result

        elif mode == CrawlMode.BROWSER:
            if not is_playwright_available():
                return CrawlResult(
                    url=url,
                    status=CrawlStatus.FAILED,
                    error_message="Playwright not installed. Install with: pip install playwright && playwright install",
                )
            result = await self._crawl_browser(url, request)

        else:
            result = await self._crawl_http(url, request)

        # 计算耗时
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        result.duration_ms = elapsed_ms

        return result

    async def crawl_many(
        self, candidates: list[CrawlCandidate], request: CrawlRequest
    ) -> CrawlBatchResult:
        """批量抓取候选 URL。

        只抓取 should_crawl=True 的候选。
        单个 URL 失败不影响其他。

        Args:
            candidates: 候选 URL 列表
            request: 抓取参数

        Returns:
            CrawlBatchResult 包含所有结果汇总
        """
        if not self.enabled:
            return CrawlBatchResult(
                requested_count=len(candidates),
                skipped_count=len(candidates),
            )

        # 过滤出需要抓取的候选
        to_crawl = [c for c in candidates if c.should_crawl]
        skipped = [c for c in candidates if not c.should_crawl]

        # 限制最大抓取数
        max_pages = min(request.max_pages, len(to_crawl))
        to_crawl = to_crawl[:max_pages]

        batch_result = CrawlBatchResult(
            requested_count=len(candidates),
            skipped_count=len(skipped) + (len([c for c in candidates if c.should_crawl]) - max_pages),
        )

        if not to_crawl:
            return batch_result

        # 并发抓取（受 semaphore 限制）
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

        tasks = [
            self._crawl_with_semaphore(candidate.url, request)
            for candidate in to_crawl
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                crawl_result = CrawlResult(
                    url=to_crawl[i].url,
                    status=CrawlStatus.FAILED,
                    error_message=str(result)[:500],
                )
            else:
                crawl_result = result

            batch_result.results.append(crawl_result)
            batch_result.crawled_count += 1

            if crawl_result.status == CrawlStatus.SUCCEEDED:
                batch_result.succeeded_count += 1
            else:
                batch_result.failed_count += 1

        return batch_result

    async def _crawl_with_semaphore(self, url: str, request: CrawlRequest) -> CrawlResult:
        """带并发限制的抓取。"""
        async with self._semaphore:
            return await self.crawl_url(url, request)

    async def _crawl_http(self, url: str, request: CrawlRequest) -> CrawlResult:
        """使用 HTTP 方式抓取（BeautifulSoupCrawler 或 httpx fallback）。"""
        try:
            from crawlee.beautifulsoup_crawler import BeautifulSoupCrawler, BeautifulSoupCrawlingContext
            from crawlee import ConcurrencySettings, HttpxHttpClient
            from crawlee.configuration import Configuration

            crawl_data: dict[str, Any] = {}

            async def request_handler(context: BeautifulSoupCrawlingContext) -> None:
                """处理抓取结果。"""
                soup = context.soup
                html_content = str(soup) if soup else ""

                # 使用 ContentExtractor 提取正文
                extracted = self._content_extractor.extract_from_html(html_content, url=url)

                crawl_data["title"] = extracted.get("title", "")
                crawl_data["text"] = extracted.get("text", "")
                crawl_data["html"] = html_content if self._crawlee_config.get("save_html", False) else None
                crawl_data["final_url"] = str(context.request.loaded_url or context.request.url)
                crawl_data["http_status"] = context.http_response.status_code if hasattr(context, 'http_response') and context.http_response else None

            # 配置 crawler
            config = Configuration(
                persist_storage=False,
                write_metadata=False,
            )

            crawler = BeautifulSoupCrawler(
                configuration=config,
                max_request_retries=1,
                request_handler_timeout=request.timeout_seconds,
                max_requests_per_crawl=1,
            )

            crawler.router.default_handler(request_handler)

            # 运行抓取
            await crawler.run([url])

            if crawl_data.get("text"):
                return CrawlResult(
                    url=url,
                    final_url=crawl_data.get("final_url"),
                    title=crawl_data.get("title"),
                    text=crawl_data.get("text"),
                    html=crawl_data.get("html"),
                    content_chars=len(crawl_data.get("text", "")),
                    status=CrawlStatus.SUCCEEDED,
                    http_status=crawl_data.get("http_status"),
                    metadata={"method": "http", "crawler": "beautifulsoup"},
                )
            else:
                return CrawlResult(
                    url=url,
                    status=CrawlStatus.FAILED,
                    error_message="No content extracted from page",
                    http_status=crawl_data.get("http_status"),
                    metadata={"method": "http", "crawler": "beautifulsoup"},
                )

        except ImportError:
            # Crawlee 未安装，使用 httpx + trafilatura fallback
            return await self._crawl_httpx_fallback(url, request)

        except Exception as e:
            logger.warning("crawlee_http_failed url=%s error=%s", url, str(e)[:200])
            return CrawlResult(
                url=url,
                status=CrawlStatus.FAILED,
                error_message=str(e)[:500],
                metadata={"method": "http", "crawler": "beautifulsoup"},
            )

    async def _crawl_browser(self, url: str, request: CrawlRequest) -> CrawlResult:
        """使用 Playwright 浏览器抓取（JS 渲染页面）。"""
        try:
            from crawlee.playwright_crawler import PlaywrightCrawler, PlaywrightCrawlingContext
            from crawlee.configuration import Configuration

            crawl_data: dict[str, Any] = {}

            async def request_handler(context: PlaywrightCrawlingContext) -> None:
                """处理浏览器抓取结果。"""
                page = context.page
                html_content = await page.content()

                extracted = self._content_extractor.extract_from_html(html_content, url=url)

                crawl_data["title"] = extracted.get("title", "") or await page.title()
                crawl_data["text"] = extracted.get("text", "")
                crawl_data["html"] = html_content if self._crawlee_config.get("save_html", False) else None
                crawl_data["final_url"] = page.url
                crawl_data["http_status"] = None  # Playwright 不直接暴露 status

            config = Configuration(
                persist_storage=False,
                write_metadata=False,
            )

            crawler = PlaywrightCrawler(
                configuration=config,
                max_request_retries=1,
                request_handler_timeout=request.timeout_seconds,
                max_requests_per_crawl=1,
                headless=True,
            )

            crawler.router.default_handler(request_handler)

            await crawler.run([url])

            if crawl_data.get("text"):
                return CrawlResult(
                    url=url,
                    final_url=crawl_data.get("final_url"),
                    title=crawl_data.get("title"),
                    text=crawl_data.get("text"),
                    html=crawl_data.get("html"),
                    content_chars=len(crawl_data.get("text", "")),
                    status=CrawlStatus.SUCCEEDED,
                    metadata={"method": "browser", "crawler": "playwright"},
                )
            else:
                return CrawlResult(
                    url=url,
                    status=CrawlStatus.FAILED,
                    error_message="No content extracted from browser-rendered page",
                    metadata={"method": "browser", "crawler": "playwright"},
                )

        except ImportError as e:
            return CrawlResult(
                url=url,
                status=CrawlStatus.FAILED,
                error_message=f"Playwright crawler not available: {e}",
                metadata={"method": "browser"},
            )

        except Exception as e:
            logger.warning("crawlee_browser_failed url=%s error=%s", url, str(e)[:200])
            return CrawlResult(
                url=url,
                status=CrawlStatus.FAILED,
                error_message=str(e)[:500],
                metadata={"method": "browser", "crawler": "playwright"},
            )

    async def _crawl_httpx_fallback(self, url: str, request: CrawlRequest) -> CrawlResult:
        """当 Crawlee 不可用时，使用 httpx + trafilatura 作为 fallback。"""
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=request.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": self._crawlee_config.get("user_agent", "ResearchCollectorBot/0.1")},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                html_content = response.text
                extracted = self._content_extractor.extract_from_html(html_content, url=url)

                if extracted.get("text"):
                    return CrawlResult(
                        url=url,
                        final_url=str(response.url),
                        title=extracted.get("title"),
                        text=extracted.get("text"),
                        content_chars=len(extracted.get("text", "")),
                        status=CrawlStatus.SUCCEEDED,
                        http_status=response.status_code,
                        metadata={"method": "httpx_fallback"},
                    )
                else:
                    return CrawlResult(
                        url=url,
                        status=CrawlStatus.FAILED,
                        error_message="No content extracted (httpx fallback)",
                        http_status=response.status_code,
                        metadata={"method": "httpx_fallback"},
                    )

        except Exception as e:
            return CrawlResult(
                url=url,
                status=CrawlStatus.FAILED,
                error_message=f"httpx fallback failed: {str(e)[:300]}",
                metadata={"method": "httpx_fallback"},
            )
