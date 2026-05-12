"""统一表单组件 - 表单 Section、配置面板等。"""

import streamlit as st


def form_section(title: str):
    """开始一个表单 Section（使用 st.container + 样式）。

    用法：
        with form_section("LLM 配置"):
            st.text_input(...)
    """
    st.markdown(
        f'<div class="form-section-title">{title}</div>',
        unsafe_allow_html=True,
    )


def config_item(label: str, value: str, status: str = "ok"):
    """渲染单行配置项状态。

    Args:
        label: 配置项名称
        value: 当前值
        status: "ok" | "warning" | "error" | "inactive"
    """
    icons = {"ok": "✅", "warning": "⚠️", "error": "❌", "inactive": "⚪"}
    icon = icons.get(status, "⚪")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.375rem 0;font-size:0.8125rem;">'
        f'<span>{icon}</span>'
        f'<span style="color:#374151;font-weight:500;">{label}</span>'
        f'<span style="color:#6B7280;">—</span>'
        f'<span style="color:#6B7280;">{value}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def save_button_row(label: str = "保存", key: str = "save_btn"):
    """渲染保存按钮行（右对齐）。"""
    _, col_btn = st.columns([3, 1])
    with col_btn:
        return st.button(f"💾 {label}", key=key, type="primary", use_container_width=True)
    return False
