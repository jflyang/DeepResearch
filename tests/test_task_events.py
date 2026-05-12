"""任务事件日志服务测试。"""

import pytest

from services.task_event_service import TaskEvent, clear_events, get_events, log_event


@pytest.fixture(autouse=True)
def clean_events():
    clear_events()
    yield
    clear_events()


class TestLogEvent:
    def test_basic_log(self):
        log_event("task-1", "task_created", "Task created")
        events = get_events("task-1")
        assert len(events) == 1
        assert events[0].event_type == "task_created"
        assert events[0].message == "Task created"
        assert events[0].level == "info"

    def test_log_with_level(self):
        log_event("task-1", "provider_failed", "Timeout", level="error")
        events = get_events("task-1")
        assert events[0].level == "error"

    def test_log_with_payload(self):
        log_event("task-1", "scoring_finished", "Done", payload={"count": 42})
        events = get_events("task-1")
        assert events[0].payload == {"count": 42}

    def test_multiple_events(self):
        log_event("task-1", "task_created", "Created")
        log_event("task-1", "query_expanded", "Expanded")
        log_event("task-1", "search_started", "Searching")
        events = get_events("task-1")
        assert len(events) == 3

    def test_events_ordered_newest_first(self):
        log_event("task-1", "first", "1")
        log_event("task-1", "second", "2")
        log_event("task-1", "third", "3")
        events = get_events("task-1")
        # 最新在前
        assert events[0].event_type == "third"
        assert events[-1].event_type == "first"

    def test_separate_tasks(self):
        log_event("task-1", "event_a", "A")
        log_event("task-2", "event_b", "B")
        assert len(get_events("task-1")) == 1
        assert len(get_events("task-2")) == 1

    def test_never_raises(self):
        """log_event 绝不抛出异常。"""
        # 即使传入奇怪的参数也不应崩溃
        log_event(None, None, None)  # type: ignore
        # 不应抛出

    def test_get_events_nonexistent_task(self):
        events = get_events("nonexistent")
        assert events == []


class TestGetEventsLimit:
    def test_limit_parameter(self):
        for i in range(30):
            log_event("task-1", f"event_{i}", f"Message {i}")

        events = get_events("task-1", limit=10)
        assert len(events) == 10

    def test_limit_default(self):
        for i in range(60):
            log_event("task-1", f"event_{i}", f"Message {i}")

        events = get_events("task-1")
        assert len(events) == 50  # default limit


class TestClearEvents:
    def test_clear_specific_task(self):
        log_event("task-1", "a", "A")
        log_event("task-2", "b", "B")
        clear_events("task-1")
        assert get_events("task-1") == []
        assert len(get_events("task-2")) == 1

    def test_clear_all(self):
        log_event("task-1", "a", "A")
        log_event("task-2", "b", "B")
        clear_events()
        assert get_events("task-1") == []
        assert get_events("task-2") == []


class TestTaskEventModel:
    def test_model_fields(self):
        event = TaskEvent(task_id="t1", event_type="test", message="hello")
        assert event.task_id == "t1"
        assert event.event_type == "test"
        assert event.level == "info"
        assert event.payload == {}
        assert event.id  # UUID generated
        assert event.created_at  # timestamp generated


class TestIntegrationWithResearchService:
    """验证 research_service 中的事件记录。"""

    @pytest.mark.asyncio
    async def test_research_logs_events(self):
        from models.enums import SearchSource, SourceType, TaskMode
        from providers.search.base import BaseSearchProvider, SearchResult
        from services.research_service import CreateResearchTaskRequest, ResearchService

        class FakeProvider(BaseSearchProvider):
            @property
            def provider_name(self):
                return SearchSource.TAVILY

            async def search(self, query, limit=10):
                return [SearchResult(
                    title="Test",
                    url="https://example.com/1",
                    snippet="Content",
                    source_provider=SearchSource.TAVILY,
                    source_type=SourceType.OTHER,
                )]

        providers = {
            "web": [FakeProvider()],
            "general": [FakeProvider()],
            "book": [],
            "video": [],
            "archive": [],
        }
        service = ResearchService(providers=providers, max_concurrency=5)

        request = CreateResearchTaskRequest(topic="Test", mode=TaskMode.CONCEPT, include_books=False)
        task = service.create_task(request)
        await service.run_initial_research(task)

        events = get_events(task.id)
        event_types = [e.event_type for e in events]

        assert "task_created" in event_types
        assert "search_started" in event_types
        assert "query_expanded" in event_types
        assert "dedupe_finished" in event_types
        assert "scoring_finished" in event_types
        assert "task_completed" in event_types
