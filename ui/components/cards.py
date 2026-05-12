"""统一卡片组件 - 统计卡片、信息卡片等。"""

import streamlit as st


def metric_row(metrics: list[dict]):
    """渲染一行统计指标卡片。

    Args:
        metrics: [{"label": "总来源", "value": 120}, ...]
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(m["label"], m["value"])


def info_card(content: str, variant: str = "default"):
    """渲染信息卡片。

    Args:
        content: Markdown 内容
        variant: "default" | "muted"
    """
    css_class = "ds-card-muted" if variant == "muted" else "ds-card"
    st.markdown(f'<div class="{css_class}">{content}</div>', unsafe_allow_html=True)


def stat_card(value: str | int, label: str):
    """渲染单个统计卡片（HTML 版本，用于自定义布局）。"""
    return f'''<div class="metric-card">
        <div class="metric-value">{value}</div>
        <div class="metric-label">{label}</div>
    </div>'''


def stat_row_html(stats: list[dict]):
    """渲染一行 HTML 统计卡片。

    Args:
        stats: [{"value": 120, "label": "总来源"}, ...]
    """
    cols_html = "".join(
        f'<div style="flex:1;">{stat_card(s["value"], s["label"])}</div>'
        for s in stats
    )
    st.markdown(
        f'<div style="display:flex; gap:0.75rem; margin-bottom:1rem;">{cols_html}</div>',
        unsafe_allow_html=True,
    )
