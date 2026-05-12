"""测试 ServiceRegistry 的 severity 逻辑。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.service_registry import ServiceRegistry, ServiceStatus


@pytest.fixture
def registry():
    """使用项目默认 providers.yaml 创建 registry。"""
    return ServiceRegistry()


def _mock_runtime(data: dict):
    """创建 mock runtime settings。"""
    return patch("app.core.service_registry._load_runtime_settings",
                 lambda: data if not hasattr(data, '__self__') else data)


class TestLLMProviderSeverity:
    """LLM Provider severity 逻辑测试。"""

    def test_deepseek_active_configured_is_ok(self, registry):
        """deepseek active+configured → severity=ok, active=true。"""
        runtime = {
            "active_provider": "deepseek",
            "cloud_llm": {"enabled": True, "provider": "deepseek", "api_key": "sk-test", "base_url": "https://api.deepseek.com", "default_model": "deepseek-chat"},
            "llm": {"providers": {"deepseek": {"enabled": True}}},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            status = registry._get_status("deepseek")
        assert status.severity == "ok"
        assert status.active is True

    def test_openai_inactive_is_not_error(self, registry):
        """openai inactive → severity=inactive，不是 error。"""
        runtime = {
            "active_provider": "deepseek",
            "cloud_llm": {"enabled": True, "provider": "deepseek", "api_key": "sk-test", "base_url": "https://api.deepseek.com", "default_model": "deepseek-chat"},
            "llm": {"providers": {"openai": {"enabled": False}}},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            status = registry._get_status("openai")
        assert status.severity == "inactive"
        assert status.active is False
        assert "error" not in (status.message or "").lower()

    def test_ollama_disabled_missing_url_is_inactive(self, registry):
        """ollama disabled + missing base_url → severity=inactive。"""
        runtime = {
            "active_provider": "deepseek",
            "llm": {"providers": {"ollama_lan": {"enabled": False}}},
            "cloud_llm": {},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            with patch("app.core.service_registry.env_has_value", return_value=False):
                status = registry._get_status("ollama_lan")
        assert status.severity == "inactive"

    def test_ollama_enabled_missing_url_is_warning(self, registry):
        """ollama enabled + missing base_url → severity=warning。"""
        runtime = {
            "active_provider": "ollama_lan",
            "llm": {"providers": {"ollama_lan": {"enabled": True}}},
            "cloud_llm": {},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            with patch("app.core.service_registry.env_has_value", return_value=False):
                status = registry._get_status("ollama_lan")
        assert status.severity == "warning"


class TestSearchProviderSeverity:
    """Search Provider severity 逻辑测试。"""

    def test_brave_disabled_missing_key_is_inactive(self, registry):
        """brave disabled + missing key → severity=inactive。"""
        runtime = {
            "active_provider": "deepseek",
            "search_policy": {"providers": {"brave": {"enabled": False}}},
            "cloud_llm": {},
            "llm": {},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            with patch("app.core.service_registry.env_has_value", return_value=False):
                status = registry._get_status("brave")
        assert status.severity == "inactive"

    def test_brave_enabled_missing_key_is_warning(self, registry):
        """brave enabled + missing key → severity=warning。"""
        runtime = {
            "active_provider": "deepseek",
            "search_policy": {"providers": {"brave": {"enabled": True}}},
            "cloud_llm": {},
            "llm": {},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            with patch("app.core.service_registry.env_has_value", return_value=False):
                status = registry._get_status("brave")
        assert status.severity == "warning"

    def test_searxng_disabled_missing_url_is_inactive(self, registry):
        """searxng disabled + missing base_url → inactive。"""
        runtime = {
            "active_provider": "deepseek",
            "search_policy": {"providers": {"searxng": {"enabled": False}}},
            "cloud_llm": {},
            "llm": {},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            with patch("app.core.service_registry.env_has_value", return_value=False):
                status = registry._get_status("searxng")
        assert status.severity == "inactive"

    def test_searxng_enabled_missing_url_is_warning(self, registry):
        """searxng enabled + missing base_url → warning。"""
        runtime = {
            "active_provider": "deepseek",
            "search_policy": {"providers": {"searxng": {"enabled": True}}},
            "cloud_llm": {},
            "llm": {},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            with patch("app.core.service_registry.env_has_value", return_value=False):
                status = registry._get_status("searxng")
        assert status.severity == "warning"

    def test_google_books_public_mode_is_ok(self, registry):
        """google_books public mode → ok。"""
        runtime = {
            "active_provider": "deepseek",
            "search": {"google_books": {"public_mode": True}},
            "search_policy": {"providers": {"google_books": {"enabled": True, "public_mode": True}}},
            "cloud_llm": {},
            "llm": {},
        }
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            status = registry._get_status("google_books")
        assert status.severity == "ok"

    def test_runtime_overrides_env(self, registry):
        """runtime 优先于 env。"""
        runtime = {
            "active_provider": "deepseek",
            "search_policy": {"providers": {"brave": {"enabled": False}}},
            "cloud_llm": {},
            "llm": {},
        }
        # Even if env has BRAVE_API_KEY, policy disables it → inactive
        with patch.object(registry, "_load_runtime_settings", return_value=runtime):
            with patch("app.core.service_registry.env_has_value", return_value=True):
                status = registry._get_status("brave")
        assert status.severity == "inactive"
