"""Crawler API 路由测试。"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.crawlers.base import CrawlBatchResult, CrawlCandidate, CrawlResult
from app.main import app
from models.enums import CrawlStatus


@pytest.fixture
def client():
    return TestClient(app)


class TestCrawlUrlEndpoint:
    """POST /crawler/crawl-url 测试。"""

    def test_crawl_url_returns_result(self, client):
        """成功抓取返回 CrawlResult。"""
        mock_result = CrawlResult(
            url="https://example.com",
            final_url="https://example.com",
            title="Example Page",
            text="This is the page content. " * 20,
            content_chars=520,
            status=CrawlStatus.SUCCEEDED,
            http_status=200,
            duration_ms=1500,
            metadata={"method": "http"},
        )

        with patch(
            "app.api.routes_crawler.CrawleeCrawlerService"
        ) as MockService:
            instance = MockService.return_value
            instance.enabled = True
            instance._crawlee_config = {"save_html": False}
            instance.crawl_url = AsyncMock(return_value=mock_result)

            response = client.post("/crawler/crawl-url", json={
                "url": "https://example.com",
                "topic": "Test",
                "mode": "adaptive",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "succeeded"
            assert data["title"] == "Example Page"
            assert data["content_chars"] == 520
            assert data["html"] is None  # save_html=false

    def test_crawl_url_disabled_returns_503(self, client):
        """服务禁用时返回 503。"""
        with patch(
            "app.api.routes_crawler.CrawleeCrawlerService"
        ) as MockService:
            instance = MockService.return_value
            instance.enabled = False

            response = client.post("/crawler/crawl-url", json={
                "url": "https://example.com",
            })

            assert response.status_code == 503


class TestReviewCandidatesEndpoint:
    """POST /crawler/review-candidates 测试。"""

    def test_review_returns_should_crawl(self, client):
        """审查返回 should_crawl 判断。"""
        response = client.post("/crawler/review-candidates", json={
            "topic": "Tim Cook",
            "candidates": [
                {"url": "https://apple.com/tim-cook", "title": "Tim Cook - Apple", "snippet": "CEO of Apple", "rank": 1},
                {"url": "https://amazon.com/product", "title": "Buy Something", "snippet": "Shopping", "rank": 2},
            ],
            "depth": "top30",
        })

        assert response.status_code == 200
        data = response.json()
        assert "candidates" in data
        assert data["total"] == 2

        # Apple URL 应该通过
        apple_candidate = next(c for c in data["candidates"] if "apple.com" in c["url"])
        assert apple_candidate["should_crawl"] is True

        # Amazon URL 应该被阻止
        amazon_candidate = next(c for c in data["candidates"] if "amazon.com" in c["url"])
        assert amazon_candidate["should_crawl"] is False


class TestCrawlBatchEndpoint:
    """POST /crawler/crawl-batch 测试。"""

    def test_batch_returns_counts(self, client):
        """批量抓取返回 succeeded/failed count。"""
        mock_result = CrawlBatchResult(
            requested_count=3,
            crawled_count=3,
            succeeded_count=2,
            failed_count=1,
            skipped_count=0,
            results=[
                CrawlResult(url="https://a.com", status=CrawlStatus.SUCCEEDED, content_chars=500, text="Content"),
                CrawlResult(url="https://b.com", status=CrawlStatus.SUCCEEDED, content_chars=300, text="Content"),
                CrawlResult(url="https://c.com", status=CrawlStatus.FAILED, error_message="timeout"),
            ],
        )

        with patch(
            "app.api.routes_crawler.CrawleeCrawlerService"
        ) as MockService:
            instance = MockService.return_value
            instance.enabled = True
            instance._crawlee_config = {"save_html": False}
            instance.crawl_many = AsyncMock(return_value=mock_result)

            response = client.post("/crawler/crawl-batch", json={
                "topic": "Test",
                "candidates": [
                    {"url": "https://a.com", "title": "A"},
                    {"url": "https://b.com", "title": "B"},
                    {"url": "https://c.com", "title": "C"},
                ],
                "max_pages": 10,
            })

            assert response.status_code == 200
            data = response.json()
            assert data["succeeded_count"] == 2
            assert data["failed_count"] == 1


class TestCrawlerStatusEndpoint:
    """GET /crawler/status 测试。"""

    def test_status_returns_info(self, client):
        """状态端点返回服务信息。"""
        with patch("app.api.routes_crawler.is_crawlee_available", return_value=False):
            with patch("app.api.routes_crawler.is_playwright_available", return_value=False):
                response = client.get("/crawler/status")

                assert response.status_code == 200
                data = response.json()
                assert "enabled" in data
                assert "crawlee_installed" in data
                assert "playwright_installed" in data
                assert "message" in data
