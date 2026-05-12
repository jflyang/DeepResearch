"""设置与健康检查 API 测试 - 使用 MockLLMProvider，不访问真实网络。"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.llm.base import LLMResponse, ProviderHealth
from app.providers.llm.mock import MockLLMProvider
from core.config import reset_settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    reset_settings()
    yield
    reset_settings()


# === GET /settings/services ===


class TestListServices:
    def test_returns_list(self, client) -> None:
        response = client.get("/settings/services")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_no_secrets_in_response(self, client) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-super-secret"}, clear=False):
            reset_settings()
            response = client.get("/settings/services")
            text = response.text
            assert "sk-super-secret" not in text

    def test_service_fields(self, client) -> None:
        response = client.get("/settings/services")
        data = response.json()
        for svc in data:
            assert "name" in svc
            assert "type" in svc
            assert "enabled" in svc
            assert "configured" in svc
            assert "missing_env_vars" in svc


# === GET /settings/llm ===


class TestGetLLMConfig:
    def test_returns_config(self, client) -> None:
        response = client.get("/settings/llm")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "ollama_lan"
        assert "enabled" in data
        assert "configured" in data
        assert "default_model" in data
        assert "timeout_seconds" in data

    def test_base_url_masked(self, client) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.50:11434"}, clear=False):
            reset_settings()
            response = client.get("/settings/llm")
            data = response.json()
            # 不应包含完整 URL，只有 host:port
            assert "http://" not in data["base_url_host"]
            assert "192.168.1.50" in data["base_url_host"]
            assert "11434" in data["base_url_host"]

    def test_no_api_key_in_response(self, client) -> None:
        response = client.get("/settings/llm")
        text = response.text
        assert "api_key" not in text.lower() or "configured" in text.lower()


# === POST /settings/llm/test ===


class TestLLMTest:
    def test_mock_provider_reachable(self, client) -> None:
        mock_provider = MockLLMProvider(response_text="pong")
        with patch("app.api.routes_settings._llm_router.get_provider", return_value=mock_provider):
            response = client.post("/settings/llm/test", json={
                "provider": "mock_llm",
                "model": "mock",
            })
        assert response.status_code == 200
        data = response.json()
        assert data["reachable"] is True
        assert data["error"] is None
        assert data["generate_ok"] is True

    def test_provider_not_found(self, client) -> None:
        response = client.post("/settings/llm/test", json={
            "provider": "nonexistent",
            "model": "x",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["reachable"] is False
        assert data["error"] is not None

    def test_health_check_failure(self, client) -> None:
        mock_provider = MockLLMProvider()
        mock_provider.health_check = AsyncMock(return_value=ProviderHealth(
            provider="mock", reachable=False, latency_ms=50, error="connection refused",
        ))
        with patch("app.api.routes_settings._llm_router.get_provider", return_value=mock_provider):
            response = client.post("/settings/llm/test", json={
                "provider": "mock_llm",
                "model": "mock",
            })
        data = response.json()
        assert data["reachable"] is False
        assert data["error"] == "connection refused"
        assert data["latency_ms"] == 50

    def test_generate_failure(self, client) -> None:
        mock_provider = MockLLMProvider()
        mock_provider.health_check = AsyncMock(return_value=ProviderHealth(
            provider="mock", reachable=True, latency_ms=5,
        ))
        mock_provider.generate = AsyncMock(side_effect=RuntimeError("model not found"))
        with patch("app.api.routes_settings._llm_router.get_provider", return_value=mock_provider):
            response = client.post("/settings/llm/test", json={
                "provider": "mock_llm",
                "model": "bad_model",
            })
        data = response.json()
        assert data["reachable"] is True
        assert data["generate_ok"] is False


# === GET /settings/search ===


class TestGetSearchConfig:
    def test_returns_all_providers(self, client) -> None:
        response = client.get("/settings/search")
        assert response.status_code == 200
        data = response.json()
        assert "tavily" in data
        assert "brave" in data
        assert "google_books" in data

    def test_no_api_key_values(self, client) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-secret-key"}, clear=False):
            reset_settings()
            response = client.get("/settings/search")
            text = response.text
            assert "sk-secret-key" not in text

    def test_api_key_configured_flag(self, client) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "sk-xxx"}, clear=False):
            reset_settings()
            response = client.get("/settings/search")
            data = response.json()
            assert data["brave"]["api_key_configured"] is True

    def test_google_books_public_mode(self, client) -> None:
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": ""}, clear=False):
            reset_settings()
            response = client.get("/settings/search")
            data = response.json()
            assert data["google_books"]["configured"] is True
            assert data["google_books"]["mode"] == "public"

    def test_tavily_not_configured_without_key(self, client) -> None:
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            reset_settings()
            response = client.get("/settings/search")
            data = response.json()
            assert data["tavily"]["api_key_configured"] is False


# === GET /settings/llm/ollama ===


class TestGetOllamaConfig:
    def test_returns_ollama_config(self, client) -> None:
        response = client.get("/settings/llm/ollama")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "configured" in data
        assert "base_url" in data
        assert "host" in data
        assert "default_model" in data
        assert "timeout_seconds" in data

    def test_missing_base_url_shows_not_configured(self, client) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": ""}, clear=False):
            reset_settings()
            response = client.get("/settings/llm/ollama")
            data = response.json()
            assert data["configured"] is False
            assert data["host"] == ""

    def test_configured_with_lan_url(self, client) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.50:11434"}, clear=False):
            reset_settings()
            response = client.get("/settings/llm/ollama")
            data = response.json()
            assert data["configured"] is True
            assert "192.168.1.50" in data["host"]


# === POST /settings/llm/ollama/test ===


class TestOllamaTest:
    def test_ollama_reachable(self, client) -> None:
        mock_health = ProviderHealth(
            provider="ollama", reachable=True, latency_ms=15, error=None
        )
        with patch(
            "app.api.routes_settings.OllamaProvider.health_check",
            new_callable=AsyncMock,
            return_value=mock_health,
        ):
            response = client.post(
                "/settings/llm/ollama/test",
                json={"base_url": "http://192.168.1.50:11434"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["reachable"] is True
        assert data["latency_ms"] == 15
        assert data["error"] is None

    def test_ollama_unreachable(self, client) -> None:
        mock_health = ProviderHealth(
            provider="ollama", reachable=False, latency_ms=100, error="connection refused"
        )
        with patch(
            "app.api.routes_settings.OllamaProvider.health_check",
            new_callable=AsyncMock,
            return_value=mock_health,
        ):
            response = client.post(
                "/settings/llm/ollama/test",
                json={"base_url": "http://10.0.0.99:11434"},
            )
        data = response.json()
        assert data["reachable"] is False
        assert data["error"] == "connection refused"


# === POST /settings/llm/ollama/models ===


class TestOllamaModels:
    def test_list_models_returns_names(self, client) -> None:
        from app.providers.llm.ollama import OllamaModelInfo

        mock_models = [
            OllamaModelInfo(name="qwen3:8b", modified_at="2026-05-01", size=4500000000),
            OllamaModelInfo(name="llama3:8b", modified_at="2026-04-20", size=4200000000),
        ]
        with patch(
            "app.api.routes_settings.OllamaProvider.list_models",
            new_callable=AsyncMock,
            return_value=mock_models,
        ):
            response = client.post(
                "/settings/llm/ollama/models",
                json={"base_url": "http://192.168.1.50:11434"},
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data["models"]) == 2
        assert data["models"][0]["name"] == "qwen3:8b"
        assert data["models"][1]["name"] == "llama3:8b"

    def test_list_models_empty(self, client) -> None:
        with patch(
            "app.api.routes_settings.OllamaProvider.list_models",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.post(
                "/settings/llm/ollama/models",
                json={"base_url": "http://192.168.1.50:11434"},
            )
        data = response.json()
        assert data["models"] == []


# === POST /settings/llm/ollama/save ===


class TestOllamaSave:
    def test_save_settings_writes_runtime_file(self, client, tmp_path) -> None:
        runtime_path = tmp_path / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
                mock_save.return_value = None
                response = client.post(
                    "/settings/llm/ollama/save",
                    json={
                        "base_url": "http://192.168.1.50:11434",
                        "default_model": "qwen3:8b",
                        "timeout_seconds": 120,
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify save_runtime_settings was called with correct args
        mock_save.assert_called_once_with("ollama", {
            "base_url": "http://192.168.1.50:11434",
            "default_model": "qwen3:8b",
            "timeout_seconds": 120,
        })

    def test_save_settings_integration(self, client, tmp_path) -> None:
        """Integration test: actually write and read runtime_settings.json."""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            with patch(
                "app.api.routes_settings.save_runtime_settings",
                side_effect=lambda section, data: _write_runtime(runtime_path, section, data),
            ):
                response = client.post(
                    "/settings/llm/ollama/save",
                    json={
                        "base_url": "http://10.0.0.5:11434",
                        "default_model": "deepseek-r1:7b",
                        "timeout_seconds": 180,
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify file content
        content = json.loads(runtime_path.read_text())
        assert content["ollama"]["base_url"] == "http://10.0.0.5:11434"
        assert content["ollama"]["default_model"] == "deepseek-r1:7b"
        assert content["ollama"]["timeout_seconds"] == 180


# === GET /settings/llm/cloud ===


class TestGetCloudLLMConfig:
    def test_returns_cloud_config(self, client) -> None:
        response = client.get("/settings/llm/cloud")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "provider" in data
        assert "base_url" in data
        assert "default_model" in data
        assert "timeout_seconds" in data
        assert "api_key_configured" in data

    def test_no_api_key_in_response(self, client) -> None:
        """API key 明文不应出现在响应中。"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-super-secret-key"}, clear=False):
            reset_settings()
            response = client.get("/settings/llm/cloud")
            text = response.text
            assert "sk-super-secret-key" not in text

    def test_api_key_configured_flag(self, client) -> None:
        with patch.dict(os.environ, {
            "ENABLE_CLOUD_LLM": "true",
            "CLOUD_LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
        }, clear=False):
            reset_settings()
            response = client.get("/settings/llm/cloud")
            data = response.json()
            assert data["api_key_configured"] is True
            assert data["provider"] == "deepseek"


# === POST /settings/llm/cloud/test ===


class TestCloudLLMTest:
    def test_cloud_reachable(self, client) -> None:
        mock_health = ProviderHealth(
            provider="deepseek", reachable=True, latency_ms=80, error=None
        )
        with patch(
            "app.api.routes_settings.OpenAICompatibleProvider.health_check",
            new_callable=AsyncMock,
            return_value=mock_health,
        ):
            response = client.post(
                "/settings/llm/cloud/test",
                json={
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-test",
                    "model": "deepseek-chat",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["reachable"] is True
        assert data["latency_ms"] == 80

    def test_cloud_unreachable(self, client) -> None:
        mock_health = ProviderHealth(
            provider="openai", reachable=False, latency_ms=200, error="connection refused"
        )
        with patch(
            "app.api.routes_settings.OpenAICompatibleProvider.health_check",
            new_callable=AsyncMock,
            return_value=mock_health,
        ):
            response = client.post(
                "/settings/llm/cloud/test",
                json={
                    "provider": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-bad",
                    "model": "gpt-4",
                },
            )
        data = response.json()
        assert data["reachable"] is False
        assert data["error"] == "connection refused"

    def test_api_key_not_in_response(self, client) -> None:
        """确保测试响应中不包含 API key。"""
        mock_health = ProviderHealth(
            provider="deepseek", reachable=True, latency_ms=50, error=None
        )
        with patch(
            "app.api.routes_settings.OpenAICompatibleProvider.health_check",
            new_callable=AsyncMock,
            return_value=mock_health,
        ):
            response = client.post(
                "/settings/llm/cloud/test",
                json={
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-my-secret-key-12345",
                    "model": "deepseek-chat",
                },
            )
        assert "sk-my-secret-key-12345" not in response.text


# === POST /settings/llm/cloud/models ===


class TestCloudLLMModels:
    def test_list_models_returns_ids(self, client) -> None:
        from app.providers.llm.openai_compatible import CloudModelInfo

        mock_models = [
            CloudModelInfo(id="deepseek-chat", owned_by="deepseek"),
            CloudModelInfo(id="deepseek-coder", owned_by="deepseek"),
        ]
        with patch(
            "app.api.routes_settings.OpenAICompatibleProvider.list_models",
            new_callable=AsyncMock,
            return_value=mock_models,
        ):
            response = client.post(
                "/settings/llm/cloud/models",
                json={
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-test",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data["models"]) == 2
        assert data["models"][0]["id"] == "deepseek-chat"
        assert data["note"] is None

    def test_list_models_empty_returns_note(self, client) -> None:
        with patch(
            "app.api.routes_settings.OpenAICompatibleProvider.list_models",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.post(
                "/settings/llm/cloud/models",
                json={
                    "provider": "openai_compatible",
                    "base_url": "https://custom.api.com/v1",
                    "api_key": "sk-test",
                },
            )
        data = response.json()
        assert data["models"] == []
        assert data["note"] is not None


# === POST /settings/llm/cloud/save ===


class TestCloudLLMSave:
    def test_save_cloud_config(self, client) -> None:
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            mock_save.return_value = None
            response = client.post(
                "/settings/llm/cloud/save",
                json={
                    "enabled": True,
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-test-key",
                    "default_model": "deepseek-chat",
                    "timeout_seconds": 120,
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        mock_save.assert_called_once_with("cloud_llm", {
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-test-key",
            "default_model": "deepseek-chat",
            "timeout_seconds": 120,
        })

    def test_save_response_no_api_key(self, client) -> None:
        """保存响应中不应包含 API key。"""
        with patch("app.api.routes_settings.save_runtime_settings"):
            response = client.post(
                "/settings/llm/cloud/save",
                json={
                    "enabled": True,
                    "provider": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-secret-openai-key",
                    "default_model": "gpt-4",
                    "timeout_seconds": 60,
                },
            )
        assert "sk-secret-openai-key" not in response.text


# === POST /settings/llm/active-provider ===


class TestActiveProvider:
    def test_set_active_provider(self, client) -> None:
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            mock_save.return_value = None
            response = client.post(
                "/settings/llm/active-provider",
                json={"provider": "deepseek"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["active_provider"] == "deepseek"

    def test_invalid_provider_rejected(self, client) -> None:
        response = client.post(
            "/settings/llm/active-provider",
            json={"provider": "nonexistent"},
        )
        data = response.json()
        assert data["success"] is False


def _write_runtime(path: Path, section: str, data: dict) -> None:
    """Helper to write runtime settings for integration test."""
    current = {}
    if path.exists():
        current = json.loads(path.read_text())
    current[section] = data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2))


# === POST /settings/search/save ===


class TestSearchSave:
    def test_save_brave_api_key(self, client) -> None:
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            with patch("app.api.routes_settings._load_runtime_settings", return_value={}):
                response = client.post(
                    "/settings/search/save",
                    json={
                        "brave": {"enabled": True, "api_key": "BSA-new-key"},
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Verify save was called with brave key
        call_args = mock_save.call_args[0]
        assert call_args[0] == "search"
        assert call_args[1]["brave"]["api_key"] == "BSA-new-key"
        assert call_args[1]["brave"]["enabled"] is True

    def test_empty_api_key_does_not_overwrite(self, client) -> None:
        existing = {"search": {"brave": {"enabled": True, "api_key": "BSA-existing"}}}
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            with patch("app.api.routes_settings._load_runtime_settings", return_value=existing):
                response = client.post(
                    "/settings/search/save",
                    json={
                        "brave": {"enabled": True, "api_key": ""},
                    },
                )
        assert response.status_code == 200
        # Empty string should not overwrite
        call_args = mock_save.call_args[0]
        assert call_args[1]["brave"]["api_key"] == "BSA-existing"

    def test_null_api_key_does_not_overwrite(self, client) -> None:
        existing = {"search": {"tavily": {"enabled": True, "api_key": "tvly-existing"}}}
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            with patch("app.api.routes_settings._load_runtime_settings", return_value=existing):
                response = client.post(
                    "/settings/search/save",
                    json={
                        "tavily": {"enabled": True, "api_key": None},
                    },
                )
        assert response.status_code == 200
        call_args = mock_save.call_args[0]
        assert call_args[1]["tavily"]["api_key"] == "tvly-existing"

    def test_clear_key_with_sentinel(self, client) -> None:
        existing = {"search": {"brave": {"enabled": True, "api_key": "BSA-old"}}}
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            with patch("app.api.routes_settings._load_runtime_settings", return_value=existing):
                response = client.post(
                    "/settings/search/save",
                    json={
                        "brave": {"enabled": True, "api_key": "__CLEAR__"},
                    },
                )
        assert response.status_code == 200
        call_args = mock_save.call_args[0]
        assert call_args[1]["brave"]["api_key"] == ""

    def test_google_books_public_mode(self, client) -> None:
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            with patch("app.api.routes_settings._load_runtime_settings", return_value={}):
                response = client.post(
                    "/settings/search/save",
                    json={
                        "google_books": {"enabled": True, "public_mode": True},
                    },
                )
        assert response.status_code == 200
        call_args = mock_save.call_args[0]
        assert call_args[1]["google_books"]["public_mode"] is True

    def test_no_api_key_in_search_response(self, client) -> None:
        """GET /settings/search 不返回 API key 明文。"""
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-secret-12345"}, clear=False):
            reset_settings()
            response = client.get("/settings/search")
            assert "tvly-secret-12345" not in response.text


# === GET /settings/obsidian ===


class TestObsidianConfig:
    def test_not_configured_by_default(self, client) -> None:
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": ""}, clear=False):
            reset_settings()
            response = client.get("/settings/obsidian")
            assert response.status_code == 200
            data = response.json()
            assert data["configured"] is False
            assert data["vault_path"] == ""
            assert data["exists"] is False
            assert data["writable"] is False

    def test_configured_with_valid_path(self, client, tmp_path) -> None:
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": str(vault_dir)}, clear=False):
            reset_settings()
            response = client.get("/settings/obsidian")
            data = response.json()
            assert data["configured"] is True
            assert data["exists"] is True
            assert data["writable"] is True


# === POST /settings/obsidian/test ===


class TestObsidianTest:
    def test_valid_path(self, client, tmp_path) -> None:
        vault_dir = tmp_path / "test_vault"
        vault_dir.mkdir()
        response = client.post(
            "/settings/obsidian/test",
            json={"vault_path": str(vault_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["writable"] is True
        assert data["error"] is None

    def test_nonexistent_path(self, client, tmp_path) -> None:
        fake_path = str(tmp_path / "nonexistent")
        response = client.post(
            "/settings/obsidian/test",
            json={"vault_path": fake_path},
        )
        data = response.json()
        assert data["exists"] is False
        assert data["writable"] is False
        assert data["error"] is not None


# === POST /settings/obsidian/save ===


class TestObsidianSave:
    def test_save_valid_path(self, client, tmp_path) -> None:
        vault_dir = tmp_path / "save_vault"
        vault_dir.mkdir()
        with patch("app.api.routes_settings.save_runtime_settings") as mock_save:
            response = client.post(
                "/settings/obsidian/save",
                json={"vault_path": str(vault_dir)},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_save.assert_called_once()

    def test_save_nonexistent_path_fails(self, client, tmp_path) -> None:
        fake_path = str(tmp_path / "does_not_exist")
        response = client.post(
            "/settings/obsidian/save",
            json={"vault_path": fake_path},
        )
        data = response.json()
        assert data["success"] is False
        assert "不存在" in data["message"]
