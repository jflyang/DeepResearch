"""统一设计系统 - 全局 CSS 样式与 Design Tokens。

设计关键词：清晰、克制、专业、统一、商用 SaaS 风格、低噪音、高可读性。
所有页面通过 apply_global_styles() 注入统一样式。
"""

import streamlit as st

# ============================================================
# Design Tokens
# ============================================================

COLORS = {
    # 主色
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_light": "#EFF6FF",
    # 状态色
    "ok": "#16A34A",
    "ok_bg": "#F0FDF4",
    "ok_border": "#BBF7D0",
    "warning": "#CA8A04",
    "warning_bg": "#FEFCE8",
    "warning_border": "#FEF08A",
    "error": "#DC2626",
    "error_bg": "#FEF2F2",
    "error_border": "#FECACA",
    "info": "#2563EB",
    "info_bg": "#EFF6FF",
    "info_border": "#BFDBFE",
    "running": "#7C3AED",
    "running_bg": "#F5F3FF",
    "running_border": "#DDD6FE",
    "inactive": "#9CA3AF",
    "inactive_bg": "#F9FAFB",
    "inactive_border": "#E5E7EB",
    "planned": "#6366F1",
    "planned_bg": "#EEF2FF",
    "planned_border": "#C7D2FE",
    # 中性色
    "neutral_50": "#F9FAFB",
    "neutral_100": "#F3F4F6",
    "neutral_200": "#E5E7EB",
    "neutral_300": "#D1D5DB",
    "neutral_400": "#9CA3AF",
    "neutral_500": "#6B7280",
    "neutral_600": "#4B5563",
    "neutral_700": "#374151",
    "neutral_800": "#1F2937",
    "neutral_900": "#111827",
    # 边框
    "border": "rgba(0, 0, 0, 0.08)",
    "border_hover": "rgba(0, 0, 0, 0.15)",
}

SPACING = {
    "page_top": "24px",
    "section": "24px",
    "card_padding": "16px",
    "card_padding_lg": "20px",
    "card_gap": "12px",
    "form_gap": "12px",
    "button_gap": "8px",
    "xs": "4px",
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "24px",
    "2xl": "32px",
}

TYPOGRAPHY = {
    "page_title": {"size": "28px", "line_height": "32px", "weight": "700"},
    "page_subtitle": {"size": "15px", "line_height": "20px", "weight": "400"},
    "section_title": {"size": "20px", "line_height": "26px", "weight": "650"},
    "card_title": {"size": "16px", "line_height": "22px", "weight": "600"},
    "body": {"size": "14px", "line_height": "21px", "weight": "400"},
    "caption": {"size": "12px", "line_height": "18px", "weight": "400"},
    "code": {"size": "12px", "line_height": "18px", "weight": "400"},
}

RADIUS = {
    "sm": "6px",
    "md": "8px",
    "lg": "12px",
}


# ============================================================
# Global CSS Injection
# ============================================================


def apply_global_styles():
    """注入全局 CSS 样式。每个页面顶部调用一次。"""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# Keep old name as alias for backward compat
inject_global_styles = apply_global_styles


_GLOBAL_CSS = """
<style>
/* ============================================================
   GLOBAL RESET & LAYOUT
   ============================================================ */

.block-container {
    padding-top: 24px !important;
    padding-bottom: 32px !important;
    max-width: 1180px !important;
}

/* ============================================================
   TYPOGRAPHY
   ============================================================ */

/* Page header */
.ds-page-header {
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
.ds-page-title {
    font-size: 28px;
    line-height: 32px;
    font-weight: 700;
    color: #111827;
    margin: 0 0 4px 0;
}
.ds-page-subtitle {
    font-size: 15px;
    line-height: 20px;
    font-weight: 400;
    color: #6B7280;
    margin: 0;
}

/* Section header */
.ds-section-header {
    margin-top: 24px;
    margin-bottom: 12px;
}
.ds-section-title {
    font-size: 20px;
    line-height: 26px;
    font-weight: 650;
    color: #1F2937;
    margin: 0;
}
.ds-section-desc {
    font-size: 13px;
    line-height: 18px;
    color: #6B7280;
    margin: 4px 0 0 0;
}

/* ============================================================
   CARDS
   ============================================================ */

.ds-card {
    background: #FFFFFF;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
}
.ds-card:hover {
    border-color: rgba(0, 0, 0, 0.15);
}
.ds-card-muted {
    background: #F9FAFB;
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
}
.ds-card-title {
    font-size: 16px;
    line-height: 22px;
    font-weight: 600;
    color: #111827;
    margin: 0 0 8px 0;
}

/* ============================================================
   STATUS BADGES
   ============================================================ */

.ds-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 12px;
    line-height: 18px;
    font-weight: 500;
    white-space: nowrap;
    vertical-align: middle;
}
.ds-badge-ok {
    background: #F0FDF4;
    color: #16A34A;
    border: 1px solid #BBF7D0;
}
.ds-badge-warning {
    background: #FEFCE8;
    color: #CA8A04;
    border: 1px solid #FEF08A;
}
.ds-badge-error {
    background: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
}
.ds-badge-info {
    background: #EFF6FF;
    color: #2563EB;
    border: 1px solid #BFDBFE;
}
.ds-badge-running {
    background: #F5F3FF;
    color: #7C3AED;
    border: 1px solid #DDD6FE;
}
.ds-badge-inactive {
    background: #F9FAFB;
    color: #9CA3AF;
    border: 1px solid #E5E7EB;
}
.ds-badge-planned {
    background: #EEF2FF;
    color: #6366F1;
    border: 1px solid #C7D2FE;
}

/* Source level badges */
.ds-level {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    line-height: 1;
}
.ds-level-S { background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; }
.ds-level-A { background: #DBEAFE; color: #1E40AF; border: 1px solid #BFDBFE; }
.ds-level-B { background: #F3F4F6; color: #374151; border: 1px solid #E5E7EB; }
.ds-level-C { background: #F9FAFB; color: #6B7280; border: 1px solid #E5E7EB; }
.ds-level-D { background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }

/* ============================================================
   CODE / JSON BLOCKS
   ============================================================ */

.ds-code-block {
    font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 18px;
    background: #F9FAFB;
    border: 1px solid rgba(0, 0, 0, 0.06);
    border-radius: 8px;
    padding: 12px;
    max-height: 320px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
}

/* ============================================================
   TABLES
   ============================================================ */

.ds-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    line-height: 20px;
}
.ds-table th {
    text-align: left;
    font-weight: 600;
    color: #374151;
    padding: 8px 12px;
    border-bottom: 2px solid #E5E7EB;
    background: #F9FAFB;
}
.ds-table td {
    padding: 8px 12px;
    border-bottom: 1px solid #F3F4F6;
    color: #374151;
}
.ds-table tr:hover td {
    background: #F9FAFB;
}

/* ============================================================
   EMPTY STATE
   ============================================================ */

.ds-empty-state {
    text-align: center;
    padding: 48px 24px;
    color: #6B7280;
}
.ds-empty-state-title {
    font-size: 16px;
    font-weight: 600;
    color: #374151;
    margin-bottom: 8px;
}
.ds-empty-state-desc {
    font-size: 14px;
    line-height: 21px;
    color: #6B7280;
    margin-bottom: 16px;
}

/* ============================================================
   DIVIDER
   ============================================================ */

.ds-divider {
    border: none;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
    margin: 24px 0;
}

/* ============================================================
   STREAMLIT OVERRIDES (subtle)
   ============================================================ */

/* Metric cards */
div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 12px;
    padding: 12px 16px;
}
div[data-testid="stMetric"] label {
    font-size: 12px !important;
    color: #6B7280 !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-size: 22px !important;
    font-weight: 700 !important;
}

/* Expander */
div[data-testid="stExpander"] {
    border: 1px solid rgba(0, 0, 0, 0.08) !important;
    border-radius: 12px !important;
    margin-bottom: 12px;
}

/* Divider */
hr {
    margin-top: 24px !important;
    margin-bottom: 24px !important;
    border-color: rgba(0, 0, 0, 0.06) !important;
}

/* Buttons */
button[kind="primary"] {
    border-radius: 8px !important;
}
button[kind="secondary"] {
    border-radius: 8px !important;
}

/* Sidebar buttons compact */
section[data-testid="stSidebar"] button {
    font-size: 13px !important;
    padding: 4px 8px !important;
}
</style>
"""
