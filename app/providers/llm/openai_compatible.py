"""OpenAI-Compatible LLM Provider - 支持 DeepSeek、OpenAI 及其他兼容 API。"""

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.providers.llm.base import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderHealth,
)

logger = logging.getLogger(__name__)


class CloudModelInfo(BaseModel):
    """云端模型信息。"""

    id: str
    owned_by: str = ""
    created: int | None = None


class OpenAICompatibleProviderError(Exception):
    """OpenAI-Compatible Provider 层异常。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OpenAICompatibleProvider(BaseLLMProvider):
    """通过 OpenAI-compatible Chat Completions API 调用云端模型。"""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str = "",
        timeout_seconds: int = 120,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout_seconds
        self._extra_headers = extra_headers or {}

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._default_model
        messages = self._build_messages(request)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        timeout = httpx.Timeout(request.timeout_seconds or self._timeout, connect=10.0)
        start = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.ConnectError as e:
            raise OpenAICompatibleProviderError(
                message=f"Connection failed: {self._base_url}",
            ) from e
        except httpx.TimeoutException as e:
            raise OpenAICompatibleProviderError(
                message=f"Request timed out after {request.timeout_seconds}s",
            ) from e

        latency_ms = int((time.perf_counter() - start) * 1000)
        status_code = resp.status_code

        # HTTP 错误处理
        if status_code == 401 or status_code == 403:
            raise OpenAICompatibleProviderError(
                message="Authentication failed: invalid or missing API key",
                status_code=status_code,
            )
        if status_code == 429:
            raise OpenAICompatibleProviderError(
                message="Rate limited: too many requests",
                status_code=429,
            )
        if status_code >= 500:
            raise OpenAICompatibleProviderError(
                message=f"Server error: {status_code}",
                status_code=status_code,
            )
        if status_code < 200 or status_code >= 300:
            raise OpenAICompatibleProviderError(
                message=f"Non-2xx response: {status_code}",
                status_code=status_code,
            )

        # JSON 解析
        try:
            data: dict[str, Any] = resp.json()
        except Exception as e:
            raise OpenAICompatibleProviderError(
                message="Failed to parse JSON response",
            ) from e

        # 提取文本
        text = self._extract_text(data)
        input_chars = len(request.user_prompt) + len(request.system_prompt or "")

        logger.info(
            "openai_compatible_call provider=%s model=%s latency_ms=%d status=%d",
            self._name, model, latency_ms, status_code,
        )

        return LLMResponse(
            text=text,
            provider=self._name,
            model=model,
            latency_ms=latency_ms,
            input_chars=input_chars,
            output_chars=len(text),
            raw=data,
        )

    async def health_check(self) -> ProviderHealth:
        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            **self._extra_headers,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers=headers,
                )
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code == 200:
                return ProviderHealth(
                    provider=self._name, reachable=True, latency_ms=latency_ms,
                )
            return ProviderHealth(
                provider=self._name, reachable=False, latency_ms=latency_ms,
                error=f"Status {resp.status_code}",
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ProviderHealth(
                provider=self._name, reachable=False, latency_ms=latency_ms,
                error=str(e)[:200],
            )

    async def list_models(self) -> list[CloudModelInfo]:
        """调用 GET /models 获取可用模型列表。不支持时返回空列表。"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            **self._extra_headers,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers=headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException):
            return []

        if resp.status_code != 200:
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        models_raw = data.get("data", [])
        if not isinstance(models_raw, list):
            return []

        result: list[CloudModelInfo] = []
        for m in models_raw:
            if not isinstance(m, dict):
                continue
            model_id = m.get("id", "")
            if not model_id:
                continue
            result.append(CloudModelInfo(
                id=model_id,
                owned_by=m.get("owned_by", ""),
                created=m.get("created"),
            ))
        return result

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})
        return messages

    def _extract_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            raise OpenAICompatibleProviderError(
                message="Response missing 'choices' field",
            )
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            raise OpenAICompatibleProviderError(
                message="Response missing 'choices[0].message.content'",
            )
        return content
