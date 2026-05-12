"""OllamaProvider 单元测试 - 使用 respx mock，不访问真实网络。"""

import pytest
import respx
from httpx import Response

from app.providers.llm.base import LLMRequest, ProviderHealth
from app.providers.llm.ollama import OllamaProvider, OllamaProviderError

BASE_URL = "http://192.168.1.50:11434"


@pytest.fixture
def provider() -> OllamaProvider:
    return OllamaProvider(base_url=BASE_URL)


@pytest.fixture
def chat_request() -> LLMRequest:
    return LLMRequest(
        model="qwen2.5:7b",
        system_prompt="You are helpful.",
        user_prompt="Hello",
        temperature=0.5,
        max_output_tokens=1024,
        timeout_seconds=30,
    )


# --- generate 成功 ---


@respx.mock
@pytest.mark.asyncio
async def test_generate_success(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=Response(200, json={
            "message": {"role": "assistant", "content": "Hi there!"},
            "done": True,
        })
    )
    resp = await provider.generate(chat_request)
    assert resp.text == "Hi there!"
    assert resp.provider == "ollama"
    assert resp.model == "qwen2.5:7b"
    assert resp.output_chars == len("Hi there!")
    assert resp.input_chars == len("You are helpful.") + len("Hello")


@respx.mock
@pytest.mark.asyncio
async def test_generate_no_system_prompt(provider: OllamaProvider) -> None:
    request = LLMRequest(model="m", user_prompt="just user")
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=Response(200, json={
            "message": {"role": "assistant", "content": "ok"},
        })
    )
    resp = await provider.generate(request)
    assert resp.text == "ok"
    assert resp.input_chars == len("just user")

    # 验证请求体中没有 system message
    call = respx.calls[0]
    import json
    body = json.loads(call.request.content)
    roles = [m["role"] for m in body["messages"]]
    assert "system" not in roles


@respx.mock
@pytest.mark.asyncio
async def test_generate_with_system_prompt(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=Response(200, json={
            "message": {"role": "assistant", "content": "reply"},
        })
    )
    await provider.generate(chat_request)

    import json
    body = json.loads(respx.calls[0].request.content)
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user"]


@respx.mock
@pytest.mark.asyncio
async def test_generate_sends_correct_options(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=Response(200, json={
            "message": {"role": "assistant", "content": "x"},
        })
    )
    await provider.generate(chat_request)

    import json
    body = json.loads(respx.calls[0].request.content)
    assert body["model"] == "qwen2.5:7b"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.5
    assert body["options"]["num_predict"] == 1024


# --- generate 错误场景 ---


@respx.mock
@pytest.mark.asyncio
async def test_generate_connection_error(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    import httpx
    respx.post(f"{BASE_URL}/api/chat").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(OllamaProviderError, match="Connection failed"):
        await provider.generate(chat_request)


@respx.mock
@pytest.mark.asyncio
async def test_generate_timeout(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    import httpx
    respx.post(f"{BASE_URL}/api/chat").mock(side_effect=httpx.ReadTimeout("timeout"))
    with pytest.raises(OllamaProviderError, match="timed out"):
        await provider.generate(chat_request)


@respx.mock
@pytest.mark.asyncio
async def test_generate_non_2xx(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(return_value=Response(500, text="error"))
    with pytest.raises(OllamaProviderError, match="Non-2xx"):
        await provider.generate(chat_request)


@respx.mock
@pytest.mark.asyncio
async def test_generate_invalid_json(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=Response(200, content=b"not json", headers={"content-type": "text/plain"})
    )
    with pytest.raises(OllamaProviderError, match="parse JSON"):
        await provider.generate(chat_request)


@respx.mock
@pytest.mark.asyncio
async def test_generate_missing_content_field(provider: OllamaProvider, chat_request: LLMRequest) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=Response(200, json={"done": True})
    )
    with pytest.raises(OllamaProviderError, match="missing"):
        await provider.generate(chat_request)


# --- health_check ---


@respx.mock
@pytest.mark.asyncio
async def test_health_check_reachable(provider: OllamaProvider) -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=Response(200, json={"models": []})
    )
    health = await provider.health_check()
    assert isinstance(health, ProviderHealth)
    assert health.reachable is True
    assert health.error is None


@respx.mock
@pytest.mark.asyncio
async def test_health_check_unreachable(provider: OllamaProvider) -> None:
    import httpx
    respx.get(f"{BASE_URL}/api/tags").mock(side_effect=httpx.ConnectError("down"))
    health = await provider.health_check()
    assert health.reachable is False
    assert health.error is not None


@respx.mock
@pytest.mark.asyncio
async def test_health_check_non_200(provider: OllamaProvider) -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(return_value=Response(503))
    health = await provider.health_check()
    assert health.reachable is False
    assert "503" in (health.error or "")


# --- list_models ---


@respx.mock
@pytest.mark.asyncio
async def test_list_models_success(provider: OllamaProvider) -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=Response(200, json={
            "models": [
                {
                    "name": "qwen3:8b",
                    "modified_at": "2026-05-01T10:00:00Z",
                    "size": 4_500_000_000,
                    "digest": "abc123",
                },
                {
                    "name": "llama3:8b",
                    "modified_at": "2026-04-20T08:00:00Z",
                    "size": 4_200_000_000,
                },
            ]
        })
    )
    models = await provider.list_models()
    assert len(models) == 2
    assert models[0].name == "qwen3:8b"
    assert models[0].size == 4_500_000_000
    assert models[0].modified_at == "2026-05-01T10:00:00Z"
    assert models[0].digest == "abc123"
    assert models[1].name == "llama3:8b"
    assert models[1].digest is None


@respx.mock
@pytest.mark.asyncio
async def test_list_models_empty(provider: OllamaProvider) -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=Response(200, json={"models": []})
    )
    models = await provider.list_models()
    assert models == []


@respx.mock
@pytest.mark.asyncio
async def test_list_models_connection_error(provider: OllamaProvider) -> None:
    import httpx
    respx.get(f"{BASE_URL}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    models = await provider.list_models()
    assert models == []


@respx.mock
@pytest.mark.asyncio
async def test_list_models_no_models_key(provider: OllamaProvider) -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=Response(200, json={"something_else": []})
    )
    models = await provider.list_models()
    assert models == []


@respx.mock
@pytest.mark.asyncio
async def test_list_models_parses_name_size_modified(provider: OllamaProvider) -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=Response(200, json={
            "models": [
                {
                    "name": "deepseek-r1:7b",
                    "modified_at": "2026-03-15T12:00:00Z",
                    "size": 3_800_000_000,
                    "digest": "def456",
                },
            ]
        })
    )
    models = await provider.list_models()
    assert len(models) == 1
    m = models[0]
    assert m.name == "deepseek-r1:7b"
    assert m.size == 3_800_000_000
    assert m.modified_at == "2026-03-15T12:00:00Z"
    assert m.digest == "def456"
