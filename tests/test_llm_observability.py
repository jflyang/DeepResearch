"""LLM Observability 测试 - 验证 AIGateway 的 trace 记录行为。"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.gateway import AIGateway
from app.ai.prompts import PromptStore
from app.ai.router import LLMRouter
from app.ai.tasks import reset_config_cache
from app.providers.llm.base import LLMResponse, ProviderHealth
from app.providers.llm.mock import MockLLMProvider
from app.tracing.models import TraceStep
from app.tracing.recorder import TraceRecorder, get_recorder, _sanitize


@pytest.fixture(autouse=True)
def _reset_config():
    reset_config_cache()
    yield
    reset_config_cache()


@pytest.fixture
def mock_provider():
    return MockLLMProvider(response_text='{"result": "test"}')


@pytest.fixture
def gateway(mock_provider):
    router = LLMRouter()
    prompt_store = PromptStore()
    gw = AIGateway(router=router, prompt_store=prompt_store)
    return gw


class TestAIGatewayTrace:
    def test_llm_call_records_used_llm(self) -> None:
        """AIGateway 调用时记录 used_llm trace event。"""
        recorder = get_recorder()
        recorder.clear("test-obs-1")

        mock_provider = MockLLMProvider(response_text="hello world")
        router = LLMRouter()
        prompt_store = PromptStore()
        gw = AIGateway(router=router, prompt_store=prompt_store)
        gw.set_task_id("test-obs-1")

        # Mock get_provider to return our mock
        with patch.object(router, "get_provider", return_value=mock_provider):
            with patch.object(prompt_store, "render", return_value="test prompt"):
                result = asyncio.run(gw.run_text("topic_understanding", {"topic": "test"}))

        events = recorder.get_events("test-obs-1")
        llm_finished = [e for e in events if e.step == TraceStep.LLM_CALL_FINISHED]
        assert len(llm_finished) >= 1
        assert llm_finished[0].provider == "mock"
        assert llm_finished[0].output_summary is not None
        assert llm_finished[0].output_summary.get("task_name") == "topic_understanding"

        recorder.clear("test-obs-1")

    def test_llm_failure_records_error(self) -> None:
        """LLM 调用失败时记录 error trace event。"""
        from app.ai.errors import LLMFallbackRequired

        recorder = get_recorder()
        recorder.clear("test-obs-2")

        mock_provider = MockLLMProvider()
        mock_provider.generate = AsyncMock(side_effect=RuntimeError("connection refused"))
        router = LLMRouter()
        prompt_store = PromptStore()
        gw = AIGateway(router=router, prompt_store=prompt_store)
        gw.set_task_id("test-obs-2")

        with patch.object(router, "get_provider", return_value=mock_provider):
            with patch.object(prompt_store, "render", return_value="test prompt"):
                with pytest.raises(LLMFallbackRequired):
                    asyncio.run(gw.run_text("topic_understanding", {"topic": "test"}))

        events = recorder.get_events("test-obs-2")
        llm_failed = [e for e in events if e.step == TraceStep.LLM_CALL_FAILED]
        assert len(llm_failed) == 1
        assert llm_failed[0].level == "error"
        assert "connection refused" in llm_failed[0].error_message

        recorder.clear("test-obs-2")

    def test_trace_does_not_contain_api_key(self) -> None:
        """Trace 不包含 API key。"""
        data = {"api_key": "sk-secret-123", "model": "gpt-4", "query": "test"}
        sanitized = _sanitize(data)
        assert sanitized["api_key"] == "***"
        assert sanitized["model"] == "gpt-4"
        assert sanitized["query"] == "test"

    def test_trace_does_not_contain_full_prompt(self) -> None:
        """Trace 不记录完整 prompt，只记录 input_chars。"""
        recorder = get_recorder()
        recorder.clear("test-obs-3")

        mock_provider = MockLLMProvider(response_text="output")
        router = LLMRouter()
        prompt_store = PromptStore()
        gw = AIGateway(router=router, prompt_store=prompt_store)
        gw.set_task_id("test-obs-3")

        long_prompt = "x" * 5000

        with patch.object(router, "get_provider", return_value=mock_provider):
            with patch.object(prompt_store, "render", return_value=long_prompt):
                asyncio.run(gw.run_text("topic_understanding", {"topic": "test"}))

        events = recorder.get_events("test-obs-3")
        # 确保没有事件包含完整 prompt
        for e in events:
            if e.input_summary:
                assert "x" * 100 not in str(e.input_summary)
                # 但应该有 input_chars
                if "input_chars" in e.input_summary:
                    assert e.input_summary["input_chars"] > 0

        recorder.clear("test-obs-3")

    def test_no_task_id_does_not_crash(self) -> None:
        """没有设置 task_id 时不崩溃。"""
        mock_provider = MockLLMProvider(response_text="ok")
        router = LLMRouter()
        prompt_store = PromptStore()
        gw = AIGateway(router=router, prompt_store=prompt_store)
        # 不调用 set_task_id

        with patch.object(router, "get_provider", return_value=mock_provider):
            with patch.object(prompt_store, "render", return_value="prompt"):
                result = asyncio.run(gw.run_text("topic_understanding", {"topic": "test"}))
                assert result == "ok"


class TestRuleOnlySteps:
    def test_rule_only_steps_can_be_recorded(self) -> None:
        """rule-only steps 能记录。"""
        recorder = TraceRecorder()
        recorder.record(
            task_id="t1",
            step="url_dedupe",
            phase="processing",
            message="Rule-only: URL deduplication",
            input_summary={"rule_only": True, "reason": "deterministic operation"},
        )
        events = recorder.get_events("t1")
        assert len(events) == 1
        assert events[0].input_summary["rule_only"] is True
