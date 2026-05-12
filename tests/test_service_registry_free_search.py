"""测试 ServiceRegistry 免费搜索 Provider 状态。"""

import os
import pytest
from unittest.mock import patch
from pathlib import Path

from app.core.service_registry import ServiceRegistry


@pytest.fixture
def config_path():
    """使用项目实际的 providers.yaml。"""
    return Path("config/providers.yaml")


class TestFreeSearchProviderStatus:
    """测试免费搜索 Provider 在 ServiceRegistry 中的状态。"""

    def test_open_library_enabled_configured(self, config_path):
        """Open Library enabled 时 configured=true（无需 API key）。"""
        with patch.dict(os.environ, {"ENABLE_OPEN_LIBRARY": "true"}, clear=False):
            registry = ServiceRegistry(config_path=config_path)
            status = registry._get_status("open_library")

        assert status.enabled is True
        assert status.configured is True

    def test_crossref_enabled_configured(self, config_path):
        """Crossref enabled 时 configured=true（无需 API key）。"""
        with patch.dict(os.environ, {"ENABLE_CROSSREF": "true"}, clear=False):
            registry = ServiceRegistry(config_path=config_path)
            status = registry._get_status("crossref")

        assert status.enabled is True
        assert status.configured is True

    def test_arxiv_enabled_configured(self, config_path):
        """arXiv enabled 时 configured=true（无需 API key）。"""
        with patch.dict(os.environ, {"ENABLE_ARXIV": "true"}, clear=False):
            registry = ServiceRegistry(config_path=config_path)
            status = registry._get_status("arxiv")

        assert status.enabled is True
        assert status.configured is True

    def test_wikipedia_enabled_configured(self, config_path):
        """Wikipedia enabled 时 configured=true（无需 API key）。"""
        with patch.dict(os.environ, {"ENABLE_WIKIPEDIA": "true"}, clear=False):
            registry = ServiceRegistry(config_path=config_path)
            status = registry._get_status("wikipedia")

        assert status.enabled is True
        assert status.configured is True

    def test_searxng_missing_base_url_not_configured(self, config_path):
        """SearXNG 缺 base_url 时 configured=false。"""
        env = {"ENABLE_SEARXNG": "true", "SEARXNG_BASE_URL": ""}
        with patch.dict(os.environ, env, clear=False):
            # 确保环境变量存在但为空
            registry = ServiceRegistry(config_path=config_path)
            status = registry._get_status("searxng")

        assert status.enabled is True
        assert status.configured is False
        assert "SEARXNG_BASE_URL" in status.missing_keys

    def test_searxng_with_base_url_configured(self, config_path):
        """SearXNG 有 base_url 时 configured=true。"""
        env = {"ENABLE_SEARXNG": "true", "SEARXNG_BASE_URL": "http://localhost:8080"}
        with patch.dict(os.environ, env, clear=False):
            registry = ServiceRegistry(config_path=config_path)
            status = registry._get_status("searxng")

        assert status.enabled is True
        assert status.configured is True

    def test_tavily_disabled_by_default(self, config_path):
        """Tavily 在 free_first 模式下默认 disabled（无 API key）。"""
        env = {"ENABLE_TAVILY": "true", "TAVILY_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.core.service_registry.ServiceRegistry._load_runtime_settings", return_value={}):
                registry = ServiceRegistry(config_path=config_path)
                status = registry._get_status("tavily")

        # Tavily requires API key, so configured=false without it
        assert status.configured is False
