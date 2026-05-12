"""LLM Provider 抽象基类与公共数据模型。"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    """LLM 调用请求。"""

    model: str
    system_prompt: str | None = None
    user_prompt: str
    temperature: float = 0.7
    max_output_tokens: int = 2048
    timeout_seconds: int = 120
    json_required: bool = False


class LLMResponse(BaseModel):
    """LLM 调用响应。"""

    text: str
    provider: str
    model: str
    latency_ms: int = 0
    input_chars: int = 0
    output_chars: int = 0
    raw: dict | None = None


class ProviderHealth(BaseModel):
    """Provider 健康检查结果。"""

    provider: str
    reachable: bool
    latency_ms: int | None = None
    error: str | None = None


class BaseLLMProvider(ABC):
    """所有 LLM Provider 必须实现此接口。"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 标识名。"""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成文本。"""

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """健康检查。"""
