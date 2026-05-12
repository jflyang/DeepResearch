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

    def list_tasks(self, limit: int = 50, offset: int = 0, status: str | None = None, q: str | None = None) -> dict:
        """获取研究任务列表。"""
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if q:
            params["q"] = q
        r = httpx.get(self._url("/research/tasks"), params=params, timeout=10.0)
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

    def get_trace(self, task_id: str, level: str | None = None, phase: str | None = None, limit: int = 500) -> dict:
        """获取任务执行轨迹。"""
        params = {"limit": limit}
        if level:
            params["level"] = level
        if phase:
            params["phase"] = phase
        r = httpx.get(self._url(f"/research/tasks/{task_id}/trace"), params=params, timeout=10.0)
        r.raise_for_status()
        return r.json()

    def get_trace_summary(self, task_id: str) -> dict:
        """获取任务执行轨迹摘要。"""
        r = httpx.get(self._url(f"/research/tasks/{task_id}/trace/summary"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def get_trace_llm(self, task_id: str) -> dict:
        """获取任务 LLM 使用详情。"""
        r = httpx.get(self._url(f"/research/tasks/{task_id}/trace/llm"), timeout=10.0)
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

    # === Report Ingestion ===

    def get_service_priority(self) -> dict:
        """获取服务优先级配置。"""
        r = httpx.get(self._url("/settings/service-priority"), timeout=10.0)
        r.raise_for_status()
        return r.json()

    def save_service_priority(self, payload: dict) -> dict:
        """保存服务优先级配置。"""
        r = httpx.post(
            self._url("/settings/service-priority/save"),
            json=payload,
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()

    # === Report Ingestion ===

    def create_report_import_task(
        self,
        topic: str,
        report_text: str,
        report_source: str | None = None,
        output_language: str = "zh",
        options: dict | None = None,
    ) -> dict:
        """创建外部报告导入任务。"""
        payload = {
            "topic": topic,
            "report_text": report_text,
            "report_source": report_source,
            "output_language": output_language,
        }
        if options:
            payload["options"] = options
        r = httpx.post(self._url("/research/import-report"), json=payload, timeout=30.0)
        r.raise_for_status()
        return r.json()

    def parse_report_import_task(self, task_id: str) -> dict:
        """解析已导入的报告。"""
        r = httpx.post(
            self._url(f"/research/import-report/{task_id}/parse"), timeout=30.0
        )
        r.raise_for_status()
        return r.json()

    def run_report_import_task(self, task_id: str) -> dict:
        """执行报告导入任务。"""
        r = httpx.post(
            self._url(f"/research/import-report/{task_id}/run"), timeout=TIMEOUT
        )
        r.raise_for_status()
        return r.json()

    def get_imported_report(self, task_id: str, include_full: bool = False) -> dict:
        """获取导入报告详情。"""
        params = {}
        if include_full:
            params["include_full"] = "true"
        r = httpx.get(
            self._url(f"/research/tasks/{task_id}/imported-report"),
            params=params,
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()
