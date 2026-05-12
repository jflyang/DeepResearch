"""研究任务页面 - 创建并运行研究任务。"""

import streamlit as st
from ui.api_client import APIClient

st.header("📝 新建研究任务")

client = APIClient()

# === Obsidian Vault 状态 ===

obsidian_path = ""
vault_usable = False

try:
    obsidian_config = client.get_obsidian_settings()
    configured = obsidian_config.get("configured", False)
    exists = obsidian_config.get("exists", False)
    writable = obsidian_config.get("writable", False)
    vault_path_setting = obsidian_config.get("vault_path", "")

    if configured and exists and writable:
        vault_usable = True
        obsidian_path = vault_path_setting
        st.markdown(f"📁 **Obsidian Vault**　✅ 默认 Vault 可用：`{vault_path_setting}`")
    elif configured and not exists:
        st.warning(f"📁 **Obsidian Vault**　⚠️ 默认 Vault 路径无效：路径不存在 — `{vault_path_setting}`　[前往 Settings 修复](/3_Settings)")
    elif configured and not writable:
        st.warning(f"📁 **Obsidian Vault**　⚠️ 默认 Vault 路径无效：路径不可写 — `{vault_path_setting}`　[前往 Settings 修复](/3_Settings)")
    else:
        st.info("📁 **Obsidian Vault**　⚠️ 未配置默认 Vault。研究可以运行，但 Markdown/Obsidian 导出功能不可用。请到 [Settings](/3_Settings) 配置。")
except Exception:
    st.info("📁 **Obsidian Vault**　⚠️ 无法获取 Vault 配置（后端未连接？）。研究仍可运行，但导出不可用。")

st.divider()

# === 输入表单 ===

with st.form("research_form"):
    topic = st.text_input("研究主题", placeholder="例如：库克的童年故事、黄仁勋早期创业、OpenAI 宫斗")

    col1, col2 = st.columns(2)
    with col1:
        mode = st.selectbox("研究模式", ["auto", "person", "company", "event", "concept"], index=0)
        depth = st.selectbox("搜索深度", ["shallow", "standard", "deep"], index=1)

    with col2:
        include_gossip = st.checkbox("包含八卦线索", value=False)
        include_books = st.checkbox("包含图书资料", value=True)
        include_video = st.checkbox("包含视频资料", value=False)

    submitted = st.form_submit_button("🚀 开始研究", type="primary")

# === 执行逻辑 ===

if submitted:
    if not topic.strip():
        st.error("请输入研究主题")
    else:
        # 创建任务
        with st.spinner("正在创建研究任务..."):
            try:
                result = client.create_task({
                    "topic": topic.strip(),
                    "mode": mode,
                    "depth": depth,
                    "include_gossip": include_gossip,
                    "include_books": include_books,
                    "include_video": include_video,
                    "obsidian_path": obsidian_path,
                })
                task_id = result["task_id"]
                st.success(f"任务已创建：`{task_id}`")
            except Exception as e:
                st.error(f"创建任务失败：{e}")
                st.stop()

        # 运行研究
        with st.spinner("正在搜索和分析资料，请稍候..."):
            try:
                summary = client.run_research(task_id)
            except Exception as e:
                st.error(f"研究执行失败：{e}")
                st.stop()

        # 展示结果摘要
        st.divider()
        st.subheader("✅ 研究完成")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("扩展查询数", summary.get("total_queries", 0))
        col2.metric("原始结果", summary.get("total_raw_results", 0))
        col3.metric("去重后", summary.get("total_after_dedup", 0))
        col4.metric("最终保存", summary.get("total_saved", 0))

        errors = summary.get("provider_errors", [])
        if errors:
            with st.expander(f"⚠️ {len(errors)} 个 Provider 错误"):
                for err in errors:
                    st.warning(err)

        # 下一步提示
        st.divider()
        st.markdown(f"""
**下一步：**
- 前往 **Results** 页面查看详细结果、筛选来源、提取正文
- 在 Results 页面可以导出研究索引到 Obsidian Vault
""")

        # 保存到 session state 并提供跳转
        st.session_state["last_task_id"] = task_id
        st.session_state["selected_task_id"] = task_id

        st.page_link("pages/2_Results.py", label="📊 查看研究结果", icon="📊")
