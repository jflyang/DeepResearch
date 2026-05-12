"""LLM Router 云端 Provider 测试。"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.ai.router import (
    LLMProviderConfigError,
    LLMProviderDisabled,
    LLMProviderNotFound,
    LLMRouter,
)
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.ollama import OllamaProvider
from app.providers.llm.openai_compatible import OpenAICompatibleProvider
from core.config import reset_settings

CONFIG_PATH = Path("config/providers.yaml")


@pytest.fixture(autouse=True)
def _reset():
    reset_settings()
    yield
    reset_settings()


@pytest.fixture(autouse=True)
def _no_runtime_settings():
    """隔离测试：不读取真实 runtime_settings.json。"""
    with patch("core.config._load_runtime_settings", return_value={}):
        reset_settings()
        yield
        reset_settings()


# === 创建 deepseek provider ===


class TestDeepSeekProvider:
    def test_creates_deepseek_provider(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_DEFAULT_MODEL": "deepseek-chat",
            "CLOUD_LLM_TIMEOUT_SECONDS": "60",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("deepseek")
            assert isinstance(provider, OpenAICompatibleProvider)
            assert provider.provider_name == "deepseek"
            assert provider._default_model == "deepseek-chat"
            assert provider._base_url == "https://api.deepseek.com/v1"

    def test_deepseek_uses_correct_api_key(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "DEEPSEEK_API_KEY": "sk-my-secret",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_DEFAULT_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("deepseek")
            assert provider._api_key == "sk-my-secret"


# === 创建 openai provider ===


class TestOpenAIProvider:
    def test_creates_openai_provider(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "OPENAI_API_KEY": "sk-openai-test",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_DEFAULT_MODEL": "gpt-4.1-mini",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("openai")
            assert isinstance(provider, OpenAICompatibleProvider)
            assert provider.provider_name == "openai"
            assert provider._default_model == "gpt-4.1-mini"
            assert provider._base_url == "https://api.openai.com/v1"
            assert provider._api_key == "sk-openai-test"

    def test_openai_missing_key_raises(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "OPENAI_API_KEY": "",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_DEFAULT_MODEL": "gpt-4",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            with pytest.raises(LLMProviderConfigError) as exc_info:
                router.get_provider("openai")
            assert "api_key" in exc_info.value.missing


# === provider disabled ===


class TestProviderDisabled:
    def test_cloud_disabled_by_env(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "false",
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_DEFAULT_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            with pytest.raises(LLMProviderDisabled) as exc_info:
                router.get_provider("deepseek")
            assert exc_info.value.name == "deepseek"

    def test_openai_disabled_when_cloud_off(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "false",
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_DEFAULT_MODEL": "gpt-4",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            with pytest.raises(LLMProviderDisabled):
                router.get_provider("openai")

    def test_cloud_enabled_by_default_when_env_not_set(self) -> None:
        """enabled_env 未设置时默认 enabled。"""
        env = {
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_DEFAULT_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ENABLE_CLOUD_LLM", None)
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("deepseek")
            assert isinstance(provider, OpenAICompatibleProvider)


# === 缺少配置 ===


class TestMissingConfig:
    def test_missing_api_key_raises(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_DEFAULT_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            with pytest.raises(LLMProviderConfigError) as exc_info:
                router.get_provider("deepseek")
            assert "api_key" in exc_info.value.missing

    def test_missing_base_url_raises(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "",
            "DEEPSEEK_DEFAULT_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            with pytest.raises(LLMProviderConfigError) as exc_info:
                router.get_provider("deepseek")
            assert "base_url" in exc_info.value.missing

    def test_missing_model_raises(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_DEFAULT_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            with pytest.raises(LLMProviderConfigError) as exc_info:
                router.get_provider("deepseek")
            assert "default_model" in exc_info.value.missing


# === 不影响 ollama_lan ===


class TestOllamaUnaffected:
    def test_ollama_still_works(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.50:11434"}, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("ollama_lan")
            assert isinstance(provider, OllamaProvider)
            assert provider._base_url == "http://192.168.1.50:11434"

    def test_mock_still_works(self) -> None:
        router = LLMRouter(config_path=CONFIG_PATH)
        provider = router.get_provider("mock_llm")
        assert isinstance(provider, MockLLMProvider)


# === task 配置 provider 路由正确 ===


class TestTaskRouting:
    def test_router_resolves_deepseek_by_name(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_DEFAULT_MODEL": "deepseek-chat",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("deepseek")
            assert isinstance(provider, OpenAICompatibleProvider)
            assert provider.provider_name == "deepseek"

    def test_router_resolves_openai_by_name(self) -> None:
        env = {
            "ENABLE_CLOUD_LLM": "true",
            "OPENAI_API_KEY": "sk-openai",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_DEFAULT_MODEL": "gpt-4.1-mini",
        }
        with patch.dict(os.environ, env, clear=False):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("openai")
            assert isinstance(provider, OpenAICompatibleProvider)
            assert provider.provider_name == "openai"


# === available_providers ===


class TestAvailableProviders:
    def test_lists_all_configured(self) -> None:
        router = LLMRouter(config_path=CONFIG_PATH)
        available = router.available_providers
        assert "ollama_lan" in available
        assert "deepseek" in available
        assert "openai" in available
        assert "openai_compatible" in available
        assert "mock_llm" in available
