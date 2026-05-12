"""MockLLMProvider 单元测试。"""

import pytest

from app.providers.llm.base import LLMRequest, ProviderHealth
from app.providers.llm.mock import MockLLMProvider


@pytest.fixture
def provider() -> MockLLMProvider:
    return MockLLMProvider(response_text="hello world")


@pytest.mark.asyncio
async def test_generate_returns_expected_text(provider: MockLLMProvider) -> None:
    request = LLMRequest(model="test-model", user_prompt="say hi")
    response = await provider.generate(request)
    assert response.text == "hello world"
    assert response.provider == "mock"
    assert response.model == "test-model"


@pytest.mark.asyncio
async def test_generate_input_output_chars(provider: MockLLMProvider) -> None:
    request = LLMRequest(
        model="m",
        system_prompt="system",
        user_prompt="user",
    )
    response = await provider.generate(request)
    assert response.input_chars == len("system") + len("user")
    assert response.output_chars == len("hello world")


@pytest.mark.asyncio
async def test_generate_no_system_prompt(provider: MockLLMProvider) -> None:
    request = LLMRequest(model="m", user_prompt="prompt only")
    response = await provider.generate(request)
    assert response.input_chars == len("prompt only")


@pytest.mark.asyncio
async def test_health_check(provider: MockLLMProvider) -> None:
    health = await provider.health_check()
    assert isinstance(health, ProviderHealth)
    assert health.reachable is True
    assert health.provider == "mock"
    assert health.error is None
