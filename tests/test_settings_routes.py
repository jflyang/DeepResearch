"""测试 Settings API 路由。"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建 FastAPI test client。"""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_runtime(tmp_path):
    """Mock runtime_settings.json 到临时文件。"""
    settings_path = tmp_path / "runtime_settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    with patch("core.config._RUNTIME_SETTINGS_PATH", settings_path):
        from core.config import reset_settings
        reset_settings()
        yield settings_path
        reset_settings()


class TestServicePriorityAPI:
    """GET/POST /settings/service-priority 测试。"""

    def test_get_service_priority_returns_llm_and_search(self, client):
        """GET /settings/service-priority 返回 llm/search_policy。"""
        r = client.get("/settings/service-priority")
        assert r.status_code == 200
        data = r.json()
        assert "llm" in data
        assert "search_policy" in data
        assert "active_provider" in data["llm"]
        assert "mode" in data["search_policy"]

    def test_save_and_read_back(self, client, mock_runtime):
        """POST /settings/service-priority/save 后 GET 能读回。"""
        payload = {
            "llm": {
                "active_provider": "deepseek",
                "provider_priority": ["deepseek", "ollama_lan", "mock_llm"],
                "providers": {
                    "deepseek": {"enabled": True},
                    "ollama_lan": {"enabled": False},
                    "mock_llm": {"enabled": True},
                },
            },
            "search_policy": {
                "mode": "free_first",
                "paid_providers_enabled": False,
                "provider_priority": {"web": ["wikipedia", "searxng"]},
                "providers": {
                    "tavily": {"enabled": True, "mode": "fallback"},
                    "brave": {"enabled": False},
                },
            },
        }
        r = client.post("/settings/service-priority/save", json=payload)
        assert r.status_code == 200
        assert r.json()["success"] is True

        # Read back
        r2 = client.get("/settings/service-priority")
        assert r2.status_code == 200
        data = r2.json()
        assert data["llm"]["active_provider"] == "deepseek"
        assert data["search_policy"]["mode"] == "free_first"

    def test_api_does_not_return_api_key(self, client):
        """API 不返回 API key 明文。"""
        r = client.get("/settings/services")
        assert r.status_code == 200
        services = r.json()
        for svc in services:
            assert "api_key" not in svc

    def test_save_refreshes_services(self, client, mock_runtime):
        """保存后 GET /settings/services 立即刷新状态。"""
        # Save with deepseek active
        payload = {
            "llm": {
                "active_provider": "mock_llm",
                "provider_priority": ["mock_llm"],
                "providers": {"mock_llm": {"enabled": True}},
            },
            "search_policy": {
                "mode": "free_first",
                "paid_providers_enabled": False,
                "provider_priority": {},
                "providers": {},
            },
        }
        r = client.post("/settings/service-priority/save", json=payload)
        assert r.status_code == 200

        # Check services reflect the change
        r2 = client.get("/settings/service-priority")
        assert r2.status_code == 200
        assert r2.json()["llm"]["active_provider"] == "mock_llm"
