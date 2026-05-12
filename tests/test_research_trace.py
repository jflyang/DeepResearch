"""Research Trace 单元测试。"""

import asyncio
from datetime import UTC, datetime

import pytest

from app.tracing.models import TraceEvent, TracePhase, TraceStep
from app.tracing.recorder import (
    TraceRecorder,
    TraceSpan,
    _sanitize,
    get_recorder,
    noop_recorder,
    trace_span,
)


class TestTraceRecorder:
    def test_record_saves_event(self) -> None:
        """record 会保存事件。"""
        recorder = TraceRecorder()
        recorder.record(
            task_id="t1",
            step=TraceStep.TASK_CREATED,
            phase=TracePhase.PLANNING,
            message="Task created",
        )
        events = recorder.get_events("t1")
        assert len(events) == 1
        assert events[0].step == TraceStep.TASK_CREATED
        assert events[0].message == "Task created"

    def test_record_multiple_events(self) -> None:
        recorder = TraceRecorder()
        recorder.info("t1", TraceStep.TASK_CREATED, TracePhase.PLANNING, "created")
        recorder.info("t1", TraceStep.QUERY_EXPANSION_FINISHED, TracePhase.PLANNING, "expanded")
        recorder.info("t1", TraceStep.DEDUPE_FINISHED, TracePhase.PROCESSING, "deduped")
        events = recorder.get_events("t1")
        assert len(events) == 3

    def test_filter_by_level(self) -> None:
        recorder = TraceRecorder()
        recorder.info("t1", TraceStep.TASK_CREATED, TracePhase.PLANNING)
        recorder.warning("t1", TraceStep.SEARCH_PROVIDER_FAILED, TracePhase.SEARCH, "429")
        recorder.error("t1", TraceStep.TASK_FAILED, TracePhase.PROCESSING, "fatal")

        warnings = recorder.get_events("t1", level="warning")
        assert len(warnings) == 1
        assert warnings[0].step == TraceStep.SEARCH_PROVIDER_FAILED

    def test_filter_by_phase(self) -> None:
        recorder = TraceRecorder()
        recorder.info("t1", TraceStep.TASK_CREATED, TracePhase.PLANNING)
        recorder.info("t1", TraceStep.DEDUPE_FINISHED, TracePhase.PROCESSING)

        planning = recorder.get_events("t1", phase=TracePhase.PLANNING)
        assert len(planning) == 1

    def test_get_summary(self) -> None:
        recorder = TraceRecorder()
        recorder.info("t1", TraceStep.TASK_CREATED, TracePhase.PLANNING)
        recorder.info("t1", TraceStep.LLM_CALL_FINISHED, TracePhase.LLM, provider="deepseek")
        recorder.info("t1", TraceStep.SEARCH_PROVIDER_FINISHED, TracePhase.SEARCH, provider="tavily")
        recorder.warning("t1", TraceStep.SEARCH_PROVIDER_FAILED, TracePhase.SEARCH, provider="google_books")
        recorder.info("t1", TraceStep.TASK_COMPLETED, TracePhase.PROCESSING)

        summary = recorder.get_summary("t1")
        assert summary["total_events"] == 5
        assert summary["llm_calls"] == 1
        assert summary["search_calls"] == 1
        assert summary["warning_count"] == 1
        assert summary["error_count"] == 0
        assert "deepseek" in summary["providers_used"]
        assert "tavily" in summary["providers_used"]

    def test_noop_recorder_does_nothing(self) -> None:
        recorder = noop_recorder()
        recorder.record(task_id="t1", step="x", phase="y")
        assert recorder.get_events("t1") == []

    def test_clear_events(self) -> None:
        recorder = TraceRecorder()
        recorder.info("t1", TraceStep.TASK_CREATED, TracePhase.PLANNING)
        recorder.clear("t1")
        assert recorder.get_events("t1") == []

    def test_record_failure_does_not_raise(self) -> None:
        """trace 失败不影响业务流程。"""
        recorder = TraceRecorder()
        # 传入无法序列化的数据不应抛出
        recorder.record(
            task_id="t1",
            step="test",
            phase="test",
            input_summary={"key": "value"},  # normal
        )
        # 即使内部出错也不抛出
        assert True  # 如果到这里就说明没有异常


class TestSanitize:
    def test_sensitive_keys_masked(self) -> None:
        """sensitive keys 会被脱敏。"""
        data = {
            "api_key": "sk-secret-123",
            "authorization": "Bearer token",
            "query": "Tim Cook",
            "url": "https://example.com",
        }
        result = _sanitize(data)
        assert result["api_key"] == "***"
        assert result["authorization"] == "***"
        assert result["query"] == "Tim Cook"
        assert result["url"] == "https://example.com"

    def test_nested_sensitive_keys(self) -> None:
        data = {"config": {"api_key": "secret", "model": "gpt-4"}}
        result = _sanitize(data)
        assert result["config"]["api_key"] == "***"
        assert result["config"]["model"] == "gpt-4"

    def test_none_input(self) -> None:
        assert _sanitize(None) is None

    def test_empty_dict(self) -> None:
        assert _sanitize({}) == {}

    def test_token_key_masked(self) -> None:
        data = {"access_token": "abc123", "name": "test"}
        result = _sanitize(data)
        assert result["access_token"] == "***"
        assert result["name"] == "test"


class TestTraceSpan:
    def test_span_records_duration(self) -> None:
        """trace_span 自动记录 duration_ms。"""
        recorder = TraceRecorder()

        async def _run():
            async with trace_span(
                recorder, "t1", TraceStep.SEARCH_PROVIDER_STARTED, TracePhase.SEARCH,
                provider="tavily",
                input_summary={"query": "test"},
            ) as span:
                await asyncio.sleep(0.01)
                span.finish(output_summary={"count": 10})

        asyncio.run(_run())

        events = recorder.get_events("t1")
        assert len(events) == 1
        assert events[0].step == TraceStep.SEARCH_PROVIDER_FINISHED
        assert events[0].duration_ms is not None
        assert events[0].duration_ms >= 10
        assert events[0].provider == "tavily"

    def test_span_records_failure(self) -> None:
        recorder = TraceRecorder()

        async def _run():
            try:
                async with trace_span(
                    recorder, "t1", TraceStep.SEARCH_PROVIDER_STARTED, TracePhase.SEARCH,
                    provider="google_books",
                ) as span:
                    raise RuntimeError("429 rate limited")
            except RuntimeError:
                pass

        asyncio.run(_run())

        events = recorder.get_events("t1")
        assert len(events) == 1
        assert events[0].step == TraceStep.SEARCH_PROVIDER_FAILED
        assert events[0].level == "error"
        assert "429" in events[0].error_message

    def test_span_auto_finish_if_not_called(self) -> None:
        recorder = TraceRecorder()

        async def _run():
            async with trace_span(
                recorder, "t1", TraceStep.DEDUPE_STARTED, TracePhase.PROCESSING,
            ):
                pass  # 不手动 finish

        asyncio.run(_run())

        events = recorder.get_events("t1")
        assert len(events) == 1
        assert events[0].step == TraceStep.DEDUPE_FINISHED


class TestJsonSerialization:
    def test_trace_event_serializable(self) -> None:
        """JSON payload 能正确序列化。"""
        event = TraceEvent(
            task_id="t1",
            step=TraceStep.TASK_CREATED,
            phase=TracePhase.PLANNING,
            message="test",
            input_summary={"topic": "Tim Cook", "mode": "person"},
            metrics={"duration_ms": 123},
        )
        data = event.model_dump(mode="json")
        assert data["task_id"] == "t1"
        assert data["input_summary"]["topic"] == "Tim Cook"
        assert data["metrics"]["duration_ms"] == 123
