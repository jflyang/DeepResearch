"""外部信号源 - 从 TrendRadar 等外部信号源收集热点与舆情线索。"""

import streamlit as st
from ui.styles import apply_global_styles
from ui.components.layout import render_page_header, render_section, render_empty_state

apply_global_styles()
render_page_header("External Signals", "从 TrendRadar 等外部信号源收集热点与舆情线索。")

# === 功能占位 ===

render_empty_state(
    title="即将上线",
    description="外部信号源功能正在开发中。未来将支持从 TrendRadar、RSS、Twitter 等渠道自动收集热点话题，并一键转为研究任务。",
    icon="📡",
)
