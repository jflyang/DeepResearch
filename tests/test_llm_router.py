"""LLMRouter 单元测试。"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.ai.router import LLMProviderDisabled, LLMProviderNotFound, LLMRouter
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.ollama import OllamaProvider
from core.config import reset_settings

CONFIG_PATH = Path("config/providers.yaml")


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_settings()
    yield  # type: ignore[misc]
    reset_settings()


class TestGetMockProvider:
    def test_returns_mock_provider(self) -> None:
        router = LLMRouter(config_path=CONFIG_PATH)
        provider = router.get_provider("mock_llm")
        assert isinstance(provider, MockLLMProvider)
        assert provider.provider_name == "mock"

    def test_mock_available_when_llm_disabled(self) -> None:
        with patch.dict(os.environ, {"ENABLE_LLM": "false"}):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("mock_llm")
            assert isinstance(provider, MockLLMProvider)


class TestProviderDisabled:
    def test_ollama_disabled_when_enable_llm_false(self) -> None:
        with patch.dict(os.environ, {"ENABLE_LLM": "false"}):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            with pytest.raises(LLMProviderDisabled) as exc_info:
                router.get_provider("ollama_lan")
            assert exc_info.value.name == "ollama_lan"

    def test_disabled_in_yaml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "providers.yaml"
        cfg.write_text(
            "llm_providers:\n"
            "  my_provider:\n"
            "    type: ollama\n"
            "    enabled: false\n",
            encoding="utf-8",
        )
        router = LLMRouter(config_path=cfg)
        with pytest.raises(LLMProviderDisabled):
            router.get_provider("my_provider")


class TestProviderNotFound:
    def test_missing_provider(self) -> None:
        router = LLMRouter(config_path=CONFIG_PATH)
        with pytest.raises(LLMProviderNotFound) as exc_info:
            router.get_provider("nonexistent")
        assert exc_info.value.name == "nonexistent"


class TestOllamaProviderInit:
    def test_base_url_from_settings(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.50:11434"}):
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("ollama_lan")
            assert isinstance(provider, OllamaProvider)
            assert provider._base_url == "http://192.168.1.50:11434"

    def test_default_base_url(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            # 确保没有覆盖
            os.environ.pop("OLLAMA_BASE_URL", None)
            reset_settings()
            router = LLMRouter(config_path=CONFIG_PATH)
            provider = router.get_provider("ollama_lan")
            assert isinstance(provider, OllamaProvider)
            assert "localhost" in provider._base_url or "11434" in provider._base_url


class TestAvailableProviders:
    def test_lists_configured_providers(self) -> None:
        router = LLMRouter(config_path=CONFIG_PATH)
        available = router.available_providers
        assert "ollama_lan" in available
        assert "mock_llm" in available
