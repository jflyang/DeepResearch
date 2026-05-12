"""服务配置中心 - 统一管理所有 provider 的启用/配置状态。

配置读取优先级：
1. config/runtime_settings.json
2. .env
3. 默认值
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.core.feature_flags import env_bool, env_has_value

_DEFAULT_CONFIG_PATH = Path("config/providers.yaml")


class ServiceStatus(BaseModel):
    """单个服务的状态。"""

    name: str
    type: str  # llm / search / extraction / export
    enabled: bool = True
    configured: bool = False
    available: bool = False
    source: str = "default"  # "runtime" | "env" | "default" | "public_mode" | "local"
    missing_keys: list[str] = Field(default_factory=list)
    message: str | None = None
    api_key_configured: bool | None = None
    # 保留向后兼容
    missing_env_vars: list[str] = Field(default_factory=list)
    note: str | None = None


class ServiceRegistry:
    """统一管理所有服务的启用和配置状态。

    每次调用 list_services() 都会重新读取 runtime_settings.json，
    确保保存配置后立即反映最新状态。
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or _DEFAULT_CONFIG_PATH
        self._services: dict[str, dict[str, Any]] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self._config_path.exists():
            return
        with open(self._config_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        self._services = data.get("services", {})

    def _load_runtime_settings(self) -> dict:
        """每次调用时重新读取 runtime_settings.json（不缓存）。

        使用 core.config 中的函数确保路径一致（基于项目根目录解析）。
        """
        from core.config import _load_runtime_settings
        return _load_runtime_settings()

    def is_enabled(self, service_name: str) -> bool:
        """检查服务是否启用。"""
        cfg = self._services.get(service_name)
        if cfg is None:
            return False
        # 静态 enabled 字段
        if "enabled" in cfg and not cfg["enabled"]:
            return False
        # 从环境变量读取 enabled 状态
        enabled_env = cfg.get("enabled_env")
        if enabled_env:
            return env_bool(enabled_env, default=True)
        return True

    def is_configured(self, service_name: str) -> bool:
        """检查服务是否已正确配置。"""
        status = self._get_status(service_name)
        return status.configured

    def get_provider_config(self, service_name: str) -> dict[str, Any]:
        """获取 provider 配置（不暴露 API key 原文）。"""
        cfg = self._services.get(service_name, {})
        result: dict[str, Any] = {
            "name": service_name,
            "type": cfg.get("type", "unknown"),
            "enabled": self.is_enabled(service_name),
            "configured": self.is_configured(service_name),
        }
        # 对 required_env 中的 key 类变量，只返回是否已配置
        runtime = self._load_runtime_settings()
        for env_var in cfg.get("required_env", []):
            key_name = env_var.lower()
            if "key" in key_name or "secret" in key_name or "token" in key_name:
                # 检查 runtime 或 env
                has_value = env_has_value(env_var) or self._has_runtime_value(service_name, env_var, runtime)
                result[f"{key_name}_configured"] = has_value
            else:
                has_value = env_has_value(env_var) or self._has_runtime_value(service_name, env_var, runtime)
                result[key_name] = has_value
        return result

    def list_services(self) -> list[ServiceStatus]:
        """列出所有服务状态（每次重新读取 runtime_settings.json）。"""
        return [self._get_status(name) for name in self._services]

    def _has_runtime_value(self, service_name: str, env_var: str, runtime: dict) -> bool:
        """检查 runtime_settings.json 中是否有对应配置值。

        映射关系：
        - OLLAMA_BASE_URL → runtime.ollama.base_url
        - DEEPSEEK_API_KEY → runtime.cloud_llm.api_key (when provider=deepseek)
        - DEEPSEEK_BASE_URL → runtime.cloud_llm.base_url (when provider=deepseek)
        - DEEPSEEK_DEFAULT_MODEL → runtime.cloud_llm.default_model (when provider=deepseek)
        - OPENAI_API_KEY → runtime.cloud_llm.api_key (when provider=openai)
        - OPENAI_BASE_URL → runtime.cloud_llm.base_url (when provider=openai)
        - OPENAI_DEFAULT_MODEL → runtime.cloud_llm.default_model (when provider=openai)
        - OPENAI_COMPATIBLE_API_KEY → runtime.cloud_llm.api_key (when provider=openai_compatible)
        - OPENAI_COMPATIBLE_BASE_URL → runtime.cloud_llm.base_url (when provider=openai_compatible)
        - OPENAI_COMPATIBLE_DEFAULT_MODEL → runtime.cloud_llm.default_model (when provider=openai_compatible)
        - TAVILY_API_KEY → runtime.search.tavily.api_key
        - BRAVE_API_KEY → runtime.search.brave.api_key
        - OBSIDIAN_VAULT_PATH → runtime.obsidian.vault_path
        """
        env_upper = env_var.upper()

        # Ollama
        if env_upper == "OLLAMA_BASE_URL":
            return bool(runtime.get("ollama", {}).get("base_url"))

        # DeepSeek
        if env_upper == "DEEPSEEK_API_KEY":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "deepseek" and bool(cloud.get("api_key"))
        if env_upper == "DEEPSEEK_BASE_URL":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "deepseek" and bool(cloud.get("base_url"))
        if env_upper == "DEEPSEEK_DEFAULT_MODEL":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "deepseek" and bool(cloud.get("default_model"))

        # OpenAI
        if env_upper == "OPENAI_API_KEY":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "openai" and bool(cloud.get("api_key"))
        if env_upper == "OPENAI_BASE_URL":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "openai" and bool(cloud.get("base_url"))
        if env_upper == "OPENAI_DEFAULT_MODEL":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "openai" and bool(cloud.get("default_model"))

        # OpenAI Compatible
        if env_upper == "OPENAI_COMPATIBLE_API_KEY":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "openai_compatible" and bool(cloud.get("api_key"))
        if env_upper == "OPENAI_COMPATIBLE_BASE_URL":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "openai_compatible" and bool(cloud.get("base_url"))
        if env_upper == "OPENAI_COMPATIBLE_DEFAULT_MODEL":
            cloud = runtime.get("cloud_llm", {})
            return cloud.get("provider") == "openai_compatible" and bool(cloud.get("default_model"))

        # Tavily
        if env_upper == "TAVILY_API_KEY":
            return bool(runtime.get("search", {}).get("tavily", {}).get("api_key"))

        # Brave
        if env_upper == "BRAVE_API_KEY":
            return bool(runtime.get("search", {}).get("brave", {}).get("api_key"))

        # Obsidian
        if env_upper == "OBSIDIAN_VAULT_PATH":
            return bool(runtime.get("obsidian", {}).get("vault_path"))

        return False

    def _get_status(self, service_name: str) -> ServiceStatus:
        cfg = self._services.get(service_name)
        if cfg is None:
            return ServiceStatus(
                name=service_name, type="unknown", enabled=False,
                configured=False, available=False, source="default",
            )

        enabled = self.is_enabled(service_name)
        svc_type: str = cfg.get("type", "unknown")
        required_env: list[str] = cfg.get("required_env", [])
        public_mode: bool = cfg.get("public_mode", False)

        runtime = self._load_runtime_settings()

        # === 特殊处理：trafilatura（本地 extraction，无需配置） ===
        if service_name == "trafilatura":
            return self._get_trafilatura_status(cfg, enabled)

        # === 特殊处理：obsidian（需要验证路径有效性） ===
        if service_name == "obsidian":
            return self._get_obsidian_status(cfg, enabled, runtime)

        # === 特殊处理：google_books（public_mode） ===
        if service_name == "google_books":
            return self._get_google_books_status(cfg, enabled, runtime)

        # === 通用逻辑：检查 runtime → env → missing ===
        missing_keys: list[str] = []
        source = "default"
        has_runtime_value = False
        has_env_value = False
        api_key_configured: bool | None = None

        for var in required_env:
            runtime_has = self._has_runtime_value(service_name, var, runtime)
            env_has = env_has_value(var)

            if runtime_has:
                has_runtime_value = True
            elif env_has:
                has_env_value = True
            else:
                missing_keys.append(var)

            # Track api_key_configured
            if "key" in var.lower() or "secret" in var.lower() or "token" in var.lower():
                if runtime_has or env_has:
                    api_key_configured = True
                else:
                    api_key_configured = False

        # Determine source
        if has_runtime_value and not missing_keys:
            source = "runtime"
        elif has_env_value and not missing_keys:
            source = "env"
        elif has_runtime_value or has_env_value:
            # Partial config from mixed sources
            source = "runtime" if has_runtime_value else "env"

        configured = len(missing_keys) == 0
        available = configured and enabled

        # Build message
        message: str | None = None
        if missing_keys and source == "default":
            message = f"缺少: {', '.join(missing_keys)}"
        elif configured:
            if source == "runtime":
                message = "来源: runtime_settings.json"
            elif source == "env":
                message = "来源: .env"

        return ServiceStatus(
            name=service_name,
            type=svc_type,
            enabled=enabled,
            configured=configured,
            available=available,
            source=source,
            missing_keys=missing_keys,
            message=message,
            api_key_configured=api_key_configured,
            # 向后兼容
            missing_env_vars=missing_keys,
            note=message,
        )

    def _get_trafilatura_status(self, cfg: dict, enabled: bool) -> ServiceStatus:
        """trafilatura 是本地 extraction provider，无需配置。"""
        available = True
        message = "本地 extraction（无需配置）"
        try:
            import trafilatura  # noqa: F401
        except ImportError:
            available = False
            message = "trafilatura 未安装"

        return ServiceStatus(
            name="trafilatura",
            type=cfg.get("type", "extraction"),
            enabled=enabled,
            configured=True,
            available=available,
            source="local",
            missing_keys=[],
            message=message,
            api_key_configured=None,
            missing_env_vars=[],
            note=message,
        )

    def _get_obsidian_status(self, cfg: dict, enabled: bool, runtime: dict) -> ServiceStatus:
        """Obsidian vault 需要验证路径有效性。"""
        vault_path = runtime.get("obsidian", {}).get("vault_path", "")
        source = "runtime" if vault_path else "default"

        # Fallback to env
        if not vault_path:
            vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
            if vault_path:
                source = "env"

        if not vault_path:
            return ServiceStatus(
                name="obsidian",
                type=cfg.get("type", "export"),
                enabled=enabled,
                configured=False,
                available=False,
                source="default",
                missing_keys=["OBSIDIAN_VAULT_PATH"],
                message="缺少: OBSIDIAN_VAULT_PATH",
                api_key_configured=None,
                missing_env_vars=["OBSIDIAN_VAULT_PATH"],
                note="缺少: OBSIDIAN_VAULT_PATH",
            )

        # Validate path
        p = Path(vault_path).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            return ServiceStatus(
                name="obsidian",
                type=cfg.get("type", "export"),
                enabled=enabled,
                configured=False,
                available=False,
                source=source,
                missing_keys=[],
                message=f"路径不存在: {vault_path}",
                api_key_configured=None,
                missing_env_vars=[],
                note=f"路径不存在: {vault_path}",
            )

        if not os.access(p, os.W_OK):
            return ServiceStatus(
                name="obsidian",
                type=cfg.get("type", "export"),
                enabled=enabled,
                configured=False,
                available=False,
                source=source,
                missing_keys=[],
                message=f"路径不可写: {vault_path}",
                api_key_configured=None,
                missing_env_vars=[],
                note=f"路径不可写: {vault_path}",
            )

        message = f"来源: {source}" if source != "default" else None
        return ServiceStatus(
            name="obsidian",
            type=cfg.get("type", "export"),
            enabled=enabled,
            configured=True,
            available=True,
            source=source,
            missing_keys=[],
            message=message,
            api_key_configured=None,
            missing_env_vars=[],
            note=message,
        )

    def _get_google_books_status(self, cfg: dict, enabled: bool, runtime: dict) -> ServiceStatus:
        """Google Books 支持 public_mode。"""
        gb_rt = runtime.get("search", {}).get("google_books", {})
        public_mode = gb_rt.get("public_mode", cfg.get("public_mode", False))
        api_key = gb_rt.get("api_key", "") or os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()

        if public_mode:
            source = "public_mode"
            message = "public mode（无需 API key）"
            configured = True
            api_key_configured = bool(api_key) if api_key else None
        elif api_key:
            source = "runtime" if gb_rt.get("api_key") else "env"
            message = f"来源: {source}"
            configured = True
            api_key_configured = True
        else:
            source = "default"
            message = "需要 API key 或启用 public mode"
            configured = False
            api_key_configured = False

        return ServiceStatus(
            name="google_books",
            type=cfg.get("type", "search"),
            enabled=enabled,
            configured=configured,
            available=configured and enabled,
            source=source,
            missing_keys=[],
            message=message,
            api_key_configured=api_key_configured,
            missing_env_vars=[],
            note=message,
        )
