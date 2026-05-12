"""设置与健康检查 API。"""

import os
from pathlib import Path as FilePath
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel

from app.ai.router import LLMRouter
from app.core.service_registry import ServiceRegistry
from app.providers.llm.base import LLMRequest
from app.providers.llm.ollama import OllamaProvider, OllamaModelInfo
from app.providers.llm.openai_compatible import OpenAICompatibleProvider, CloudModelInfo
from core.config import get_settings, reset_settings, save_runtime_settings, _load_runtime_settings

router = APIRouter(prefix="/settings", tags=["settings"])

_registry = ServiceRegistry()
_llm_router = LLMRouter()


# === Request / Response schemas ===


class LLMTestRequest(BaseModel):
    provider: str = "ollama_lan"
    model: str = "qwen3:8b"


class LLMTestResponse(BaseModel):
    reachable: bool
    latency_ms: int | None = None
    error: str | None = None
    generate_ok: bool | None = None


class OllamaTestRequest(BaseModel):
    base_url: str


class OllamaTestResponse(BaseModel):
    reachable: bool
    latency_ms: int | None = None
    error: str | None = None


class OllamaModelsRequest(BaseModel):
    base_url: str


class OllamaModelsResponse(BaseModel):
    models: list[OllamaModelInfo]


class OllamaSaveRequest(BaseModel):
    base_url: str
    default_model: str = "qwen3:8b"
    timeout_seconds: int = 120


class OllamaSaveResponse(BaseModel):
    success: bool
    message: str


# --- Cloud LLM schemas ---


class CloudLLMTestRequest(BaseModel):
    provider: str
    base_url: str
    api_key: str
    model: str


class CloudLLMTestResponse(BaseModel):
    reachable: bool
    latency_ms: int | None = None
    error: str | None = None


class CloudLLMModelsRequest(BaseModel):
    provider: str
    base_url: str
    api_key: str


class CloudLLMModelsResponse(BaseModel):
    models: list[CloudModelInfo]
    note: str | None = None


class CloudLLMSaveRequest(BaseModel):
    enabled: bool = True
    provider: str
    base_url: str
    api_key: str
    default_model: str
    timeout_seconds: int = 120


class CloudLLMSaveResponse(BaseModel):
    success: bool
    message: str


class ActiveProviderRequest(BaseModel):
    provider: str


class ActiveProviderResponse(BaseModel):
    success: bool
    active_provider: str


# === Endpoints ===


@router.get("/services")
async def list_services() -> list[dict[str, Any]]:
    """返回所有服务配置状态。"""
    services = _registry.list_services()
    return [s.model_dump() for s in services]


@router.get("/llm")
async def get_llm_config() -> dict[str, Any]:
    """返回 LLM provider 配置状态。"""
    settings = get_settings()
    return {
        "provider": "ollama_lan",
        "enabled": settings.enable_llm,
        "configured": settings.ollama_configured,
        "default_model": settings.ollama_default_model,
        "base_url_host": _mask_url(settings.ollama_base_url),
        "timeout_seconds": settings.ollama_timeout_seconds,
        "active_provider": settings.active_llm_provider,
    }


# --- Ollama endpoints ---


@router.get("/llm/ollama")
async def get_ollama_config() -> dict[str, Any]:
    """返回 Ollama 详细配置。"""
    settings = get_settings()
    return {
        "enabled": settings.enable_llm,
        "configured": settings.ollama_configured,
        "base_url": settings.ollama_base_url,
        "host": _mask_url(settings.ollama_base_url),
        "default_model": settings.ollama_default_model,
        "timeout_seconds": settings.ollama_timeout_seconds,
    }


@router.post("/llm/ollama/test")
async def test_ollama_connection(body: OllamaTestRequest) -> OllamaTestResponse:
    """测试指定 Ollama 服务器是否可达。"""
    provider = OllamaProvider(base_url=body.base_url)
    health = await provider.health_check()
    return OllamaTestResponse(
        reachable=health.reachable,
        latency_ms=health.latency_ms,
        error=health.error,
    )


@router.post("/llm/ollama/models")
async def list_ollama_models(body: OllamaModelsRequest) -> OllamaModelsResponse:
    """查询指定 Ollama 服务器的已安装模型。"""
    provider = OllamaProvider(base_url=body.base_url)
    models = await provider.list_models()
    return OllamaModelsResponse(models=models)


@router.post("/llm/ollama/save")
async def save_ollama_config(body: OllamaSaveRequest) -> OllamaSaveResponse:
    """保存 Ollama 配置到 runtime_settings.json。"""
    try:
        save_runtime_settings("ollama", {
            "base_url": body.base_url,
            "default_model": body.default_model,
            "timeout_seconds": body.timeout_seconds,
        })
        reset_settings()
        return OllamaSaveResponse(success=True, message="配置已保存")
    except Exception as e:
        return OllamaSaveResponse(success=False, message=f"保存失败: {e}")


# --- Cloud LLM endpoints ---


@router.get("/llm/cloud")
async def get_cloud_llm_config() -> dict[str, Any]:
    """返回云端 LLM 配置（不返回 API key 明文）。"""
    settings = get_settings()
    provider = settings.cloud_llm_provider

    # 根据 provider 确定具体配置
    if provider == "deepseek":
        base_url = settings.deepseek_base_url
        default_model = settings.deepseek_default_model
        api_key_configured = bool(settings.deepseek_api_key)
    elif provider == "openai":
        base_url = settings.openai_base_url
        default_model = settings.openai_default_model
        api_key_configured = bool(settings.openai_api_key)
    elif provider == "openai_compatible":
        base_url = settings.openai_compatible_base_url
        default_model = settings.openai_compatible_default_model
        api_key_configured = bool(settings.openai_compatible_api_key)
    else:
        base_url = ""
        default_model = ""
        api_key_configured = False

    return {
        "enabled": settings.enable_cloud_llm,
        "provider": provider,
        "base_url": base_url,
        "default_model": default_model,
        "timeout_seconds": settings.cloud_llm_timeout_seconds,
        "api_key_configured": api_key_configured,
    }


@router.post("/llm/cloud/test")
async def test_cloud_llm(body: CloudLLMTestRequest) -> CloudLLMTestResponse:
    """测试云端 LLM 连通性（临时创建 provider）。"""
    provider = OpenAICompatibleProvider(
        name=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
        default_model=body.model,
        timeout_seconds=15,
    )
    health = await provider.health_check()
    return CloudLLMTestResponse(
        reachable=health.reachable,
        latency_ms=health.latency_ms,
        error=health.error,
    )


@router.post("/llm/cloud/models")
async def list_cloud_llm_models(body: CloudLLMModelsRequest) -> CloudLLMModelsResponse:
    """查询云端 LLM 可用模型列表。"""
    provider = OpenAICompatibleProvider(
        name=body.provider,
        base_url=body.base_url,
        api_key=body.api_key,
    )
    models = await provider.list_models()
    note = None
    if not models:
        note = "该 API 未返回模型列表，请手动填写模型名称"
    return CloudLLMModelsResponse(models=models, note=note)


@router.post("/llm/cloud/save")
async def save_cloud_llm_config(body: CloudLLMSaveRequest) -> CloudLLMSaveResponse:
    """保存云端 LLM 配置到 runtime_settings.json。"""
    try:
        save_runtime_settings("cloud_llm", {
            "enabled": body.enabled,
            "provider": body.provider,
            "base_url": body.base_url,
            "api_key": body.api_key,
            "default_model": body.default_model,
            "timeout_seconds": body.timeout_seconds,
        })
        reset_settings()
        return CloudLLMSaveResponse(success=True, message="云端 LLM 配置已保存")
    except Exception as e:
        return CloudLLMSaveResponse(success=False, message=f"保存失败: {e}")


@router.post("/llm/active-provider")
async def set_active_provider(body: ActiveProviderRequest) -> ActiveProviderResponse:
    """设置当前默认 LLM provider。"""
    valid_providers = {"ollama_lan", "deepseek", "openai", "openai_compatible"}
    if body.provider not in valid_providers:
        return ActiveProviderResponse(
            success=False,
            active_provider=get_settings().active_llm_provider,
        )
    try:
        save_runtime_settings("active_provider", body.provider)
        reset_settings()
        return ActiveProviderResponse(success=True, active_provider=body.provider)
    except Exception:
        return ActiveProviderResponse(
            success=False,
            active_provider=get_settings().active_llm_provider,
        )


# --- General LLM test ---


@router.post("/llm/test")
async def test_llm(body: LLMTestRequest) -> LLMTestResponse:
    """测试 LLM provider 连通性。"""
    try:
        provider = _llm_router.get_provider(body.provider)
    except Exception as e:
        return LLMTestResponse(reachable=False, error=str(e))

    # health_check
    health = await provider.health_check()
    if not health.reachable:
        return LLMTestResponse(
            reachable=False,
            latency_ms=health.latency_ms,
            error=health.error,
        )

    # 可选 generate 测试
    generate_ok: bool | None = None
    try:
        request = LLMRequest(
            model=body.model,
            user_prompt="ping",
            max_output_tokens=16,
            timeout_seconds=15,
        )
        response = await provider.generate(request)
        generate_ok = bool(response.text)
    except Exception:
        generate_ok = False

    return LLMTestResponse(
        reachable=True,
        latency_ms=health.latency_ms,
        error=None,
        generate_ok=generate_ok,
    )


# --- Search settings schemas ---


class SearchSaveProviderConfig(BaseModel):
    enabled: bool = True
    api_key: str | None = None


class SearchSaveGoogleBooksConfig(BaseModel):
    enabled: bool = True
    api_key: str | None = None
    public_mode: bool = True


class SearchSaveRequest(BaseModel):
    tavily: SearchSaveProviderConfig | None = None
    brave: SearchSaveProviderConfig | None = None
    google_books: SearchSaveGoogleBooksConfig | None = None


class SearchSaveResponse(BaseModel):
    success: bool
    message: str


# --- Obsidian schemas ---


class ObsidianSaveRequest(BaseModel):
    vault_path: str


class ObsidianSaveResponse(BaseModel):
    success: bool
    message: str


class ObsidianTestRequest(BaseModel):
    vault_path: str


class ObsidianTestResponse(BaseModel):
    exists: bool
    writable: bool
    error: str | None = None


# === Search endpoints ===


@router.get("/search")
async def get_search_config() -> dict[str, Any]:
    """返回搜索 provider 配置状态（不返回 API key 明文）。"""
    settings = get_settings()
    return {
        "tavily": {
            "enabled": settings.enable_tavily,
            "configured": _registry.is_configured("tavily"),
            "api_key_configured": bool(settings.tavily_api_key),
        },
        "brave": {
            "enabled": settings.enable_brave,
            "configured": _registry.is_configured("brave"),
            "api_key_configured": bool(settings.brave_api_key),
        },
        "google_books": {
            "enabled": settings.enable_google_books,
            "configured": _registry.is_configured("google_books"),
            "api_key_configured": bool(settings.google_books_api_key),
            "mode": "authenticated" if settings.google_books_api_key else "public",
        },
    }


@router.post("/search/save")
async def save_search_config(body: SearchSaveRequest) -> SearchSaveResponse:
    """保存搜索 provider 配置到 runtime_settings.json。"""
    try:
        runtime = _load_runtime_settings()
        current_search = runtime.get("search", {})

        if body.tavily is not None:
            tavily_data = current_search.get("tavily", {})
            tavily_data["enabled"] = body.tavily.enabled
            if body.tavily.api_key == "__CLEAR__":
                tavily_data["api_key"] = ""
            elif body.tavily.api_key:
                tavily_data["api_key"] = body.tavily.api_key
            current_search["tavily"] = tavily_data

        if body.brave is not None:
            brave_data = current_search.get("brave", {})
            brave_data["enabled"] = body.brave.enabled
            if body.brave.api_key == "__CLEAR__":
                brave_data["api_key"] = ""
            elif body.brave.api_key:
                brave_data["api_key"] = body.brave.api_key
            current_search["brave"] = brave_data

        if body.google_books is not None:
            gb_data = current_search.get("google_books", {})
            gb_data["enabled"] = body.google_books.enabled
            gb_data["public_mode"] = body.google_books.public_mode
            if body.google_books.api_key == "__CLEAR__":
                gb_data["api_key"] = ""
            elif body.google_books.api_key:
                gb_data["api_key"] = body.google_books.api_key
            current_search["google_books"] = gb_data

        save_runtime_settings("search", current_search)
        reset_settings()
        return SearchSaveResponse(success=True, message="搜索配置已保存")
    except Exception as e:
        return SearchSaveResponse(success=False, message=f"保存失败: {e}")


# === Obsidian endpoints ===


@router.get("/obsidian")
async def get_obsidian_config() -> dict[str, Any]:
    """返回 Obsidian Vault 配置状态。"""
    settings = get_settings()
    vault_path = settings.obsidian_vault_path
    configured = bool(vault_path)
    exists = False
    writable = False

    if configured:
        p = FilePath(vault_path).expanduser().resolve()
        exists = p.exists() and p.is_dir()
        writable = exists and os.access(p, os.W_OK)

    return {
        "vault_path": vault_path,
        "configured": configured,
        "exists": exists,
        "writable": writable,
    }


@router.post("/obsidian/test")
async def test_obsidian_path(body: ObsidianTestRequest) -> ObsidianTestResponse:
    """测试 Obsidian Vault 路径是否有效。"""
    try:
        p = FilePath(body.vault_path).expanduser().resolve()
        exists = p.exists() and p.is_dir()
        writable = exists and os.access(p, os.W_OK)

        error = None
        if not exists:
            error = f"路径不存在: {p}"
        elif not writable:
            error = f"路径不可写: {p}"

        return ObsidianTestResponse(exists=exists, writable=writable, error=error)
    except Exception as e:
        return ObsidianTestResponse(exists=False, writable=False, error=str(e))


@router.post("/obsidian/save")
async def save_obsidian_config(body: ObsidianSaveRequest) -> ObsidianSaveResponse:
    """保存 Obsidian Vault 路径到 runtime_settings.json。"""
    try:
        p = FilePath(body.vault_path).expanduser().resolve()
        if not p.exists():
            return ObsidianSaveResponse(success=False, message=f"路径不存在: {p}")
        if not p.is_dir():
            return ObsidianSaveResponse(success=False, message=f"路径不是目录: {p}")
        if not os.access(p, os.W_OK):
            return ObsidianSaveResponse(success=False, message=f"路径不可写: {p}")

        save_runtime_settings("obsidian", {"vault_path": str(p)})
        reset_settings()
        return ObsidianSaveResponse(success=True, message="Vault 路径已保存")
    except Exception as e:
        return ObsidianSaveResponse(success=False, message=f"保存失败: {e}")


# === Helpers ===


def _mask_url(url: str) -> str:
    """只返回 host:port，隐藏路径和凭据。"""
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{host}{port}"
