"""结果浏览页面 - 查看分类结果，下载提取正文。"""

import streamlit as st
from ui.api_client import APIClient

st.header("📊 研究结果")

client = APIClient()

# === Task ID 输入 ===

default_task_id = st.session_state.get("last_task_id", "")
task_id = st.text_input("Task ID", value=default_task_id, placeholder="输入任务 ID")

if not task_id.strip():
    st.info("请输入 Task ID 或先在 Research 页面创建任务。")
    st.stop()

# === 加载任务状态 ===

try:
    task = client.get_task(task_id.strip())
except Exception as e:
    st.error(f"获取任务失败：{e}")
    st.stop()

# 任务信息
col1, col2, col3 = st.columns(3)
col1.markdown(f"**主题**: {task['topic']}")
col2.markdown(f"**模式**: {task['mode']}")
col3.markdown(f"**状态**: {task['status']}")

if task["status"] != "completed":
    st.warning(f"任务状态为 `{task['status']}`，结果可能不完整。")

st.divider()

# === 加载来源 ===

try:
    sources_data = client.get_sources(task_id.strip())
except Exception as e:
    st.error(f"获取来源失败：{e}")
    st.stop()

categories = sources_data.get("categories", {})
total = sources_data.get("total", 0)

if total == 0:
    st.info("暂无来源数据。请先运行研究任务。")
    st.stop()

# === 统计 ===

st.subheader("📈 统计")

all_items = []
for items in categories.values():
    all_items.extend(items)

# 去重统计
seen_urls = set()
unique_items = []
for item in all_items:
    if item["url"] not in seen_urls:
        seen_urls.add(item["url"])
        unique_items.append(item)

s_a_count = sum(1 for i in unique_items if i["source_level"] in ("S", "A"))
downloadable = sum(1 for i in unique_items if i["download_status"] == "pending")
gossip_items = categories.get("八卦与旁证", [])

col1, col2, col3, col4 = st.columns(4)
col1.metric("总 URL 数", len(unique_items))
col2.metric("A 级以上", s_a_count)
col3.metric("可下载", downloadable)
col4.metric("八卦线索", len(gossip_items))

st.divider()

# === 分类 Tabs ===

display_categories = ["必读资料", "一手资料", "深度报道", "图书资料", "八卦与旁证"]
available_cats = [cat for cat in display_categories if cat in categories]

if not available_cats:
    # 显示所有有内容的分类
    available_cats = list(categories.keys())

if available_cats:
    tabs = st.tabs(available_cats)

    for tab, cat_name in zip(tabs, available_cats):
        with tab:
            items = categories[cat_name]
            if not items:
                st.info("该分类暂无内容。")
                continue

            for item in items:
                level_emoji = {"S": "🏆", "A": "⭐", "B": "📄", "C": "📎", "D": "⚠️"}
                emoji = level_emoji.get(item["source_level"], "📄")

                with st.container():
                    col_main, col_action = st.columns([4, 1])
                    with col_main:
                        st.markdown(
                            f"{emoji} **[{item['source_level']}]** "
                            f"[{item['title'][:80]}]({item['url']})"
                        )
                        st.caption(f"{item.get('reason_to_read', '')} | {item['source_type']}")
                    with col_action:
                        if item["download_status"] == "pending":
                            if st.button("📥 提取", key=f"extract_{item['id']}"):
                                with st.spinner("提取中..."):
                                    try:
                                        result = client.extract_source(item["id"])
                                        if result.get("status") == "extracted":
                                            st.success("提取成功")
                                        else:
                                            st.warning("提取失败")
                                    except Exception as e:
                                        st.error(f"提取失败：{e}")
                        else:
                            st.caption(f"✅ {item['download_status']}")
                    st.divider()
else:
    st.info("暂无分类数据。")

# === 事件日志 ===

st.divider()
st.subheader("📋 任务事件日志")

try:
    events_data = client.get_events(task_id.strip(), limit=20)
    events = events_data.get("events", [])

    if events:
        for event in events:
            level = event.get("level", "info")
            icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
            time_str = event.get("created_at", "")[:19].replace("T", " ")
            st.caption(f"{icon} `{time_str}` **{event['event_type']}** — {event['message']}")
    else:
        st.info("暂无事件记录。")
except Exception as e:
    st.warning(f"无法加载事件日志：{e}")
