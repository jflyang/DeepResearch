"""统一状态组件 - Badge、状态指示器。

所有函数返回 HTML 字符串，供 st.markdown(..., unsafe_allow_html=True) 使用。
不包含用户输入的原始 HTML，安全使用。
"""

from __future__ import annotations


# ============================================================
# Status Badge
# ============================================================

# 状态 → (css_variant, icon, default_label)
_STATUS_MAP: dict[str, tuple[str, str, str]] = {
    # 通用
    "ok": ("ok", "✅", "正常"),
    "completed": ("ok", "✅", "已完成"),
    "configured": ("ok", "✅", "已配置"),
    "extracted": ("ok", "✅", "已提取"),
    "exported": ("ok", "✅", "已导出"),
    "success": ("ok", "✅", "成功"),
    # 运行中
    "running": ("running", "🔄", "运行中"),
    "extracting": ("running", "🔄", "提取中"),
    "downloading": ("running", "🔄", "下载中"),
    "pending": ("info", "🕐", "等待中"),
    "queued": ("info", "🕐", "排队中"),
    # 警告
    "warning": ("warning", "⚠️", "警告"),
    "degraded": ("warning", "⚠️", "降级"),
    # 错误
    "error": ("error", "❌", "错误"),
    "failed": ("error", "❌", "失败"),
    # 非活跃
    "inactive": ("inactive", "⚪", "未启用"),
    "disabled": ("inactive", "⚪", "已禁用"),
    "skipped": ("inactive", "⏭️", "跳过"),
    # 规划
    "planned": ("planned", "🧩", "规划中"),
    "not_implemented": ("planned", "🧩", "未实现"),
    # 功能类
    "info": ("info", "ℹ️", "信息"),
    "llm": ("info", "🤖", "LLM"),
    "search": ("info", "🔎", "搜索"),
    "export": ("info", "📤", "导出"),
}


def status_badge(label: str | None = None, status: str = "inactive") -> str:
    """生成通用状态 Badge HTML。

    Args:
        label: 显示文本。如果为 None，使用 status 对应的默认标签。
        status: 状态标识符，映射到样式和图标。

    Returns:
        HTML 字符串，可用于 st.markdown(..., unsafe_allow_html=True)
    """
    status_key = (status or "inactive").lower().strip()
    variant, icon, default_label = _STATUS_MAP.get(status_key, ("inactive", "⚪", status_key))
    display_label = label if label is not None else default_label

    return (
        f'<span class="ds-badge ds-badge-{variant}">'
        f'{icon} {display_label}'
        f'</span>'
    )


def service_status_badge(
    enabled: bool = False,
    configured: bool = False,
    active: bool = False,
) -> str:
    """生成服务状态 Badge。

    逻辑：
    - active + enabled + configured → ok "运行中"
    - enabled + configured → ok "已配置"
    - enabled + not configured → warning "未配置"
    - not enabled → inactive "未启用"
    """
    if not enabled:
        return status_badge("未启用", "inactive")
    if not configured:
        return status_badge("未配置", "warning")
    if active:
        return status_badge("运行中", "running")
    return status_badge("已配置", "ok")


def task_status_badge(status: str) -> str:
    """生成任务状态 Badge。

    Args:
        status: "completed" | "running" | "pending" | "failed" | "cancelled" | ...
    """
    label_map = {
        "completed": "已完成",
        "running": "运行中",
        "pending": "等待中",
        "failed": "失败",
        "cancelled": "已取消",
    }
    label = label_map.get(status, status)
    return status_badge(label, status)


def source_level_badge(level: str) -> str:
    """生成来源等级 Badge HTML。

    Args:
        level: "S" | "A" | "B" | "C" | "D"

    Returns:
        HTML 字符串
    """
    safe_level = (level or "?").upper().strip()
    css_class = f"ds-level-{safe_level}" if safe_level in ("S", "A", "B", "C", "D") else "ds-level-C"
    return f'<span class="ds-level {css_class}">{safe_level}</span>'


def llm_task_status_badge(status: str) -> str:
    """生成 LLM 任务状态 Badge。

    Args:
        status: "used_llm" | "fallback" | "skipped_not_reached" | "skipped_disabled"
                | "skipped_not_implemented" | "skipped_missing_prompt"
                | "rule_only" | "covered_by" | "waiting"
    """
    llm_status_map = {
        "used_llm": ("已执行", "ok"),
        "fallback": ("降级", "warning"),
        "skipped_not_reached": ("未到达", "inactive"),
        "skipped_disabled": ("已禁用", "inactive"),
        "skipped_not_implemented": ("未实现", "planned"),
        "skipped_missing_prompt": ("缺少模板", "warning"),
        "rule_only": ("规则处理", "info"),
        "covered_by": ("已覆盖", "inactive"),
        "waiting": ("等待中", "pending"),
    }
    label, variant = llm_status_map.get(status, (status, "inactive"))
    return status_badge(label, variant)


def download_status_badge(status: str) -> str:
    """生成下载/提取状态 Badge。"""
    dl_map = {
        "pending": ("待提取", "pending"),
        "downloading": ("提取中", "running"),
        "extracted": ("已提取", "extracted"),
        "exported": ("已导出", "exported"),
        "failed": ("失败", "failed"),
        "skipped": ("跳过", "skipped"),
    }
    label, variant = dl_map.get(status, (status, "inactive"))
    return status_badge(label, variant)


# ============================================================
# Inline helpers
# ============================================================


def status_dot(active: bool, label: str = "") -> str:
    """生成状态圆点指示器 HTML。"""
    color = "#16A34A" if active else "#D1D5DB"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;">'
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};"></span>'
        f'<span style="font-size:13px;color:#374151;">{label}</span>'
        f'</span>'
    )


def render_badge(text: str, variant: str = "inactive"):
    """直接渲染 Badge 到 Streamlit（便捷方法）。"""
    st_import = __import__("streamlit")
    st_import.markdown(status_badge(text, variant), unsafe_allow_html=True)


# === Backward-compatible aliases ===

badge = status_badge
level_badge = source_level_badge
render_status_indicator = lambda active, label: __import__("streamlit").markdown(
    status_dot(active, label), unsafe_allow_html=True
)
