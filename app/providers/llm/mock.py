"""Mock LLM Provider - 用于测试，不访问网络。"""

from app.providers.llm.base import BaseLLMProvider, LLMRequest, LLMResponse, ProviderHealth


class MockLLMProvider(BaseLLMProvider):
    """返回预设文本的 Mock Provider。"""

    def __init__(self, response_text: str = "mock response") -> None:
        self._response_text = response_text

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        input_chars = len(request.user_prompt) + len(request.system_prompt or "")
        output_chars = len(self._response_text)
        return LLMResponse(
            text=self._response_text,
            provider=self.provider_name,
            model=request.model,
            latency_ms=0,
            input_chars=input_chars,
            output_chars=output_chars,
            raw=None,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.provider_name,
            reachable=True,
            latency_ms=0,
            error=None,
        )
