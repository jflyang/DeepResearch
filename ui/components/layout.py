"""统一布局组件 - 页面头部、Section、分隔、状态展示。

所有函数直接渲染到 Streamlit（返回 None）。
HTML 输出使用 ds- 前缀 class，样式定义在 ui/styles.py。
"""

from __future__ import annotations

import streamlit as st


# ============================================================
# Page Header
# ============================================================


def render_page_header(
    title: str,
    subtitle: str | None = None,
    icon: str | None = None,
    actions: list[dict] | None = None,
):
    """渲染统一页面标题区域。"""
    display_title = f"{icon} {title}" if icon else title
    subtitle_html = f'<p class="ds-page-subtitle">{subtitle}</p>' if subtitle else ""

    st.markdown(
        f'<div class="ds-page-header">'
        f'<h1 class="ds-page-title">{display_title}</h1>'
        f'{subtitle_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    if actions:
        cols = st.columns(len(actions) + 3)
        for i, action in enumerate(actions):
            with cols[-(len(actions) - i)]:
                st.button(action.get("label", ""), key=action.get("key", f"action_{i}"))


# ============================================================
# Section
# ============================================================


def render_section(
    title: str,
    description: str | None = None,
    icon: str | None = None,
):
    """渲染统一 Section 标题。"""
    display_title = f"{icon} {title}" if icon else title
    desc_html = f'<p class="ds-section-desc">{description}</p>' if description else ""

    st.markdown(
        f'<div class="ds-section-header">'
        f'<h2 class="ds-section-title">{display_title}</h2>'
        f'{desc_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_divider():
    """渲染统一分隔线。"""
    st.markdown('<hr class="ds-divider">', unsafe_allow_html=True)


def render_two_column_layout(left_ratio: int = 2, right_ratio: int = 1):
    """返回两列布局的 columns 对象。"""
    return st.columns([left_ratio, right_ratio])


# ============================================================
# State Components - 空状态、错误、成功、警告、信息
# ============================================================


def render_empty_state(
    title: str,
    description: str,
    action_label: str | None = None,
    action_callback=None,
    icon: str = "📭",
):
    """渲染空状态占位。

    Args:
        title: 标题（短）
        description: 说明文字（告诉用户下一步做什么）
        action_label: 可选操作按钮文案
        action_callback: 可选按钮回调（如果提供，渲染为 st.button）
        icon: 图标，默认 📭
    """
    st.markdown(
        f'<div class="ds-empty-state">'
        f'<div style="font-size:32px;margin-bottom:12px;">{icon}</div>'
        f'<div class="ds-empty-state-title">{title}</div>'
        f'<div class="ds-empty-state-desc">{description}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if action_label and action_callback:
        _, col_center, _ = st.columns([2, 1, 2])
        with col_center:
            if st.button(action_label, use_container_width=True):
                action_callback()
    elif action_label:
        st.markdown(
            f'<div style="text-align:center;margin-top:8px;">'
            f'<span style="color:#2563EB;font-size:14px;font-weight:500;">{action_label}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_error_state(
    title: str,
    description: str,
    details: str | None = None,
    action_label: str | None = None,
    action_callback=None,
):
    """渲染错误状态。

    Args:
        title: 错误标题（短）
        description: 可操作建议
        details: 可选技术详情（折叠显示）
        action_label: 可选操作按钮
        action_callback: 按钮回调
    """
    st.markdown(
        f'<div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:12px;padding:16px 20px;margin-bottom:12px;">'
        f'<div style="font-size:15px;font-weight:600;color:#991B1B;margin-bottom:4px;">{title}</div>'
        f'<div style="font-size:13px;color:#7F1D1D;line-height:1.5;">{description}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if details:
        with st.expander("技术详情", expanded=False):
            st.code(details, language=None)

    if action_label and action_callback:
        if st.button(action_label):
            action_callback()


def render_success_state(
    title: str,
    description: str,
    details: str | None = None,
    action_label: str | None = None,
    action_callback=None,
):
    """渲染成功状态。

    Args:
        title: 成功标题
        description: 后续说明
        details: 可选详情
        action_label: 可选操作按钮
        action_callback: 按钮回调
    """
    st.markdown(
        f'<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:12px;padding:16px 20px;margin-bottom:12px;">'
        f'<div style="font-size:15px;font-weight:600;color:#166534;margin-bottom:4px;">{title}</div>'
        f'<div style="font-size:13px;color:#14532D;line-height:1.5;">{description}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if details:
        st.caption(details)

    if action_label and action_callback:
        if st.button(action_label):
            action_callback()


def render_warning_callout(title: str, description: str):
    """渲染警告提示条。

    Args:
        title: 警告标题
        description: 说明和建议
    """
    st.markdown(
        f'<div style="background:#FEFCE8;border:1px solid #FEF08A;border-radius:12px;padding:14px 18px;margin-bottom:12px;">'
        f'<div style="font-size:14px;font-weight:600;color:#854D0E;margin-bottom:2px;">{title}</div>'
        f'<div style="font-size:13px;color:#713F12;line-height:1.5;">{description}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_info_callout(title: str, description: str):
    """渲染信息提示条。

    Args:
        title: 信息标题
        description: 说明
    """
    st.markdown(
        f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:12px;padding:14px 18px;margin-bottom:12px;">'
        f'<div style="font-size:14px;font-weight:600;color:#1E40AF;margin-bottom:2px;">{title}</div>'
        f'<div style="font-size:13px;color:#1E3A5F;line-height:1.5;">{description}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Backward-compatible aliases
# ============================================================

page_header = render_page_header
section_title = render_section
section_divider = render_divider
