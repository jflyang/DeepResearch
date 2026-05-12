"""CrawleeCrawlerService 单元测试。

测试策略：不访问真实网络，使用 mock 模拟 Crawlee 行为。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawlers.base import CrawlBatchResult, CrawlCandidate, CrawlRequest, CrawlResult
from app.crawlers.crawlee_service import CrawleeCrawlerService, is_crawlee_available
from models.enums import CrawlMode, CrawlStatus


@pytest.fixture
def service():
    """创建测试用 CrawleeCrawlerService 实例。"""
    policy = {
        "crawlee": {
            "enabled": True,
            "default_mode": "adaptive",
            "max_pages_per_task": 30,
            "timeout_seconds": 10,
            "max_concurrency": 2,
            "respect_robots_txt": True,
            "user_agent": "TestBot/0.1",
            "browser_fallback": True,
            "save_html": False,
            "min_content_chars_for_success": 200,
        }
    }
    return CrawleeCrawlerService(policy=policy)


@pytest.fixture
def disabled_service():
    """创建禁用的 CrawleeCrawlerService 实例。"""
    policy = {"crawlee": {"enabled": False}}
    return CrawleeCrawlerService(policy=policy)


@pytest.fixture
def request_http():
    return CrawlRequest(mode=CrawlMode.HTTP, timeout_seconds=10)


@pytest.fixture
def request_adaptive():
    return CrawlRequest(mode=CrawlMode.ADAPTIVE, timeout_seconds=10)


class TestCrawlUrl:
    """crawl_url 测试。"""

    @pytest.mark.asyncio
    async def test_disabled_service_returns_failed(self, disabled_service, request_http):
        """禁用服务时返回 failed 状态。"""
        result = await disabled_service.crawl_url("https://example.com", request_http)
        assert result.status == CrawlStatus.FAILED
        assert "disabled" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_crawlee_not_installed_returns_error(self, service, request_http):
        """Crawlee 未安装时返回明确错误。"""
        with patch("app.crawlers.crawlee_service.is_crawlee_available", return_value=False):
            result = await service.crawl_url("https://example.com", request_http)
            assert result.status == CrawlStatus.FAILED
            assert "not installed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_successful_http_crawl(self, service, request_http):
        """HTTP 抓取成功返回 title/text/content_chars。"""
        mock_result = CrawlResult(
            url="https://example.com",
            final_url="https://example.com",
            title="Test Page",
            text="This is a test page with enough content to pass the minimum threshold. " * 10,
            content_chars=700,
            status=CrawlStatus.SUCCEEDED,
            http_status=200,
            metadata={"method": "http"},
        )

        with patch("app.crawlers.crawlee_service.is_crawlee_available", return_value=True):
            with patch.object(service, "_crawl_http", new_callable=AsyncMock, return_value=mock_result):
                result = await service.crawl_url("https://example.com", request_http)
                assert result.status == CrawlStatus.SUCCEEDED
                assert result.title == "Test Page"
                assert result.content_chars == 700
                assert result.duration_ms is not None

    @pytest.mark.asyncio
    async def test_failed_http_crawl(self, service, request_http):
        """HTTP 抓取失败返回 status=failed。"""
        mock_result = CrawlResult(
            url="https://example.com",
            status=CrawlStatus.FAILED,
            error_message="Connection timeout",
        )

        with patch("app.crawlers.crawlee_service.is_crawlee_available", return_value=True):
            with patch.object(service, "_crawl_http", new_callable=AsyncMock, return_value=mock_result):
                result = await service.crawl_url("https://example.com", request_http)
                assert result.status == CrawlStatus.FAILED
                assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_adaptive_mode_browser_fallback(self, service, request_adaptive):
        """adaptive 模式下内容太少时尝试 browser fallback。"""
        # HTTP 返回内容太少
        http_result = CrawlResult(
            url="https://spa-app.com",
            text="Loading...",
            content_chars=10,
            status=CrawlStatus.SUCCEEDED,
            metadata={"method": "http"},
        )

        # Browser 返回完整内容
        browser_result = CrawlResult(
            url="https://spa-app.com",
            title="SPA App",
            text="Full rendered content with lots of text. " * 20,
            content_chars=800,
            status=CrawlStatus.SUCCEEDED,
            metadata={"method": "browser"},
        )

        with patch("app.crawlers.crawlee_service.is_crawlee_available", return_value=True):
            with patch.object(service, "_crawl_http", new_callable=AsyncMock, return_value=http_result):
                with patch.object(service, "_crawl_browser", new_callable=AsyncMock, return_value=browser_result):
                    with patch("app.crawlers.crawlee_service.is_playwright_available", return_value=True):
                        result = await service.crawl_url("https://spa-app.com", request_adaptive)
                        assert result.status == CrawlStatus.SUCCEEDED
                        assert result.content_chars == 800
                        assert result.metadata.get("method") == "browser"

    @pytest.mark.asyncio
    async def test_http_mode_no_browser_fallback(self, service, request_http):
        """mode=http 时不调用 browser。"""
        http_result = CrawlResult(
            url="https://example.com",
            text="Short",
            content_chars=5,
            status=CrawlStatus.SUCCEEDED,
            metadata={"method": "http"},
        )

        with patch.object(service, "_crawl_http", new_callable=AsyncMock, return_value=http_result):
            with patch.object(service, "_crawl_browser", new_callable=AsyncMock) as mock_browser:
                result = await service.crawl_url("https://example.com", request_http)
                mock_browser.assert_not_called()


class TestCrawlMany:
    """crawl_many 批量抓取测试。"""

    @pytest.mark.asyncio
    async def test_batch_crawl_success(self, service):
        """批量抓取中一个失败不影响其他。"""
        candidates = [
            CrawlCandidate(url="https://good1.com", should_crawl=True),
            CrawlCandidate(url="https://bad.com", should_crawl=True),
            CrawlCandidate(url="https://good2.com", should_crawl=True),
        ]

        request = CrawlRequest(mode=CrawlMode.HTTP, max_pages=10)

        async def mock_crawl(url, req):
            if "bad" in url:
                return CrawlResult(url=url, status=CrawlStatus.FAILED, error_message="404")
            return CrawlResult(
                url=url, title=f"Page {url}", text="Content " * 50,
                content_chars=350, status=CrawlStatus.SUCCEEDED,
            )

        with patch.object(service, "crawl_url", side_effect=mock_crawl):
            result = await service.crawl_many(candidates, request)

            assert result.requested_count == 3
            assert result.crawled_count == 3
            assert result.succeeded_count == 2
            assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_batch_skips_should_crawl_false(self, service):
        """should_crawl=false 的候选被跳过。"""
        candidates = [
            CrawlCandidate(url="https://good.com", should_crawl=True),
            CrawlCandidate(url="https://skip.com", should_crawl=False),
        ]

        request = CrawlRequest(mode=CrawlMode.HTTP, max_pages=10)

        async def mock_crawl(url, req):
            return CrawlResult(
                url=url, text="Content " * 50,
                content_chars=350, status=CrawlStatus.SUCCEEDED,
            )

        with patch.object(service, "crawl_url", side_effect=mock_crawl):
            result = await service.crawl_many(candidates, request)

            assert result.crawled_count == 1
            assert result.skipped_count == 1

    @pytest.mark.asyncio
    async def test_batch_respects_max_pages(self, service):
        """批量抓取受 max_pages 限制。"""
        candidates = [
            CrawlCandidate(url=f"https://page{i}.com", should_crawl=True)
            for i in range(20)
        ]

        request = CrawlRequest(mode=CrawlMode.HTTP, max_pages=5)

        async def mock_crawl(url, req):
            return CrawlResult(
                url=url, text="Content " * 50,
                content_chars=350, status=CrawlStatus.SUCCEEDED,
            )

        with patch.object(service, "crawl_url", side_effect=mock_crawl):
            result = await service.crawl_many(candidates, request)

            assert result.crawled_count == 5

    @pytest.mark.asyncio
    async def test_disabled_service_batch(self, disabled_service):
        """禁用服务时批量抓取全部跳过。"""
        candidates = [
            CrawlCandidate(url="https://example.com", should_crawl=True),
        ]
        request = CrawlRequest(mode=CrawlMode.HTTP)

        result = await disabled_service.crawl_many(candidates, request)
        assert result.skipped_count == 1
        assert result.crawled_count == 0
