"""AIGateway 单元测试。"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, Field

from app.ai.errors import LLMFallbackRequired, LLMTaskFailed
from app.ai.gateway import AIGateway
from app.ai.prompts import PromptStore
from app.ai.router import LLMRouter
from app.ai.tasks import LLMTaskConfig, reset_config_cache
from app.providers.llm.base import BaseLLMProvider, LLMRequest, LLMResponse, ProviderHealth
from core.config import reset_settings


# === Test fixtures ===


class _MockProvider(BaseLLMProvider):
    """测试用 mock provider。"""

    def __init__(self, response_text: str = "mock") -> None:
        self._response_text = response_text

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=self._response_text,
            provider="mock",
            model=request.model,
            latency_ms=1,
            input_chars=len(request.user_prompt),
            output_chars=len(self._response_text),
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="mock", reachable=True)


class _SampleOutput(BaseModel):
    name: str
    score: float = 0.0
    tags: list[str] = Field(default_factory=list)


TEMPLATE_DIR = Path("config/prompt_templates")


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_config_cache()
    reset_settings()
    yield  # type: ignore[misc]
    reset_config_cache()
    reset_settings()


@pytest.fixture
def mock_provider() -> _MockProvider:
    return _MockProvider(response_text='{"name": "test", "score": 0.9, "tags": ["a"]}')


@pytest.fixture
def text_provider() -> _MockProvider:
    return _MockProvider(response_text="plain text response")


@pytest.fixture
def prompt_store() -> PromptStore:
    return PromptStore(template_dir=TEMPLATE_DIR)


def _make_gateway(provider: _MockProvider, prompt_store: PromptStore) -> AIGateway:
    """创建 gateway，mock 掉 router 和 task config。"""
    router = LLMRouter.__new__(LLMRouter)
    router._providers_config = {}
    router._config_path = Path("/dev/null")
    # patch get_provider to return our mock
    router.get_provider = lambda name: provider  # type: ignore[assignment]
    return AIGateway(router=router, prompt_store=prompt_store)


# === run_text 测试 ===


class TestRunText:
    @pytest.mark.asyncio
    async def test_success(self, text_provider: _MockProvider, prompt_store: PromptStore) -> None:
        gateway = _make_gateway(text_provider, prompt_store)
        with _patch_task_config():
            result = await gateway.run_text(
                "topic_understanding",
                {"topic": "量子计算"},
                language="zh",
            )
        assert result == "plain text response"

    @pytest.mark.asyncio
    async def test_max_input_chars_applied(
        self, text_provider: _MockProvider, prompt_store: PromptStore
    ) -> None:
        gateway = _make_gateway(text_provider, prompt_store)
        # 使用很小的 max_input_chars
        config = LLMTaskConfig(
            provider="mock",
            model="test",
            max_input_chars=50,
            json_required=False,
            require_llm=False,
        )
        with _patch_task_config(config):
            result = await gateway.run_text(
                "topic_understanding",
                {"topic": "A" * 200},
                language="zh",
            )
        # 应该成功返回（prompt 被截断但不影响调用）
        assert result == "plain text response"


# === run_json 测试 ===


class TestRunJson:
    @pytest.mark.asyncio
    async def test_success(self, mock_provider: _MockProvider, prompt_store: PromptStore) -> None:
        gateway = _make_gateway(mock_provider, prompt_store)
        with _patch_task_config(LLMTaskConfig(
            provider="mock", model="test", json_required=True, require_llm=False,
        )):
            result = await gateway.run_json(
                "topic_understanding",
                {"topic": "AI"},
                output_schema=_SampleOutput,
                language="zh",
            )
        assert isinstance(result, _SampleOutput)
        assert result.name == "test"
        assert result.score == 0.9
        assert result.tags == ["a"]

    @pytest.mark.asyncio
    async def test_parse_failure_triggers_fallback(
        self, prompt_store: PromptStore
    ) -> None:
        bad_provider = _MockProvider(response_text="not json at all")
        gateway = _make_gateway(bad_provider, prompt_store)
        config = LLMTaskConfig(
            provider="mock",
            model="test",
            json_required=True,
            retry_on_parse_error=True,
            max_retries=1,
            require_llm=False,
            fallback="rule_based",
        )
        with _patch_task_config(config):
            with pytest.raises(LLMFallbackRequired) as exc_info:
                await gateway.run_json(
                    "topic_understanding",
                    {"topic": "test"},
                    output_schema=_SampleOutput,
                )
        assert exc_info.value.fallback == "rule_based"
        assert exc_info.value.task == "topic_understanding"

    @pytest.mark.asyncio
    async def test_require_llm_true_raises_task_failed(
        self, prompt_store: PromptStore
    ) -> None:
        bad_provider = _MockProvider(response_text="invalid")
        gateway = _make_gateway(bad_provider, prompt_store)
        config = LLMTaskConfig(
            provider="mock",
            model="test",
            json_required=True,
            retry_on_parse_error=False,
            max_retries=0,
            require_llm=True,
        )
        with _patch_task_config(config):
            with pytest.raises(LLMTaskFailed) as exc_info:
                await gateway.run_json(
                    "topic_understanding",
                    {"topic": "test"},
                    output_schema=_SampleOutput,
                )
        assert exc_info.value.task == "topic_understanding"


# === max_input_chars 测试 ===


class TestMaxInputChars:
    @pytest.mark.asyncio
    async def test_long_prompt_truncated(
        self, prompt_store: PromptStore
    ) -> None:
        """验证超长 prompt 被截断后仍能正常调用。"""
        captured_requests: list[LLMRequest] = []

        class _CapturingProvider(BaseLLMProvider):
            @property
            def provider_name(self) -> str:
                return "capture"

            async def generate(self, request: LLMRequest) -> LLMResponse:
                captured_requests.append(request)
                return LLMResponse(
                    text="ok", provider="capture", model="m",
                    input_chars=len(request.user_prompt), output_chars=2,
                )

            async def health_check(self) -> ProviderHealth:
                return ProviderHealth(provider="capture", reachable=True)

        provider = _CapturingProvider()
        gateway = _make_gateway(provider, prompt_store)  # type: ignore[arg-type]
        config = LLMTaskConfig(
            provider="capture",
            model="test",
            max_input_chars=80,
            json_required=False,
            require_llm=False,
        )
        with _patch_task_config(config):
            await gateway.run_text(
                "topic_understanding",
                {"topic": "X" * 500},
                language="zh",
            )
        # prompt 应该被截断到 max_input_chars 以内
        assert len(captured_requests[0].user_prompt) <= 80


# === Helpers ===


def _patch_task_config(config: LLMTaskConfig | None = None):
    """Patch load_llm_task_config 返回指定配置。"""
    if config is None:
        config = LLMTaskConfig(
            provider="mock",
            model="test",
            json_required=False,
            require_llm=False,
        )
    return patch("app.ai.gateway.load_llm_task_config", return_value=config)
