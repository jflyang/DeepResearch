"""RelevanceFilter 单元测试。

测试相关性判断规则的正确性。
"""

import pytest

from app.crawlers.relevance_filter import RelevanceFilter
from models.enums import CrawlSkipReason, SearchResultDepth


@pytest.fixture
def filter_instance():
    """创建测试用 RelevanceFilter 实例。"""
    config = {
        "enabled": True,
        "min_score": 0.55,
        "llm_enabled": False,
        "top_n_for_llm_review": 30,
    }
    return RelevanceFilter(config=config)


@pytest.fixture
def tim_cook_candidates():
    """Tim Cook 主题的测试候选。"""
    return [
        {
            "url": "https://www.apple.com/leadership/tim-cook/",
            "title": "Tim Cook - Apple Leadership",
            "snippet": "Tim Cook is the CEO of Apple and serves on its board of directors.",
            "rank": 1,
        },
        {
            "url": "https://www.stanford.edu/news/tim-cook-commencement",
            "title": "Tim Cook Stanford Commencement Speech 2019",
            "snippet": "Apple CEO Tim Cook delivered the commencement address at Stanford University.",
            "rank": 2,
        },
        {
            "url": "https://www.nytimes.com/interview/tim-cook-exclusive",
            "title": "Exclusive Interview: Tim Cook on Apple's Future",
            "snippet": "In a rare interview, Tim Cook discusses Apple's vision for the next decade.",
            "rank": 3,
        },
        {
            "url": "https://en.wikipedia.org/wiki/Tim_Cook",
            "title": "Tim Cook - Wikipedia",
            "snippet": "Timothy Donald Cook is an American business executive who has been the CEO of Apple Inc.",
            "rank": 4,
        },
        {
            "url": "https://www.amazon.com/dp/B08XYZ123",
            "title": "Tim Cook Cookbook - Amazon",
            "snippet": "Buy Tim Cook's favorite recipes cookbook on Amazon.",
            "rank": 5,
        },
        {
            "url": "https://www.oreilly.com/python-cookbook",
            "title": "Python Cookbook: Recipes for Mastering Python 3",
            "snippet": "A comprehensive guide to Python programming with practical recipes.",
            "rank": 6,
        },
        {
            "url": "https://www.allrecipes.com/recipe/tim-cook-style-pasta",
            "title": "Tim Cook Style Pasta Recipe",
            "snippet": "A delicious pasta recipe inspired by Silicon Valley culture.",
            "rank": 7,
        },
        {
            "url": "https://login.example.com/auth",
            "title": "Login - Example Portal",
            "snippet": "Sign in to access your account.",
            "rank": 8,
        },
    ]


class TestRelevanceFilter:
    """RelevanceFilter 规则测试。"""

    @pytest.mark.asyncio
    async def test_apple_url_should_crawl(self, filter_instance, tim_cook_candidates):
        """Apple 官方页面应该被抓取。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        apple_result = next(r for r in results if "apple.com" in r.url)
        assert apple_result.should_crawl is True
        assert apple_result.relevance_score >= 0.6

    @pytest.mark.asyncio
    async def test_university_url_should_crawl(self, filter_instance, tim_cook_candidates):
        """大学网站应该被抓取。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        stanford_result = next(r for r in results if "stanford.edu" in r.url)
        assert stanford_result.should_crawl is True

    @pytest.mark.asyncio
    async def test_interview_url_should_crawl(self, filter_instance, tim_cook_candidates):
        """访谈文章应该被抓取。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        interview_result = next(r for r in results if "nytimes.com" in r.url)
        assert interview_result.should_crawl is True
        assert interview_result.relevance_score >= 0.7

    @pytest.mark.asyncio
    async def test_python_cookbook_should_not_crawl(self, filter_instance, tim_cook_candidates):
        """Python cookbook 与 Tim Cook 无关，不应抓取。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        python_result = next(r for r in results if "oreilly.com" in r.url)
        assert python_result.should_crawl is False

    @pytest.mark.asyncio
    async def test_cooking_recipe_should_not_crawl(self, filter_instance, tim_cook_candidates):
        """菜谱网站不应抓取。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        recipe_result = next(r for r in results if "allrecipes.com" in r.url)
        assert recipe_result.should_crawl is False

    @pytest.mark.asyncio
    async def test_amazon_blocked_domain(self, filter_instance, tim_cook_candidates):
        """Amazon 购物页面被阻止。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        amazon_result = next(r for r in results if "amazon.com" in r.url)
        assert amazon_result.should_crawl is False
        assert amazon_result.skip_reason == CrawlSkipReason.BLOCKED_DOMAIN

    @pytest.mark.asyncio
    async def test_login_page_low_relevance(self, filter_instance, tim_cook_candidates):
        """登录页面低相关性。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        login_result = next(r for r in results if "login" in r.url)
        assert login_result.should_crawl is False

    @pytest.mark.asyncio
    async def test_wikipedia_low_priority(self, filter_instance, tim_cook_candidates):
        """Wikipedia 默认低优先。"""
        results = await filter_instance.filter_candidates(
            candidates=tim_cook_candidates,
            topic="Tim Cook",
            canonical_topic="Tim Cook",
        )

        wiki_result = next(r for r in results if "wikipedia.org" in r.url)
        # Wikipedia 有主题匹配加分，但有低优先减分
        # 最终可能刚好在阈值附近
        assert wiki_result.relevance_score < 0.8  # 不应该是最高分

    @pytest.mark.asyncio
    async def test_duplicate_url_skipped(self, filter_instance):
        """重复 URL 被跳过。"""
        candidates = [
            {"url": "https://example.com/article", "title": "Article", "snippet": "Content", "rank": 1},
            {"url": "https://example.com/article", "title": "Article", "snippet": "Content", "rank": 2},
            {"url": "https://example.com/article/", "title": "Article", "snippet": "Content", "rank": 3},
        ]

        results = await filter_instance.filter_candidates(
            candidates=candidates,
            topic="Test Topic",
        )

        duplicates = [r for r in results if r.skip_reason == CrawlSkipReason.DUPLICATE_URL]
        assert len(duplicates) >= 1  # 至少一个重复

    @pytest.mark.asyncio
    async def test_top30_limit(self, filter_instance):
        """top30 模式最多保留 30 个候选。"""
        candidates = [
            {"url": f"https://example{i}.com", "title": f"Page {i}", "snippet": "Content", "rank": i}
            for i in range(50)
        ]

        results = await filter_instance.filter_candidates(
            candidates=candidates,
            topic="Test",
            depth=SearchResultDepth.TOP30,
        )

        assert len(results) <= 30

    @pytest.mark.asyncio
    async def test_top100_limit(self, filter_instance):
        """top100 模式最多保留 100 个候选。"""
        candidates = [
            {"url": f"https://example{i}.com", "title": f"Page {i}", "snippet": "Content", "rank": i}
            for i in range(150)
        ]

        results = await filter_instance.filter_candidates(
            candidates=candidates,
            topic="Test",
            depth=SearchResultDepth.TOP100,
        )

        assert len(results) <= 100

    @pytest.mark.asyncio
    async def test_filter_disabled_all_pass(self):
        """过滤器禁用时全部通过。"""
        config = {"enabled": False}
        filter_instance = RelevanceFilter(config=config)

        candidates = [
            {"url": "https://amazon.com/product", "title": "Product", "snippet": "Buy now"},
        ]

        results = await filter_instance.filter_candidates(
            candidates=candidates,
            topic="Test",
        )

        assert all(r.should_crawl for r in results)
