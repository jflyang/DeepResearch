"""Streamlit 入口 - 研究工作台主页。"""

import streamlit as st

st.set_page_config(page_title="Research Collector", page_icon="🔬", layout="wide")

st.title("🔬 Research Collector")
st.markdown("**慢速深度研究资料收集器** — 本地研究工作台")

st.divider()

st.markdown("""
### 使用流程

1. **Research** — 输入主题，配置参数，启动搜索
2. **Results** — 查看分类结果，下载提取正文
3. **Settings** — 检查 API 配置状态

---

### 快速开始

1. 确保后端 API 已启动：`make api`
2. 在左侧导航选择 **Research** 页面
3. 输入研究主题，点击「开始研究」
""")
