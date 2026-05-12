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
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                assert registry.is_enabled("tavily") is True
                assert registry.is_configured("tavily") is False

    def test_missing_keys_listed(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                services = registry.list_services()
                tavily = next(s for s in services if s.name == "tavily")
                assert "TAVILY_API_KEY" in tavily.missing_keys
                # 向后兼容
                assert "TAVILY_API_KEY" in tavily.missing_env_vars


class TestBraveWithKey:
    def test_configured_true(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-xxx"}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                assert registry.is_configured("brave") is True
                assert registry.is_enabled("brave") is True

    def test_no_missing_keys(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-xxx"}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                services = registry.list_services()
                brave = next(s for s in services if s.name == "brave")
                assert brave.missing_keys == []
                assert brave.missing_env_vars == []

    def test_api_key_not_exposed(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-secret-123"}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                config = registry.get_provider_config("brave")
                # 不应包含原文 key
                assert "sk-secret-123" not in str(config)
                assert config.get("brave_api_key_configured") is True


class TestGoogleBooksPublicMode:
    def test_configured_without_key(self, registry: ServiceRegistry) -> None:
        runtime = {"search": {"google_books": {"public_mode": True}}}
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                assert registry.is_configured("google_books") is True

    def test_source_public_mode(self, registry: ServiceRegistry) -> None:
        runtime = {"search": {"google_books": {"public_mode": True, "enabled": True}}}
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                gb = next(s for s in services if s.name == "google_books")
                assert gb.configured is True
                assert gb.source == "public_mode"
                assert gb.message is not None
                assert "public mode" in gb.message


class TestOllamaNoBaseUrl:
    def test_not_configured_without_base_url(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                assert registry.is_configured("ollama_lan") is False

    def test_missing_keys(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                services = registry.list_services()
                ollama = next(s for s in services if s.name == "ollama_lan")
                assert "OLLAMA_BASE_URL" in ollama.missing_keys

    def test_configured_with_base_url_env(self, registry: ServiceRegistry) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.50:11434"}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                assert registry.is_configured("ollama_lan") is True


class TestListServices:
    def test_returns_all_services(self, registry: ServiceRegistry) -> None:
        with patch.object(registry, "_load_runtime_settings", return_value={}):
            services = registry.list_services()
            names = [s.name for s in services]
            assert "ollama_lan" in names
            assert "tavily" in names
            assert "brave" in names
            assert "google_books" in names
            assert "trafilatura" in names
            assert "obsidian" in names

    def test_all_are_service_status(self, registry: ServiceRegistry) -> None:
        with patch.object(registry, "_load_runtime_settings", return_value={}):
            services = registry.list_services()
            for s in services:
                assert isinstance(s, ServiceStatus)

    def test_types_correct(self, registry: ServiceRegistry) -> None:
        with patch.object(registry, "_load_runtime_settings", return_value={}):
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
    """测试 runtime_settings.json 优先级高于 .env。"""

    def test_ollama_configured_from_runtime(self, registry: ServiceRegistry) -> None:
        """runtime_settings 中有 ollama.base_url 时 configured=true, source=runtime。"""
        runtime = {"ollama": {"base_url": "http://192.168.1.50:11434", "default_model": "qwen3:8b"}}
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                ollama = next(s for s in services if s.name == "ollama_lan")
                assert ollama.configured is True
                assert ollama.missing_keys == []
                assert ollama.source == "runtime"

    def test_tavily_configured_from_runtime(self, registry: ServiceRegistry) -> None:
        """runtime_settings 中有 search.tavily.api_key 时 configured=true。"""
        runtime = {"search": {"tavily": {"api_key": "tvly-from-runtime", "enabled": True}}}
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                tavily = next(s for s in services if s.name == "tavily")
                assert tavily.configured is True
                assert tavily.api_key_configured is True
                assert tavily.source == "runtime"

    def test_brave_configured_from_runtime(self, registry: ServiceRegistry) -> None:
        """runtime_settings 中有 search.brave.api_key 时 configured=true。"""
        runtime = {"search": {"brave": {"api_key": "BSA-runtime", "enabled": True}}}
        with patch.dict(os.environ, {"BRAVE_API_KEY": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                brave = next(s for s in services if s.name == "brave")
                assert brave.configured is True
                assert brave.api_key_configured is True
                assert brave.source == "runtime"

    def test_google_books_public_mode_from_runtime(self, registry: ServiceRegistry) -> None:
        """google_books public_mode=true 时 configured=true, source=public_mode。"""
        runtime = {"search": {"google_books": {"enabled": True, "public_mode": True}}}
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                gb = next(s for s in services if s.name == "google_books")
                assert gb.configured is True
                assert gb.source == "public_mode"

    def test_obsidian_configured_from_runtime(self, registry: ServiceRegistry, tmp_path) -> None:
        """runtime_settings 中有 obsidian.vault_path 且路径可写时 configured=true。"""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        runtime = {"obsidian": {"vault_path": str(vault_dir)}}
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                obsidian = next(s for s in services if s.name == "obsidian")
                assert obsidian.configured is True
                assert obsidian.source == "runtime"

    def test_obsidian_not_writable(self, registry: ServiceRegistry, tmp_path) -> None:
        """obsidian vault_path 存在但不可写时 configured=false，显示路径不可写。"""
        vault_dir = tmp_path / "readonly_vault"
        vault_dir.mkdir()
        vault_dir.chmod(0o444)
        runtime = {"obsidian": {"vault_path": str(vault_dir)}}
        try:
            with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": ""}, clear=False):
                with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                    services = registry.list_services()
                    obsidian = next(s for s in services if s.name == "obsidian")
                    assert obsidian.configured is False
                    assert "不可写" in (obsidian.message or "")
        finally:
            vault_dir.chmod(0o755)

    def test_env_source_when_only_env_has_value(self, registry: ServiceRegistry) -> None:
        """env 中有值但 runtime 没有时 source=env。"""
        with patch.dict(os.environ, {"BRAVE_API_KEY": "BSA-from-env"}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value={}):
                services = registry.list_services()
                brave = next(s for s in services if s.name == "brave")
                assert brave.configured is True
                assert brave.source == "env"

    def test_runtime_priority_over_env(self, registry: ServiceRegistry) -> None:
        """runtime 优先级高于 env（runtime 有值时 source=runtime）。"""
        runtime = {"search": {"tavily": {"api_key": "tvly-runtime", "enabled": True}}}
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-env"}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                tavily = next(s for s in services if s.name == "tavily")
                assert tavily.configured is True
                # Both have values, but runtime takes priority in source reporting
                assert tavily.source == "runtime"

    def test_deepseek_configured_from_runtime(self, registry: ServiceRegistry) -> None:
        """runtime cloud_llm provider=deepseek 且有 api_key/base_url/default_model 时 configured=true。"""
        runtime = {
            "cloud_llm": {
                "enabled": True,
                "provider": "deepseek",
                "api_key": "sk-deep",
                "base_url": "https://api.deepseek.com/v1",
                "default_model": "deepseek-chat",
            }
        }
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_BASE_URL": "",
            "DEEPSEEK_DEFAULT_MODEL": "",
        }, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                services = registry.list_services()
                ds = next(s for s in services if s.name == "deepseek")
                assert ds.configured is True
                assert ds.source == "runtime"
                assert ds.api_key_configured is True

    def test_trafilatura_always_available(self, registry: ServiceRegistry) -> None:
        """trafilatura 本地 provider，始终 available=true（假设已安装）。"""
        with patch.object(registry, "_load_runtime_settings", return_value={}):
            services = registry.list_services()
            traf = next(s for s in services if s.name == "trafilatura")
            assert traf.configured is True
            assert traf.source == "local"
            assert "本地" in (traf.message or "")


class TestRuntimeSettingsConfigPriority:
    """测试 core.config 中 runtime_settings 优先级。"""

    def test_tavily_key_from_runtime_overrides_env(self) -> None:
        """runtime_settings.json 中的 API key 优先于 .env。"""
        from core.config import reset_settings, get_settings

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
        runtime = {"search": {"google_books": {"public_mode": True}}}
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            with patch.object(registry, "_load_runtime_settings", return_value=runtime):
                assert registry.is_configured("google_books") is True
