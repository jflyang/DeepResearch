"""Ollama LLM Provider - 通过 /api/chat 调用本地或局域网 Ollama 实例。"""

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


class OllamaModelInfo(BaseModel):
    """Ollama 模型信息。"""

    name: str
    modified_at: str = ""
    size: int = 0
    digest: str | None = None


class OllamaProviderError(Exception):
    """Ollama Provider 层异常，由 gateway 决定是否 fallback。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OllamaProvider(BaseLLMProvider):
    """通过 Ollama /api/chat 接口调用本地或局域网模型。"""

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        messages = self._build_messages(request)
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }

        timeout = httpx.Timeout(request.timeout_seconds, connect=10.0)
        start = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.ConnectError as e:
            raise OllamaProviderError(
                message=f"Connection failed: {self._base_url}",
            ) from e
        except httpx.TimeoutException as e:
            raise OllamaProviderError(
                message=f"Request timed out after {request.timeout_seconds}s",
            ) from e

        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code < 200 or resp.status_code >= 300:
            raise OllamaProviderError(
                message=f"Non-2xx response: {resp.status_code}",
                status_code=resp.status_code,
            )

        try:
            data: dict[str, Any] = resp.json()
        except Exception as e:
            raise OllamaProviderError(
                message="Failed to parse JSON response",
            ) from e

        text = self._extract_text(data)
        input_chars = len(request.user_prompt) + len(request.system_prompt or "")

        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=request.model,
            latency_ms=latency_ms,
            input_chars=input_chars,
            output_chars=len(text),
            raw=data,
        )

    async def health_check(self) -> ProviderHealth:
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code == 200:
                return ProviderHealth(
                    provider=self.provider_name,
                    reachable=True,
                    latency_ms=latency_ms,
                    error=None,
                )
            return ProviderHealth(
                provider=self.provider_name,
                reachable=False,
                latency_ms=latency_ms,
                error=f"Status {resp.status_code}",
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ProviderHealth(
                provider=self.provider_name,
                reachable=False,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def list_models(self) -> list[OllamaModelInfo]:
        """调用 GET /api/tags 获取已安装模型列表。"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
        except httpx.ConnectError:
            logger.warning("list_models: connection failed to %s", self._base_url)
            return []
        except httpx.TimeoutException:
            logger.warning("list_models: timeout connecting to %s", self._base_url)
            return []

        if resp.status_code != 200:
            logger.warning("list_models: non-200 status %d", resp.status_code)
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        models_raw = data.get("models", [])
        if not isinstance(models_raw, list):
            return []

        result: list[OllamaModelInfo] = []
        for m in models_raw:
            if not isinstance(m, dict):
                continue
            name = m.get("name", "")
            if not name:
                continue
            result.append(OllamaModelInfo(
                name=name,
                modified_at=m.get("modified_at", ""),
                size=m.get("size", 0),
                digest=m.get("digest"),
            ))
        return result

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})
        return messages

    def _extract_text(self, data: dict[str, Any]) -> str:
        """从 /api/chat 响应中提取文本。"""
        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        raise OllamaProviderError(message="Response missing 'message.content' field")
