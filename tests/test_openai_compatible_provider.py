"""OpenAICompatibleProvider 单元测试 - 使用 respx mock，不访问真实网络。"""

import json

import pytest
import respx
from httpx import Response

from app.providers.llm.base import LLMRequest, ProviderHealth
from app.providers.llm.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAICompatibleProviderError,
)

BASE_URL = "https://api.deepseek.com/v1"


@pytest.fixture
def provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="deepseek",
        base_url=BASE_URL,
        api_key="sk-test-key",
        default_model="deepseek-chat",
        timeout_seconds=30,
    )


@pytest.fixture
def chat_request() -> LLMRequest:
    return LLMRequest(
        model="deepseek-chat",
        system_prompt="You are helpful.",
        user_prompt="Hello",
        temperature=0.3,
        max_output_tokens=100,
        timeout_seconds=30,
    )


# === generate 成功 ===


@respx.mock
@pytest.mark.asyncio
async def test_generate_success(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Hi there!"}}],
            "usage": {"total_tokens": 10},
        })
    )
    resp = await provider.generate(chat_request)
    assert resp.text == "Hi there!"
    assert resp.provider == "deepseek"
    assert resp.model == "deepseek-chat"
    assert resp.output_chars == len("Hi there!")
    assert resp.input_chars == len("You are helpful.") + len("Hello")


# === system_prompt 为空时只发送 user message ===


@respx.mock
@pytest.mark.asyncio
async def test_no_system_prompt(provider: OpenAICompatibleProvider) -> None:
    request = LLMRequest(model="deepseek-chat", user_prompt="just user")
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        })
    )
    await provider.generate(request)

    body = json.loads(respx.calls[0].request.content)
    roles = [m["role"] for m in body["messages"]]
    assert "system" not in roles
    assert roles == ["user"]


# === 401 返回清晰错误 ===


@respx.mock
@pytest.mark.asyncio
async def test_401_auth_error(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(401, json={"error": {"message": "Invalid API key"}})
    )
    with pytest.raises(OpenAICompatibleProviderError, match="Authentication failed"):
        await provider.generate(chat_request)


# === 429 返回清晰错误 ===


@respx.mock
@pytest.mark.asyncio
async def test_429_rate_limit(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(429, json={"error": {"message": "Rate limit exceeded"}})
    )
    with pytest.raises(OpenAICompatibleProviderError, match="Rate limited"):
        await provider.generate(chat_request)


# === 5xx 服务错误 ===


@respx.mock
@pytest.mark.asyncio
async def test_500_server_error(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(502, text="Bad Gateway")
    )
    with pytest.raises(OpenAICompatibleProviderError, match="Server error"):
        await provider.generate(chat_request)


# === 响应缺少 choices ===


@respx.mock
@pytest.mark.asyncio
async def test_missing_choices(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(200, json={"id": "123"})
    )
    with pytest.raises(OpenAICompatibleProviderError, match="choices"):
        await provider.generate(chat_request)


# === 响应 choices 为空列表 ===


@respx.mock
@pytest.mark.asyncio
async def test_empty_choices(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(200, json={"choices": []})
    )
    with pytest.raises(OpenAICompatibleProviderError, match="choices"):
        await provider.generate(chat_request)


# === 连接失败 ===


@respx.mock
@pytest.mark.asyncio
async def test_connection_error(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    import httpx
    respx.post(f"{BASE_URL}/chat/completions").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(OpenAICompatibleProviderError, match="Connection failed"):
        await provider.generate(chat_request)


# === 超时 ===


@respx.mock
@pytest.mark.asyncio
async def test_timeout(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    import httpx
    respx.post(f"{BASE_URL}/chat/completions").mock(side_effect=httpx.ReadTimeout("timeout"))
    with pytest.raises(OpenAICompatibleProviderError, match="timed out"):
        await provider.generate(chat_request)


# === health_check ===


@respx.mock
@pytest.mark.asyncio
async def test_health_check_reachable(provider: OpenAICompatibleProvider) -> None:
    respx.get(f"{BASE_URL}/models").mock(
        return_value=Response(200, json={"data": []})
    )
    health = await provider.health_check()
    assert isinstance(health, ProviderHealth)
    assert health.reachable is True
    assert health.provider == "deepseek"


@respx.mock
@pytest.mark.asyncio
async def test_health_check_unreachable(provider: OpenAICompatibleProvider) -> None:
    import httpx
    respx.get(f"{BASE_URL}/models").mock(side_effect=httpx.ConnectError("down"))
    health = await provider.health_check()
    assert health.reachable is False
    assert health.error is not None


# === Authorization header 包含 Bearer token ===


@respx.mock
@pytest.mark.asyncio
async def test_auth_header_sent(provider: OpenAICompatibleProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "x"}}],
        })
    )
    await provider.generate(chat_request)
    auth_header = respx.calls[0].request.headers.get("authorization")
    assert auth_header == "Bearer sk-test-key"


# === list_models ===


@respx.mock
@pytest.mark.asyncio
async def test_list_models_success(provider: OpenAICompatibleProvider) -> None:
    respx.get(f"{BASE_URL}/models").mock(
        return_value=Response(200, json={
            "data": [
                {"id": "deepseek-chat", "owned_by": "deepseek", "created": 1700000000},
                {"id": "deepseek-coder", "owned_by": "deepseek"},
            ]
        })
    )
    models = await provider.list_models()
    assert len(models) == 2
    assert models[0].id == "deepseek-chat"
    assert models[0].owned_by == "deepseek"
    assert models[0].created == 1700000000
    assert models[1].id == "deepseek-coder"


@respx.mock
@pytest.mark.asyncio
async def test_list_models_empty(provider: OpenAICompatibleProvider) -> None:
    respx.get(f"{BASE_URL}/models").mock(
        return_value=Response(200, json={"data": []})
    )
    models = await provider.list_models()
    assert models == []


@respx.mock
@pytest.mark.asyncio
async def test_list_models_not_supported(provider: OpenAICompatibleProvider) -> None:
    """API 不支持 /models 时返回空列表，不崩溃。"""
    respx.get(f"{BASE_URL}/models").mock(
        return_value=Response(404, text="Not Found")
    )
    models = await provider.list_models()
    assert models == []


@respx.mock
@pytest.mark.asyncio
async def test_list_models_connection_error(provider: OpenAICompatibleProvider) -> None:
    import httpx
    respx.get(f"{BASE_URL}/models").mock(side_effect=httpx.ConnectError("refused"))
    models = await provider.list_models()
    assert models == []


@respx.mock
@pytest.mark.asyncio
async def test_list_models_no_data_key(provider: OpenAICompatibleProvider) -> None:
    respx.get(f"{BASE_URL}/models").mock(
        return_value=Response(200, json={"models": []})
    )
    models = await provider.list_models()
    assert models == []


# === API key 不出现在日志 ===


@respx.mock
@pytest.mark.asyncio
async def test_api_key_not_in_logs(provider: OpenAICompatibleProvider, chat_request: LLMRequest, caplog) -> None:
    """确保 API key 不出现在日志输出中。"""
    import logging
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        })
    )
    with caplog.at_level(logging.DEBUG):
        await provider.generate(chat_request)
    assert "sk-test-key" not in caplog.text
