"""UI → FastAPI 的 HTTP 客户端。UI 层通过此模块与后端通信。"""

import time

import httpx

API_BASE = "http://localhost:8000"
TIMEOUT = 120.0

_NO_CACHE_HEADERS = {"Cache-Control": "no-cache"}


class APIClient:
    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def health(self) -> dict:
        r = httpx.get(self._url("/settings/health"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def get_services(self) -> list[dict]:
        """获取服务状态（不缓存，每次请求最新数据）。"""
        r = httpx.get(
            self._url("/settings/services"),
            params={"_ts": int(time.time() * 1000)},
            headers=_NO_CACHE_HEADERS,
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()

    def get_llm_config(self) -> dict:
        r = httpx.get(self._url("/settings/llm"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def test_llm(self, provider: str = "ollama_lan", model: str = "qwen3:8b") -> dict:
        r = httpx.post(
            self._url("/settings/llm/test"),
            json={"provider": provider, "model": model},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def get_search_config(self) -> dict:
        r = httpx.get(self._url("/settings/search"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def create_task(self, payload: dict) -> dict:
        r = httpx.post(self._url("/research/tasks"), json=payload, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def run_research(self, task_id: str) -> dict:
        r = httpx.post(self._url(f"/research/tasks/{task_id}/run"), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def get_task(self, task_id: str) -> dict:
        r = httpx.get(self._url(f"/research/tasks/{task_id}"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def get_sources(self, task_id: str) -> dict:
        r = httpx.get(self._url(f"/research/tasks/{task_id}/sources"), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def extract_source(self, source_id: str) -> dict:
        r = httpx.post(self._url(f"/sources/{source_id}/extract"), timeout=60.0)
        r.raise_for_status()
        return r.json()

    def export_index(self, task_id: str) -> dict:
        r = httpx.post(self._url(f"/research/tasks/{task_id}/export-index"), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def get_events(self, task_id: str, limit: int = 20) -> dict:
        r = httpx.get(self._url(f"/research/tasks/{task_id}/events"), params={"limit": limit}, timeout=10.0)
        r.raise_for_status()
        return r.json()

    # === Ollama Settings ===

    def get_ollama_settings(self) -> dict:
        r = httpx.get(self._url("/settings/llm/ollama"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def test_ollama_connection(self, base_url: str) -> dict:
        r = httpx.post(
            self._url("/settings/llm/ollama/test"),
            json={"base_url": base_url},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()

    def list_ollama_models(self, base_url: str) -> list[dict]:
        r = httpx.post(
            self._url("/settings/llm/ollama/models"),
            json={"base_url": base_url},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("models", [])

    def save_ollama_settings(self, base_url: str, default_model: str, timeout_seconds: int) -> dict:
        r = httpx.post(
            self._url("/settings/llm/ollama/save"),
            json={
                "base_url": base_url,
                "default_model": default_model,
                "timeout_seconds": timeout_seconds,
            },
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()

    # === Cloud LLM Settings ===

    def get_cloud_llm_settings(self) -> dict:
        r = httpx.get(self._url("/settings/llm/cloud"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def test_cloud_llm_connection(
        self, provider: str, base_url: str, api_key: str, model: str
    ) -> dict:
        r = httpx.post(
            self._url("/settings/llm/cloud/test"),
            json={
                "provider": provider,
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
            },
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json()

    def list_cloud_llm_models(self, provider: str, base_url: str, api_key: str) -> dict:
        r = httpx.post(
            self._url("/settings/llm/cloud/models"),
            json={
                "provider": provider,
                "base_url": base_url,
                "api_key": api_key,
            },
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()

    def save_cloud_llm_settings(
        self,
        enabled: bool,
        provider: str,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout_seconds: int,
    ) -> dict:
        r = httpx.post(
            self._url("/settings/llm/cloud/save"),
            json={
                "enabled": enabled,
                "provider": provider,
                "base_url": base_url,
                "api_key": api_key,
                "default_model": default_model,
                "timeout_seconds": timeout_seconds,
            },
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()

    def set_active_llm_provider(self, provider: str) -> dict:
        r = httpx.post(
            self._url("/settings/llm/active-provider"),
            json={"provider": provider},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()

    # === Search Settings ===

    def get_search_settings(self) -> dict:
        r = httpx.get(self._url("/settings/search"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def save_search_settings(self, payload: dict) -> dict:
        r = httpx.post(
            self._url("/settings/search/save"),
            json=payload,
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()

    # === Obsidian Settings ===

    def get_obsidian_settings(self) -> dict:
        r = httpx.get(self._url("/settings/obsidian"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def test_obsidian_path(self, vault_path: str) -> dict:
        r = httpx.post(
            self._url("/settings/obsidian/test"),
            json={"vault_path": vault_path},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()

    def save_obsidian_settings(self, vault_path: str) -> dict:
        r = httpx.post(
            self._url("/settings/obsidian/save"),
            json={"vault_path": vault_path},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()
