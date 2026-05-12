"""LLM 任务配置加载 - 从 YAML 读取并合并 defaults。"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

_DEFAULT_CONFIG_PATH = Path("config/llm_tasks.yaml")

_cached_config: dict[str, Any] | None = None


class LLMTaskConfig(BaseModel):
    """单个 LLM 任务的完整配置。"""

    provider: str = "ollama_lan"
    model: str = "qwen3:8b"
    temperature: float = 0.2
    max_input_chars: int = 6000
    max_output_tokens: int = 1000
    timeout_seconds: int = 120
    json_required: bool = True
    retry_on_parse_error: bool = True
    max_retries: int = 1
    fallback: str | None = None
    require_llm: bool = False


class TaskNotFoundError(Exception):
    """请求的任务名不存在于配置中。"""

    def __init__(self, task_name: str) -> None:
        self.task_name = task_name
        super().__init__(f"LLM task not found: '{task_name}'")


def _load_raw_config(path: Path | None = None) -> dict[str, Any]:
    """加载并缓存原始 YAML 配置。"""
    global _cached_config
    if _cached_config is not None:
        return _cached_config
    config_path = path or _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"LLM tasks config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    _cached_config = data
    return data


def reset_config_cache() -> None:
    """清除缓存（仅用于测试）。"""
    global _cached_config
    _cached_config = None


def load_llm_task_config(task_name: str, config_path: Path | None = None) -> LLMTaskConfig:
    """加载指定任务配置，未配置字段使用 defaults 填充。"""
    data = _load_raw_config(config_path)
    defaults: dict[str, Any] = data.get("defaults", {})
    tasks: dict[str, Any] = data.get("tasks", {})

    if task_name not in tasks:
        raise TaskNotFoundError(task_name)

    task_overrides: dict[str, Any] = tasks[task_name] or {}
    merged = {**defaults, **task_overrides}

    # 解析 provider: active → 使用当前活跃 provider
    if merged.get("provider") == "active":
        from core.config import get_settings
        settings = get_settings()
        merged["provider"] = settings.active_llm_provider

    return LLMTaskConfig(**merged)
