"""统一来源卡片组件 - 来源列表渲染。"""

import streamlit as st
from ui.components.status import level_badge, download_status_badge


def render_source_item_html(item: dict) -> str:
    """生成单个来源的 HTML 卡片（不含交互按钮）。

    Args:
        item: 来源数据字典

    Returns:
        HTML 字符串
    """
    level = item.get("source_level", "?")
    title = item.get("title", "无标题")[:100]
    url = item.get("url", "")
    domain = item.get("domain", "")
    source_type = item.get("source_type", "")
    snippet = item.get("snippet", "")
    reason = item.get("reason_to_read", "")

    # 分数
    rel = item.get("relevance_score", 0)
    auth = item.get("authority_score", 0)
    orig = item.get("originality_score", 0)

    # 构建 meta
    meta_parts = []
    if domain:
        meta_parts.append(domain)
    if source_type:
        meta_parts.append(source_type)
    meta_str = " · ".join(meta_parts)

    # 分数行
    scores_str = ""
    if rel or auth or orig:
        scores_str = f'<div class="source-scores">相关 {rel:.1f} · 权威 {auth:.1f} · 原创 {orig:.1f}</div>'

    # 理由
    reason_str = ""
    if reason:
        reason_str = f'<div style="font-size:0.75rem;color:#6B7280;margin-top:0.25rem;">💡 {reason}</div>'

    return f'''<div class="source-card">
        <div style="display:flex;align-items:center;gap:0.5rem;">
            {level_badge(level)}
            <a href="{url}" target="_blank" class="source-title" style="text-decoration:none;color:#111827;">{title}</a>
        </div>
        <div class="source-meta">{meta_str}</div>
        {scores_str}
        {reason_str}
    </div>'''


def render_source_list_header(total: int, filtered: int):
    """渲染来源列表头部统计。"""
    if filtered < total:
        st.caption(f"显示 {filtered} / {total} 条来源")
    else:
        st.caption(f"共 {total} 条来源")
