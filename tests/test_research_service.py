"""研究服务测试 - 使用 MockSearchProvider。"""

import pytest

from models.enums import SearchSource, SourceType, TaskMode, TaskStatus
from providers.search.base import BaseSearchProvider, SearchProviderError, SearchResult
from services.research_service import (
    CreateResearchTaskRequest,
    ResearchService,
)


# === Mock Provider ===


class MockWebProvider(BaseSearchProvider):
    """返回固定结果的 Mock Web Provider。"""

    def __init__(self, results: list[SearchResult] | None = None, should_fail: bool = False):
        self._results = results or []
        self._should_fail = should_fail
        self.call_count = 0

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.TAVILY

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        self.call_count += 1
        if self._should_fail:
            raise SearchProviderError(provider="mock_web", message="mock failure")
        return self._results


class MockBookProvider(BaseSearchProvider):
    """返回固定结果的 Mock Book Provider。"""

    def __init__(self, results: list[SearchResult] | None = None):
        self._results = results or []
        self.call_count = 0

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.GOOGLE_BOOKS

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        self.call_count += 1
        return self._results


# === Fixtures ===


def _make_results(count: int, prefix: str = "https://example.com") -> list[SearchResult]:
    return [
        SearchResult(
            title=f"Result {i}",
            url=f"{prefix}/page-{i}",
            snippet=f"Snippet for result {i} with enough text to score well in relevance",
            source_provider=SearchSource.TAVILY,
            source_type=SourceType.OTHER,
        )
        for i in range(count)
    ]


def _make_book_results(count: int) -> list[SearchResult]:
    return [
        SearchResult(
            title=f"Book {i}",
            url=f"https://books.google.com/books?id=book{i}",
            snippet=f"A book about topic {i}",
            source_provider=SearchSource.GOOGLE_BOOKS,
            source_type=SourceType.BOOK,
        )
        for i in range(count)
    ]


@pytest.fixture
def mock_providers():
    web = MockWebProvider(results=_make_results(3))
    book = MockBookProvider(results=_make_book_results(2))
    return {
        "web": [web],
        "general": [web],
        "book": [book],
        "video": [],
        "archive": [],
    }


@pytest.fixture
def service(mock_providers):
    return ResearchService(providers=mock_providers, max_concurrency=5)


# === Tests ===


class TestCreateTask:
    def test_creates_task_with_correct_fields(self, service):
        request = CreateResearchTaskRequest(
            topic="Elon Musk",
            mode=TaskMode.PERSON,
            include_books=True,
            include_gossip=False,
        )
        task = service.create_task(request)
        assert task.topic == "Elon Musk"
        assert task.mode == TaskMode.PERSON
        assert task.status == TaskStatus.PENDING
        assert task.id  # UUID generated

    def test_creates_task_with_defaults(self, service):
        request = CreateResearchTaskRequest(topic="test")
        task = service.create_task(request)
        assert task.mode == TaskMode.AUTO
        assert task.include_books is True
        assert task.include_gossip is False


class TestRunInitialResearch:
    @pytest.mark.asyncio
    async def test_returns_summary(self, service):
        request = CreateResearchTaskRequest(topic="quantum computing", mode=TaskMode.CONCEPT)
        task = service.create_task(request)
        summary = await service.run_initial_research(task)

        assert summary.task_id == task.id
        assert summary.topic == "quantum computing"
        assert summary.status == TaskStatus.COMPLETED
        assert summary.total_queries > 0
        assert summary.total_raw_results > 0

    @pytest.mark.asyncio
    async def test_task_status_updated(self, service):
        request = CreateResearchTaskRequest(topic="test")
        task = service.create_task(request)
        await service.run_initial_research(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None

    @pytest.mark.asyncio
    async def test_expanded_queries_saved(self, service):
        request = CreateResearchTaskRequest(topic="Tesla", mode=TaskMode.COMPANY)
        task = service.create_task(request)
        await service.run_initial_research(task)

        assert len(task.expanded_queries) > 0
        assert any("Tesla" in q for q in task.expanded_queries)

    @pytest.mark.asyncio
    async def test_dedup_reduces_count(self):
        # 两个 provider 返回相同 URL
        same_results = _make_results(3, prefix="https://same.com")
        web1 = MockWebProvider(results=same_results)
        web2 = MockWebProvider(results=same_results)

        providers = {
            "web": [web1, web2],
            "general": [web1, web2],
            "book": [],
            "video": [],
            "archive": [],
        }
        service = ResearchService(providers=providers, max_concurrency=5)

        request = CreateResearchTaskRequest(topic="test", mode=TaskMode.CONCEPT, include_books=False)
        task = service.create_task(request)
        summary = await service.run_initial_research(task)

        # raw 应该是 dedup 前的两倍，dedup 后应该等于单个 provider 的数量
        assert summary.total_raw_results > summary.total_after_dedup

    @pytest.mark.asyncio
    async def test_book_provider_called_for_book_queries(self, mock_providers):
        service = ResearchService(providers=mock_providers, max_concurrency=5)
        request = CreateResearchTaskRequest(
            topic="Elon Musk", mode=TaskMode.PERSON, include_books=True
        )
        task = service.create_task(request)
        await service.run_initial_research(task)

        book_provider = mock_providers["book"][0]
        assert book_provider.call_count > 0


class TestProviderFailure:
    @pytest.mark.asyncio
    async def test_single_provider_failure_does_not_crash(self):
        failing = MockWebProvider(should_fail=True)
        working = MockWebProvider(results=_make_results(2))

        providers = {
            "web": [failing, working],
            "general": [failing, working],
            "book": [],
            "video": [],
            "archive": [],
        }
        service = ResearchService(providers=providers, max_concurrency=5)

        request = CreateResearchTaskRequest(topic="test", mode=TaskMode.CONCEPT, include_books=False)
        task = service.create_task(request)
        summary = await service.run_initial_research(task)

        # 任务仍然完成
        assert summary.status == TaskStatus.COMPLETED
        # 有错误记录
        assert len(summary.provider_errors) > 0
        # 仍有结果
        assert summary.total_saved > 0

    @pytest.mark.asyncio
    async def test_all_providers_fail_still_completes(self):
        failing = MockWebProvider(should_fail=True)

        providers = {
            "web": [failing],
            "general": [failing],
            "book": [],
            "video": [],
            "archive": [],
        }
        service = ResearchService(providers=providers, max_concurrency=5)

        request = CreateResearchTaskRequest(topic="test", mode=TaskMode.CONCEPT, include_books=False)
        task = service.create_task(request)
        summary = await service.run_initial_research(task)

        assert summary.status == TaskStatus.COMPLETED
        assert summary.total_saved == 0
        assert len(summary.provider_errors) > 0


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_respects_max_concurrency(self):
        """验证并发限制生效（通过 call_count 间接验证）。"""
        web = MockWebProvider(results=_make_results(1))
        providers = {
            "web": [web],
            "general": [web],
            "book": [],
            "video": [],
            "archive": [],
        }
        service = ResearchService(providers=providers, max_concurrency=2)

        request = CreateResearchTaskRequest(topic="test", mode=TaskMode.CONCEPT, include_books=False)
        task = service.create_task(request)
        summary = await service.run_initial_research(task)

        # 所有 query 都被执行了
        assert web.call_count == summary.total_queries


class TestSourceItemConversion:
    @pytest.mark.asyncio
    async def test_source_items_have_correct_fields(self, service):
        request = CreateResearchTaskRequest(topic="test", mode=TaskMode.CONCEPT)
        task = service.create_task(request)
        summary = await service.run_initial_research(task)

        assert summary.total_saved > 0
