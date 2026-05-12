"""LLM Router - 根据 provider name 返回对应 BaseLLMProvider 实例。"""

import os
from pathlib import Path
from typing import Any

import yaml

from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.ollama import OllamaProvider
from app.providers.llm.openai_compatible import OpenAICompatibleProvider
from core.config import get_settings

_DEFAULT_PROVIDERS_PATH = Path("config/providers.yaml")


class LLMProviderNotFound(Exception):
    """请求的 provider 不存在于配置中。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"LLM provider not found: '{name}'")


class LLMProviderDisabled(Exception):
    """请求的 provider 已被禁用。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"LLM provider disabled: '{name}'")


class LLMProviderConfigError(Exception):
    """Provider 缺少必要配置。"""

    def __init__(self, name: str, missing: str) -> None:
        self.name = name
        self.missing = missing
        super().__init__(f"LLM provider '{name}' missing config: {missing}")


class LLMRouter:
    """根据 provider name 返回对应 BaseLLMProvider 实例。"""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or _DEFAULT_PROVIDERS_PATH
        self._providers_config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self._config_path.exists():
            return
        with open(self._config_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        self._providers_config = data.get("llm_providers", {})

    def get_provider(self, name: str) -> BaseLLMProvider:
        """根据 provider name 返回实例。"""
        settings = get_settings()

        # ENABLE_LLM=false 时，只允许 mock
        if not settings.enable_llm:
            if name == "mock_llm":
                return MockLLMProvider()
            raise LLMProviderDisabled(name)

        if name not in self._providers_config:
            raise LLMProviderNotFound(name)

        cfg = self._providers_config[name]

        # 检查 enabled（静态或环境变量）
        if not self._is_enabled(cfg):
            raise LLMProviderDisabled(name)

        provider_type: str = cfg.get("type", "")
        return self._create_provider(name, provider_type, cfg)

    def _is_enabled(self, cfg: dict[str, Any]) -> bool:
        """检查 provider 是否启用。"""
        if "enabled" in cfg and not cfg["enabled"]:
            return False
        enabled_env = cfg.get("enabled_env")
        if enabled_env:
            val = os.environ.get(enabled_env, "").strip().lower()
            if val in ("0", "false", "no", "off"):
                return False
        return True

    def _create_provider(self, name: str, provider_type: str, cfg: dict[str, Any]) -> BaseLLMProvider:
        settings = get_settings()

        if provider_type == "ollama":
            base_url = self._env_val(cfg.get("base_url_env"), settings.ollama_base_url)
            return OllamaProvider(base_url=base_url)

        if provider_type == "openai_compatible":
            return self._create_openai_compatible(name, cfg)

        if provider_type == "mock":
            return MockLLMProvider()

        raise LLMProviderNotFound(f"unknown type: {provider_type}")

    def _create_openai_compatible(self, name: str, cfg: dict[str, Any]) -> OpenAICompatibleProvider:
        """创建 OpenAI-compatible provider，校验必要配置。"""
        settings = get_settings()

        # 从 runtime_settings 中读取 cloud_llm 覆盖
        from core.config import _load_runtime_settings
        runtime = _load_runtime_settings()
        cloud_rt = runtime.get("cloud_llm", {})

        # 判断是否应该使用 runtime 覆盖
        use_runtime = cloud_rt.get("provider") == name

        base_url = self._env_val(cfg.get("base_url_env"), "")
        api_key = self._env_val(cfg.get("api_key_env"), "")
        default_model = self._env_val(cfg.get("default_model_env"), "")
        timeout_str = self._env_val(cfg.get("timeout_seconds_env"), "120")

        # Runtime overrides for the active cloud provider
        if use_runtime:
            if cloud_rt.get("base_url"):
                base_url = cloud_rt["base_url"]
            if cloud_rt.get("api_key"):
                api_key = cloud_rt["api_key"]
            if cloud_rt.get("default_model"):
                default_model = cloud_rt["default_model"]
            if cloud_rt.get("timeout_seconds"):
                timeout_str = str(cloud_rt["timeout_seconds"])

        if not base_url:
            raise LLMProviderConfigError(name, "base_url")
        if not api_key:
            raise LLMProviderConfigError(name, "api_key")
        if not default_model:
            raise LLMProviderConfigError(name, "default_model")

        timeout = int(timeout_str) if timeout_str.isdigit() else 120

        return OpenAICompatibleProvider(
            name=name,
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            timeout_seconds=timeout,
        )

    def _env_val(self, env_key: str | None, default: str) -> str:
        """从环境变量读取值，fallback 到 default。"""
        if not env_key:
            return default
        return os.environ.get(env_key, "").strip() or default

    @property
    def available_providers(self) -> list[str]:
        return list(self._providers_config.keys())


# 兼容旧 gateway 引用
ProviderRouter = LLMRouter
