"""AI Gateway - LLM 调用统一入口。"""

import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai.budget import apply_input_budget
from app.ai.errors import LLMFallbackRequired, LLMTaskFailed
from app.ai.parser import LLMJsonParseError, LLMJsonSchemaError, parse_as
from app.ai.prompts import PromptStore
from app.ai.router import LLMRouter
from app.ai.tasks import LLMTaskConfig, load_llm_task_config
from app.providers.llm.base import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AIGateway:
    """统一 LLM 调用网关。"""

    def __init__(self, router: LLMRouter, prompt_store: PromptStore) -> None:
        self._router = router
        self._prompt_store = prompt_store

    async def run_text(
        self,
        task_name: str,
        payload: dict[str, Any],
        language: str = "zh",
    ) -> str:
        """执行文本生成任务，返回原始文本。"""
        config = load_llm_task_config(task_name)
        prompt = self._render_prompt(task_name, payload, language, config)
        response = await self._call_provider(task_name, prompt, config)
        return response.text

    async def run_json(
        self,
        task_name: str,
        payload: dict[str, Any],
        output_schema: type[T],
        language: str = "zh",
    ) -> T:
        """执行 JSON 生成任务，返回校验后的 schema 实例。"""
        config = load_llm_task_config(task_name)
        prompt = self._render_prompt(task_name, payload, language, config)

        last_error: Exception | None = None
        attempts = 1 + (config.max_retries if config.retry_on_parse_error else 0)

        for attempt in range(attempts):
            response = await self._call_provider(task_name, prompt, config)
            try:
                return parse_as(response.text, output_schema)
            except (LLMJsonParseError, LLMJsonSchemaError) as e:
                last_error = e
                logger.warning(
                    "parse_failed task=%s attempt=%d/%d",
                    task_name, attempt + 1, attempts,
                )

        # 所有重试耗尽
        self._raise_failure(task_name, config, str(last_error))
        raise AssertionError("unreachable")  # type hint helper

    def _render_prompt(
        self,
        task_name: str,
        payload: dict[str, Any],
        language: str,
        config: LLMTaskConfig,
    ) -> str:
        """渲染 prompt 并应用 max_input_chars 预算。"""
        raw_prompt = self._prompt_store.render(task_name, language, payload)
        return apply_input_budget(raw_prompt, config.max_input_chars)

    async def _call_provider(
        self,
        task_name: str,
        prompt: str,
        config: LLMTaskConfig,
    ) -> LLMResponse:
        """获取 provider 并调用 generate。"""
        provider = self._router.get_provider(config.provider)
        request = LLMRequest(
            model=config.model,
            user_prompt=prompt,
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
            timeout_seconds=config.timeout_seconds,
            json_required=config.json_required,
        )

        start = time.perf_counter()
        try:
            response = await provider.generate(request)
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "llm_call_error task=%s provider=%s model=%s latency_ms=%d error=%s",
                task_name, provider.provider_name, config.model, latency_ms, type(e).__name__,
            )
            self._raise_failure(task_name, config, str(e))
            raise AssertionError("unreachable")

        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "llm_call_ok task=%s provider=%s model=%s latency_ms=%d output_chars=%d",
            task_name, provider.provider_name, config.model, latency_ms, response.output_chars,
        )
        return response

    def _raise_failure(self, task_name: str, config: LLMTaskConfig, reason: str) -> None:
        """根据 require_llm 决定抛出哪种异常。"""
        if config.require_llm:
            raise LLMTaskFailed(task=task_name, reason=reason, provider=config.provider)
        raise LLMFallbackRequired(task=task_name, fallback=config.fallback, reason=reason)
