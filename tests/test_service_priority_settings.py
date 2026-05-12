"""测试服务优先级配置的保存和读取。"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_runtime_settings(tmp_path):
    """创建临时 runtime_settings.json。"""
    settings_path = tmp_path / "config" / "runtime_settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{}", encoding="utf-8")
    return settings_path


@pytest.fixture
def mock_runtime_path(tmp_runtime_settings):
    """Mock _RUNTIME_SETTINGS_PATH 到临时文件。"""
    with patch("core.config._RUNTIME_SETTINGS_PATH", tmp_runtime_settings):
        yield tmp_runtime_settings


def test_save_active_provider_deepseek(mock_runtime_path):
    """保存 active_provider=deepseek 后 runtime_settings.json 中 llm.active_provider=deepseek。"""
    from core.config import save_runtime_settings, _load_runtime_settings

    save_runtime_settings("active_provider", "deepseek")
    save_runtime_settings("llm", {
        "active_provider": "deepseek",
        "provider_priority": ["deepseek", "ollama_lan"],
        "providers": {"deepseek": {"enabled": True}, "ollama_lan": {"enabled": False}},
    })

    data = _load_runtime_settings()
    assert data["active_provider"] == "deepseek"
    assert data["llm"]["active_provider"] == "deepseek"


def test_invalid_active_provider_rejected():
    """active_provider 非法时 API 应报错。"""
    from app.api.routes_settings import _VALID_LLM_PROVIDERS

    assert "invalid_provider" not in _VALID_LLM_PROVIDERS
    assert "deepseek" in _VALID_LLM_PROVIDERS
    assert "mock_llm" in _VALID_LLM_PROVIDERS


def test_search_provider_priority_roundtrip(mock_runtime_path):
    """search provider priority 保存后可读回。"""
    from core.config import save_runtime_settings, _load_runtime_settings

    sp_data = {
        "mode": "free_first",
        "paid_providers_enabled": False,
        "provider_priority": {
            "web": ["wikipedia", "searxng"],
            "book": ["google_books", "open_library"],
        },
        "providers": {
            "tavily": {"enabled": True, "mode": "fallback"},
            "brave": {"enabled": False},
        },
    }
    save_runtime_settings("search_policy", sp_data)

    data = _load_runtime_settings()
    assert data["search_policy"]["mode"] == "free_first"
    assert data["search_policy"]["provider_priority"]["web"] == ["wikipedia", "searxng"]
    assert data["search_policy"]["providers"]["tavily"]["mode"] == "fallback"


def test_tavily_mode_fallback_saved(mock_runtime_path):
    """Tavily mode=fallback 可保存。"""
    from core.config import save_runtime_settings, _load_runtime_settings

    save_runtime_settings("search_policy", {
        "mode": "free_first",
        "paid_providers_enabled": False,
        "provider_priority": {},
        "providers": {"tavily": {"enabled": True, "mode": "fallback"}},
    })

    data = _load_runtime_settings()
    assert data["search_policy"]["providers"]["tavily"]["mode"] == "fallback"


def test_save_does_not_overwrite_other_sections(mock_runtime_path):
    """保存 service priority 时不覆盖 runtime_settings 其他 section。"""
    from core.config import save_runtime_settings, _load_runtime_settings

    # Pre-existing data
    save_runtime_settings("obsidian", {"vault_path": "/test/vault"})
    save_runtime_settings("cloud_llm", {"provider": "deepseek", "api_key": "sk-test"})

    # Save llm priority
    save_runtime_settings("llm", {"active_provider": "deepseek", "providers": {}})

    data = _load_runtime_settings()
    assert data["obsidian"]["vault_path"] == "/test/vault"
    assert data["cloud_llm"]["api_key"] == "sk-test"
    assert data["llm"]["active_provider"] == "deepseek"
