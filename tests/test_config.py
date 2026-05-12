"""配置层测试。"""

import os
from unittest.mock import patch

import pytest

from core.config import Settings, reset_settings


class TestSettingsDefaults:
    def test_default_values(self):
        s = Settings(
            _env_file=None,  # 不读取 .env 文件
        )
        assert s.app_env == "development"
        assert s.database_url == "sqlite:///./data/research.db"
        assert s.ollama_model == "qwen2.5:7b"
        assert s.default_search_depth == 3
        assert s.default_result_limit == 10
        assert s.scoring_authority_weight == 0.3
        assert s.scoring_relevance_weight == 0.4

    def test_obsidian_not_configured_by_default(self):
        s = Settings(_env_file=None)
        assert s.obsidian_configured is False
        assert s.obsidian_path.as_posix() == "."

    def test_obsidian_configured_when_set(self):
        s = Settings(_env_file=None, obsidian_vault_path="/Users/me/vault")
        assert s.obsidian_configured is True
        assert s.obsidian_path.as_posix() == "/Users/me/vault"


class TestProviderAvailability:
    def test_tavily_disabled_without_key(self):
        s = Settings(_env_file=None, tavily_api_key="")
        assert s.tavily_available is False

    def test_tavily_enabled_with_key(self):
        s = Settings(_env_file=None, tavily_api_key="tvly-xxx")
        assert s.tavily_available is True

    def test_tavily_disabled_by_toggle(self):
        s = Settings(_env_file=None, tavily_api_key="tvly-xxx", enable_tavily=False)
        assert s.tavily_available is False

    def test_brave_disabled_without_key(self):
        s = Settings(_env_file=None, brave_api_key="")
        assert s.brave_available is False

    def test_brave_enabled_with_key(self):
        s = Settings(_env_file=None, brave_api_key="BSA-xxx")
        assert s.brave_available is True

    def test_google_books_disabled_without_key(self):
        s = Settings(_env_file=None, google_books_api_key="")
        assert s.google_books_available is False

    def test_google_books_enabled_with_key(self):
        s = Settings(_env_file=None, google_books_api_key="AIza-xxx")
        assert s.google_books_available is True


class TestValidation:
    def test_weight_must_be_0_to_1(self):
        with pytest.raises(ValueError, match="Weight must be between"):
            Settings(_env_file=None, scoring_authority_weight=1.5)

    def test_weight_negative_rejected(self):
        with pytest.raises(ValueError, match="Weight must be between"):
            Settings(_env_file=None, scoring_relevance_weight=-0.1)

    def test_depth_too_low(self):
        with pytest.raises(ValueError, match="Search depth must be 1-10"):
            Settings(_env_file=None, default_search_depth=0)

    def test_depth_too_high(self):
        with pytest.raises(ValueError, match="Search depth must be 1-10"):
            Settings(_env_file=None, default_search_depth=11)

    def test_limit_too_low(self):
        with pytest.raises(ValueError, match="Result limit must be 1-100"):
            Settings(_env_file=None, default_result_limit=0)

    def test_limit_too_high(self):
        with pytest.raises(ValueError, match="Result limit must be 1-100"):
            Settings(_env_file=None, default_result_limit=101)

    def test_valid_boundary_values(self):
        s = Settings(
            _env_file=None,
            scoring_authority_weight=0.0,
            scoring_relevance_weight=1.0,
            default_search_depth=1,
            default_result_limit=100,
        )
        assert s.scoring_authority_weight == 0.0
        assert s.scoring_relevance_weight == 1.0


class TestEnvOverride:
    def test_env_vars_override_defaults(self):
        env = {
            "APP_ENV": "production",
            "OLLAMA_MODEL": "llama3:8b",
            "DEFAULT_SEARCH_DEPTH": "5",
            "ENABLE_BRAVE": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            s = Settings(_env_file=None)
            assert s.app_env == "production"
            assert s.ollama_model == "llama3:8b"
            assert s.default_search_depth == 5
            assert s.enable_brave is False
