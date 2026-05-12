"""ServiceRegistry 单元测试。"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.service_registry import ServiceRegistry, ServiceStatus

CONFIG_PATH = Path("config/providers.yaml")


@pytest.fixture
def registry() -> ServiceRegistry:
    return ServiceRegistry(config_path=CONFIG_PATH)


class TestTavilyMissingKey:
    def test_enabled_but_not_configured(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            assert registry.is_enabled("tavily") is True
            assert registry.is_configured("tavily") is False

    def test_missing_env_vars_listed(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            services = registry.list_services()
            tavily = next(s for s in services if s.name == "tavily")
            assert "TAVILY_API_KEY" in tavily.missing_env_vars


class TestBraveWithKey:
    def test_configured_true(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-xxx"}, clear=False):
            assert registry.is_configured("brave") is True
            assert registry.is_enabled("brave") is True

    def test_no_missing_env_vars(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-xxx"}, clear=False):
            services = registry.list_services()
            brave = next(s for s in services if s.name == "brave")
            assert brave.missing_env_vars == []

    def test_api_key_not_exposed(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-secret-123"}, clear=False):
            config = registry.get_provider_config("brave")
            # 不应包含原文 key
            assert "sk-secret-123" not in str(config)
            assert config.get("brave_api_key_configured") is True


class TestGoogleBooksPublicMode:
    def test_configured_without_key(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            assert registry.is_configured("google_books") is True

    def test_note_public_mode(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            services = registry.list_services()
            gb = next(s for s in services if s.name == "google_books")
            assert gb.note is not None
            assert "public mode" in gb.note


class TestOllamaNoBaseUrl:
    def test_not_configured_without_base_url(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": ""}, clear=False):
            assert registry.is_configured("ollama_lan") is False

    def test_missing_env_vars(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": ""}, clear=False):
            services = registry.list_services()
            ollama = next(s for s in services if s.name == "ollama_lan")
            assert "OLLAMA_BASE_URL" in ollama.missing_env_vars

    def test_configured_with_base_url(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.50:11434"}, clear=False):
            assert registry.is_configured("ollama_lan") is True


class TestListServices:
    def test_returns_all_services(self, registry: ServiceRegistry) -> None:
        services = registry.list_services()
        names = [s.name for s in services]
        assert "ollama_lan" in names
        assert "tavily" in names
        assert "brave" in names
        assert "google_books" in names
        assert "trafilatura" in names
        assert "obsidian" in names

    def test_all_are_service_status(self, registry: ServiceRegistry) -> None:
        services = registry.list_services()
        for s in services:
            assert isinstance(s, ServiceStatus)

    def test_types_correct(self, registry: ServiceRegistry) -> None:
        services = registry.list_services()
        type_map = {s.name: s.type for s in services}
        assert type_map["ollama_lan"] == "llm"
        assert type_map["tavily"] == "search"
        assert type_map["brave"] == "search"
        assert type_map["google_books"] == "search"
        assert type_map["trafilatura"] == "extraction"
        assert type_map["obsidian"] == "export"


class TestIsEnabled:
    def test_disabled_via_env(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"ENABLE_TAVILY": "false"}, clear=False):
            assert registry.is_enabled("tavily") is False

    def test_unknown_service(self, registry: ServiceRegistry) -> None:
        assert registry.is_enabled("nonexistent") is False


# === Runtime settings priority ===


class TestRuntimeSettingsPriority:
    def test_tavily_key_from_runtime_overrides_env(self) -> None:
        """runtime_settings.json 中的 API key 优先于 .env。"""
        from core.config import reset_settings, get_settings, _RUNTIME_SETTINGS_PATH
        import json

        runtime_data = {"search": {"tavily": {"api_key": "tvly-from-runtime", "enabled": True}}}
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-from-env"}, clear=False):
            with patch("core.config._load_runtime_settings", return_value=runtime_data):
                reset_settings()
                settings = get_settings()
                assert settings.tavily_api_key == "tvly-from-runtime"
                reset_settings()

    def test_brave_configured_from_runtime(self) -> None:
        """runtime_settings 中有 brave key 时 configured=True。"""
        from core.config import reset_settings, get_settings

        runtime_data = {"search": {"brave": {"api_key": "BSA-runtime", "enabled": True}}}
        with patch.dict(os.environ, {"BRAVE_API_KEY": ""}, clear=False):
            with patch("core.config._load_runtime_settings", return_value=runtime_data):
                reset_settings()
                settings = get_settings()
                assert settings.brave_available is True
                reset_settings()

    def test_obsidian_path_from_runtime(self) -> None:
        """runtime_settings 中的 vault_path 优先于 .env。"""
        from core.config import reset_settings, get_settings

        runtime_data = {"obsidian": {"vault_path": "/tmp/runtime-vault"}}
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": "/tmp/env-vault"}, clear=False):
            with patch("core.config._load_runtime_settings", return_value=runtime_data):
                reset_settings()
                settings = get_settings()
                assert settings.obsidian_vault_path == "/tmp/runtime-vault"
                reset_settings()

    def test_google_books_public_mode_configured(self, registry: ServiceRegistry) -> None:
        """Google Books public_mode=true 时 configured=true。"""
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            assert registry.is_configured("google_books") is True
