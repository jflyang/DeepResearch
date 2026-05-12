"""研究任务页面 - 创建并运行研究任务。"""

import streamlit as st
from ui.api_client import APIClient

st.header("📝 新建研究任务")

client = APIClient()

# === 输入表单 ===

with st.form("research_form"):
    topic = st.text_input("研究主题", placeholder="例如：Elon Musk、FTX 事件、量子计算")

    col1, col2 = st.columns(2)
    with col1:
        mode = st.selectbox("研究模式", ["auto", "person", "company", "event", "concept"], index=0)
        depth = st.selectbox("搜索深度", ["shallow", "standard", "deep"], index=1)

    with col2:
        include_gossip = st.checkbox("包含八卦线索", value=False)
        include_books = st.checkbox("包含图书资料", value=True)
        include_video = st.checkbox("包含视频资料", value=False)

    obsidian_path = st.text_input("Obsidian Vault 路径", placeholder="/path/to/your/vault（可选）")

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
                    "obsidian_path": obsidian_path.strip(),
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

        st.info(f"前往 **Results** 页面查看详细结果，Task ID: `{task_id}`")

        # 保存到 session state
        st.session_state["last_task_id"] = task_id
