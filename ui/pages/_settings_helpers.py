"""Settings 页面纯函数 - 可独立测试，不依赖 Streamlit。"""

from __future__ import annotations


# ============================================================
# Service Display State
# ============================================================


def build_service_display_state(service: dict) -> dict:
    """构建单个服务的显示状态。

    Args:
        service: 来自 GET /settings/services 的单个服务数据

    Returns:
        {
            "name": str,
            "type": str,
            "status": "active" | "ok" | "warning" | "inactive" | "error",
            "icon": str,
            "label": str,
            "message": str,
        }
    """
    name = service.get("name", "Unknown")
    svc_type = service.get("type", "unknown")
    severity = service.get("severity", "inactive")
    active = service.get("active", False)
    message = service.get("message") or service.get("note", "")

    # 映射 severity → 显示状态
    if active and severity == "ok":
        status = "active"
        icon = "✅"
        label = "当前使用"
    elif severity == "ok":
        status = "ok"
        icon = "✅"
        label = "可用"
    elif severity == "warning":
        status = "warning"
        icon = "⚠️"
        label = "启用但缺配置"
    elif severity == "error":
        status = "error"
        icon = "❌"
        label = "错误"
    else:
        status = "inactive"
        icon = "⚪"
        label = "未启用"

    return {
        "name": name,
        "type": svc_type,
        "status": status,
        "icon": icon,
        "label": label,
        "message": message,
    }


# ============================================================
# Group Services
# ============================================================


def group_services_by_type(services: list[dict]) -> dict[str, list[dict]]:
    """将服务列表按 type 分组。

    Returns:
        {"llm": [...], "search": [...], "storage": [...], ...}
    """
    groups: dict[str, list[dict]] = {}
    for svc in services:
        display = build_service_display_state(svc)
        svc_type = display["type"]
        if svc_type not in groups:
            groups[svc_type] = []
        groups[svc_type].append(display)
    return groups


# ============================================================
# Provider Card Status
# ============================================================


def get_provider_card_status(
    provider_name: str,
    enabled: bool = False,
    configured: bool = False,
    is_active: bool = False,
    api_key_set: bool = False,
) -> dict:
    """获取 Provider 卡片的显示状态。

    Returns:
        {
            "name": str,
            "status": "active" | "ok" | "warning" | "inactive",
            "icon": str,
            "label": str,
            "needs_action": bool,
            "action_hint": str | None,
        }
    """
    if not enabled:
        return {
            "name": provider_name,
            "status": "inactive",
            "icon": "⚪",
            "label": "未启用",
            "needs_action": False,
            "action_hint": None,
        }

    if is_active and configured:
        return {
            "name": provider_name,
            "status": "active",
            "icon": "✅",
            "label": "当前使用",
            "needs_action": False,
            "action_hint": None,
        }

    if configured:
        return {
            "name": provider_name,
            "status": "ok",
            "icon": "✅",
            "label": "可用",
            "needs_action": False,
            "action_hint": None,
        }

    # enabled but not configured
    action = "需要配置 API Key" if not api_key_set else "需要完成配置"
    return {
        "name": provider_name,
        "status": "warning",
        "icon": "⚠️",
        "label": "启用但缺配置",
        "needs_action": True,
        "action_hint": action,
    }


# ============================================================
# API Key Masking
# ============================================================


def mask_api_key_status(config: dict) -> dict:
    """处理 API key 显示状态，不暴露实际值。

    Args:
        config: 包含 api_key_configured, enabled 等字段的配置

    Returns:
        {
            "configured": bool,
            "placeholder": str,
            "help_text": str,
        }
    """
    configured = config.get("api_key_configured", False)

    if configured:
        return {
            "configured": True,
            "placeholder": "已配置（留空保留，重新输入可更换）",
            "help_text": "✅ API Key 已配置",
        }
    return {
        "configured": False,
        "placeholder": "请输入 API Key",
        "help_text": "⚠️ API Key 未配置",
    }
