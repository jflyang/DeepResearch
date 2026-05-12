"""Streamlit 入口 - 研究工作台主页。"""

import streamlit as st
from ui.styles import inject_global_styles

st.set_page_config(page_title="Research Collector", page_icon="🔬", layout="wide")

inject_global_styles()

from ui.components.layout import page_header

page_header("Research Collector", "慢速深度研究资料收集器 — 本地研究工作台")

st.markdown("""
### 使用流程

1. **Research** — 输入主题，配置参数，启动搜索
2. **Report Ingestion** — 导入外部研究报告，提取引用来源
3. **Results** — 查看分类结果，提取正文，导出到 Obsidian
4. **Settings** — 配置 LLM、搜索 Provider、Obsidian Vault

---

### 快速开始

1. 确保后端 API 已启动：`make api`
2. 在左侧导航选择 **Research** 页面
3. 输入研究主题，点击「开始研究」
""")
