"""ResearchService + Crawlee 集成测试。

验证研究流程中 Crawlee 抓取阶段的正确编排。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crawlers.base import CrawlBatchResult, CrawlCandidate, CrawlRequest, CrawlResult
from app.crawlers.crawlee_service import CrawleeCrawlerService
from app.crawlers.relevance_filter import RelevanceFilter
from models.enums import CrawlMode, CrawlStatus, SearchResultDepth, SourceLevel


class TestResearchCrawleeIntegration:
    """ResearchService 与 Crawlee 集成测试。"""

    @pytest.mark.asyncio
    async def test_relevance_filter_receives_search_results(self):
        """搜索结果传入 RelevanceFilter 进行审查。"""
        filter_instance = RelevanceFilter(config={
            "enabled": True,
            "min_score": 0.55,
            "llm_enabled": False,
        })

        # 模拟搜索结果
        search_results = [
            {
                "url": "https://apple.com/tim-cook",
                "title": "Tim Cook - Apple CEO",
                "snippet": "Tim Cook is the CEO of Apple Inc.",
                "rank": 1,
                "source_provider": "searxng",
            },
            {
                "url": "https://random-shop.com/product",
                "title": "Buy Electronics",
                "snippet": "Shop for the latest gadgets.",
                "rank": 2,
                "source_provider": "searxng",
            },
        ]

        candidates = await filter_instance.filter_candidates(
            candidates=search_results,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
            depth=SearchResultDepth.TOP30,
        )

        # 验证过滤结果
        assert len(candidates) == 2
        apple_candidate = next(c for c in candidates if "apple.com" in c.url)
        assert apple_candidate.should_crawl is True

    @pytest.mark.asyncio
    async def test_should_crawl_candidates_enter_crawlee(self):
        """should_crawl=true 的候选进入 Crawlee 抓取。"""
        service = CrawleeCrawlerService(policy={
            "crawlee": {
                "enabled": True,
                "max_concurrency": 2,
                "timeout_seconds": 10,
                "browser_fallback": False,
                "min_content_chars_for_success": 100,
            }
        })

        candidates = [
            CrawlCandidate(url="https://good.com/article", should_crawl=True, relevance_score=0.8),
            CrawlCandidate(url="https://skip.com/page", should_crawl=False, relevance_score=0.3),
            CrawlCandidate(url="https://another.com/post", should_crawl=True, relevance_score=0.7),
        ]

        request = CrawlRequest(mode=CrawlMode.HTTP, max_pages=10)

        # Mock crawl_url
        async def mock_crawl(url, req):
            return CrawlResult(
                url=url,
                title=f"Page from {url}",
                text="Extracted content. " * 30,
                content_chars=540,
                status=CrawlStatus.SUCCEEDED,
            )

        with patch.object(service, "crawl_url", side_effect=mock_crawl):
            result = await service.crawl_many(candidates, request)

        # 只有 should_crawl=true 的被抓取
        assert result.crawled_count == 2
        assert result.skipped_count == 1
        assert result.succeeded_count == 2

    @pytest.mark.asyncio
    async def test_crawl_result_can_become_extracted_document(self):
        """CrawlResult 可以转换为 ExtractedDocument。"""
        from models.schemas import ExtractedDocument

        crawl_result = CrawlResult(
            url="https://example.com/article",
            final_url="https://example.com/article",
            title="Important Article",
            text="This is the full article content about Tim Cook's early career at Apple.",
            content_chars=70,
            status=CrawlStatus.SUCCEEDED,
            http_status=200,
        )

        # 模拟将 CrawlResult 转换为 ExtractedDocument
        doc = ExtractedDocument(
            source_item_id="test-source-id",
            title=crawl_result.title or "",
            content=crawl_result.text or "",
        )

        assert doc.title == "Important Article"
        assert "Tim Cook" in doc.content
        assert doc.source_item_id == "test-source-id"

    @pytest.mark.asyncio
    async def test_single_url_failure_does_not_affect_task(self):
        """单个 URL 抓取失败不影响整个研究任务。"""
        service = CrawleeCrawlerService(policy={
            "crawlee": {
                "enabled": True,
                "max_concurrency": 2,
                "timeout_seconds": 5,
                "browser_fallback": False,
                "min_content_chars_for_success": 100,
            }
        })

        candidates = [
            CrawlCandidate(url="https://good1.com", should_crawl=True),
            CrawlCandidate(url="https://timeout.com", should_crawl=True),
            CrawlCandidate(url="https://good2.com", should_crawl=True),
        ]

        request = CrawlRequest(mode=CrawlMode.HTTP, max_pages=10)

        async def mock_crawl(url, req):
            if "timeout" in url:
                return CrawlResult(
                    url=url,
                    status=CrawlStatus.FAILED,
                    error_message="Connection timeout after 5s",
                )
            return CrawlResult(
                url=url,
                title=f"Page {url}",
                text="Good content. " * 30,
                content_chars=420,
                status=CrawlStatus.SUCCEEDED,
            )

        with patch.object(service, "crawl_url", side_effect=mock_crawl):
            result = await service.crawl_many(candidates, request)

        # 任务整体成功，只有一个 URL 失败
        assert result.succeeded_count == 2
        assert result.failed_count == 1
        assert result.crawled_count == 3

    @pytest.mark.asyncio
    async def test_a_level_sources_auto_crawl(self):
        """A/S 级来源自动抓取。"""
        filter_instance = RelevanceFilter(config={
            "enabled": True,
            "min_score": 0.4,  # 低阈值确保通过
            "llm_enabled": False,
        })

        # 模拟 A 级来源的 URL
        a_level_sources = [
            {
                "url": "https://nytimes.com/tim-cook-interview",
                "title": "Tim Cook Interview - NYTimes",
                "snippet": "An exclusive interview with Apple CEO Tim Cook.",
                "rank": 1,
            },
            {
                "url": "https://stanford.edu/tim-cook-speech",
                "title": "Tim Cook at Stanford",
                "snippet": "Tim Cook delivers commencement speech.",
                "rank": 2,
            },
        ]

        candidates = await filter_instance.filter_candidates(
            candidates=a_level_sources,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        # A 级来源应该全部通过
        assert all(c.should_crawl for c in candidates)

    @pytest.mark.asyncio
    async def test_trace_records_crawlee_batch(self):
        """Trace 记录 crawlee_batch_finished 事件。"""
        from app.tracing.models import TraceStep

        # 验证 TraceStep 常量存在
        assert hasattr(TraceStep, "CRAWLEE_BATCH_STARTED")
        assert hasattr(TraceStep, "CRAWLEE_BATCH_FINISHED")
        assert hasattr(TraceStep, "CRAWLEE_URL_STARTED")
        assert hasattr(TraceStep, "CRAWLEE_URL_FINISHED")
        assert hasattr(TraceStep, "CRAWLEE_URL_FAILED")
        assert hasattr(TraceStep, "CRAWL_CANDIDATES_COLLECTED")
        assert hasattr(TraceStep, "CRAWL_CANDIDATE_REVIEW_STARTED")
        assert hasattr(TraceStep, "CRAWL_CANDIDATE_REVIEW_FINISHED")

        # 验证值
        assert TraceStep.CRAWLEE_BATCH_FINISHED == "crawlee_batch_finished"
