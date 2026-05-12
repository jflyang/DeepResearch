"""服务配置中心 - 统一管理所有 provider 的启用/配置状态。"""

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
    missing_env_vars: list[str] = Field(default_factory=list)
    note: str | None = None


class ServiceRegistry:
    """统一管理所有服务的启用和配置状态。"""

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
        """检查服务是否已正确配置（所有必需环境变量已设置）。"""
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
        for env_var in cfg.get("required_env", []):
            key_name = env_var.lower()
            if "key" in key_name or "secret" in key_name or "token" in key_name:
                result[f"{key_name}_configured"] = env_has_value(env_var)
            else:
                result[key_name] = env_has_value(env_var)
        return result

    def list_services(self) -> list[ServiceStatus]:
        """列出所有服务状态。"""
        return [self._get_status(name) for name in self._services]

    def _get_status(self, service_name: str) -> ServiceStatus:
        cfg = self._services.get(service_name)
        if cfg is None:
            return ServiceStatus(name=service_name, type="unknown", enabled=False, configured=False)

        enabled = self.is_enabled(service_name)
        svc_type: str = cfg.get("type", "unknown")
        required_env: list[str] = cfg.get("required_env", [])
        public_mode: bool = cfg.get("public_mode", False)

        # 检查缺失的环境变量
        missing: list[str] = [var for var in required_env if not env_has_value(var)]

        # 判断 configured
        if public_mode and len(required_env) == 0:
            # 无必需变量且支持 public mode
            configured = True
        elif public_mode and missing:
            # 有可选 key 但支持 public mode
            configured = True
        else:
            configured = len(missing) == 0

        # note
        note: str | None = None
        if public_mode and missing:
            note = cfg.get("note_when_no_key")
        elif public_mode and not required_env:
            note = cfg.get("note_when_no_key")

        return ServiceStatus(
            name=service_name,
            type=svc_type,
            enabled=enabled,
            configured=configured,
            missing_env_vars=missing,
            note=note,
        )
