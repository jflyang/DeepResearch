"""Results - 研究结果工作台。

结构：
1. 侧栏：Research Library（历史任务列表）
2. 主区域：任务摘要 + Tabs (Overview / Sources / Synthesis / Trace / Export)
"""

import streamlit as st
from ui.api_client import APIClient
from ui.styles import apply_global_styles
from ui.components.layout import render_page_header, render_section, render_empty_state, render_warning_callout, render_info_callout, render_error_state, render_success_state
from ui.pages._results_helpers import (
    build_source_filter_state,
    apply_source_filters,
    format_task_summary_cards,
    get_synthesis_button_state,
    get_export_button_state,
)

apply_global_styles()
render_page_header("Results", "查看历史任务、筛选来源、抓取正文、合成研究文档并导出到 Obsidian。")

client = APIClient()


# ============================================================
# 一、侧栏 - Research Library
# ============================================================

with st.sidebar:
    st.markdown("### Research Library")

    history_q = st.text_input("搜索", key="history_search", placeholder="关键词...", label_visibility="collapsed")
    history_status = st.selectbox("状态", ["全部", "completed", "running", "pending", "failed"], key="history_status", label_visibility="collapsed")

    col_r, col_d = st.columns(2)
    with col_r:
        if st.button("刷新", key="refresh_history", use_container_width=True):
            pass
    with col_d:
        show_deleted = st.checkbox("已删除", key="show_deleted_tasks")

    try:
        status_filter = history_status if history_status != "全部" else None
        q_filter = history_q if history_q else None
        tasks_data = client.list_tasks(limit=30, status=status_filter, q=q_filter, include_deleted=show_deleted)
        history_tasks = tasks_data.get("items", [])
    except Exception:
        history_tasks = []

    if history_tasks:
        for ht in history_tasks:
            is_deleted = ht.get("deleted_at") is not None
            status_icon = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}.get(ht["status"], "❓")
            if is_deleted:
                status_icon = "🗑️"
            topic_short = ht["topic"][:25] + ("..." if len(ht["topic"]) > 25 else "")
            src_count = ht.get("source_count", 0)
            hq = ht.get("high_quality_count", 0)

            btn_label = f"{status_icon} {topic_short}"
            btn_help = f"{ht['topic']} | {src_count} sources" + (f" · {hq} S/A" if hq else "")

            if st.button(btn_label, key=f"hist_{ht['task_id']}", help=btn_help, use_container_width=True):
                st.session_state["selected_task_id"] = ht["task_id"]
                st.rerun()

        st.caption(f"共 {tasks_data.get('total', 0)} 个任务")
    else:
        st.caption("暂无研究任务")


# ============================================================
# 任务选择逻辑
# ============================================================

selected_id = st.session_state.get("selected_task_id", "") or st.session_state.get("last_task_id", "")

if not selected_id:
    if history_tasks:
        completed = [t for t in history_tasks if t["status"] == "completed"]
        selected_id = completed[0]["task_id"] if completed else history_tasks[0]["task_id"]

if not selected_id:
    render_empty_state(
        title="请选择一个研究任务",
        description="从左侧 Research Library 选择历史任务，或先到 Research 页面创建新任务。",
        icon="📚",
    )
    st.stop()

# 加载任务
try:
    task = client.get_task(selected_id)
except Exception as e:
    st.error(f"获取任务失败：{e}")
    st.stop()

# 加载来源
try:
    sources_data = client.get_sources(selected_id)
    all_items = sources_data.get("items", [])
    categories = sources_data.get("categories", {})
    total_sources = sources_data.get("total", 0)
except Exception as e:
    st.error(f"获取来源失败：{e}")
    all_items = []
    categories = {}
    total_sources = 0

# Vault 状态
vault_usable = False
vault_path = ""
try:
    obs_cfg = client.get_obsidian_settings()
    if obs_cfg.get("configured") and obs_cfg.get("exists") and obs_cfg.get("writable"):
        vault_usable = True
        vault_path = obs_cfg.get("vault_path", "")
except Exception:
    pass

status = task["status"]
topic = task["topic"]


# ============================================================
# 二、任务摘要区
# ============================================================

# 任务标题行
status_icon = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}.get(status, "❓")
st.markdown(f"### {status_icon} {topic}")

info_parts = [f"模式: {task['mode']}", f"状态: {status}"]
if task.get("created_at"):
    info_parts.append(f"创建: {task['created_at'][:16]}")
st.caption(" · ".join(info_parts))

# Summary Cards
summary_cards = format_task_summary_cards(task, all_items)
cols = st.columns(len(summary_cards))
for col, card in zip(cols, summary_cards):
    col.metric(card["label"], card["value"])

if status != "completed":
    render_warning_callout("任务未完成", f"当前状态为 {status}，结果可能不完整。")


# ============================================================
# 三、主 Tabs
# ============================================================

tab_overview, tab_sources, tab_synthesis, tab_trace, tab_export = st.tabs(
    ["Overview", "Sources", "Synthesis", "Trace", "Export"]
)


# --- Overview Tab ---
with tab_overview:
    render_section("任务信息")

    ov_col1, ov_col2 = st.columns(2)
    with ov_col1:
        st.markdown(f"**主题**: {topic}")
        st.markdown(f"**模式**: {task['mode']}")
        st.markdown(f"**创建时间**: {(task.get('created_at') or '')[:16]}")
    with ov_col2:
        st.markdown(f"**完成时间**: {(task.get('completed_at') or '—')[:16]}")
        st.markdown(f"**来源总数**: {total_sources}")
        extracted_count = sum(1 for s in all_items if s.get("download_status") in ("extracted", "exported"))
        st.markdown(f"**已提取**: {extracted_count}")

    # 任务管理
    with st.expander("任务管理", expanded=False):
        mgmt_col1, mgmt_col2, mgmt_col3 = st.columns(3)

        with mgmt_col1:
            st.markdown("**重命名**")
            new_topic = st.text_input("新名称", value=topic, key="rename_input", label_visibility="collapsed")
            if st.button("保存", key="btn_rename"):
                if new_topic.strip() and new_topic.strip() != topic:
                    try:
                        client.rename_task(selected_id, new_topic.strip())
                        st.success("已重命名")
                        st.rerun()
                    except Exception as e:
                        st.error(f"失败: {e}")

        with mgmt_col2:
            st.markdown("**复制**")
            if st.button("复制并重新研究", key="btn_clone"):
                try:
                    result = client.clone_task(selected_id, rerun_immediately=True)
                    new_id = result.get("new_task_id", "")
                    st.success(f"已复制: {new_id[:8]}...")
                    st.session_state["selected_task_id"] = new_id
                    st.rerun()
                except Exception as e:
                    st.error(f"失败: {e}")

        with mgmt_col3:
            st.markdown("**删除**")
            confirm = st.checkbox("确认删除", key="confirm_delete")
            if st.button("删除任务", key="btn_delete", disabled=not confirm):
                try:
                    client.delete_task(selected_id)
                    st.session_state.pop("selected_task_id", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"失败: {e}")


# --- Sources Tab ---
with tab_sources:
    if not all_items:
        render_empty_state(
            title="暂无来源数据",
            description="该任务还没有来源。请确认研究任务是否已完成。",
            icon="🔍",
        )
    else:
        # Filter bar
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            f_level = st.selectbox("等级", ["全部", "S", "A", "B", "C", "D"], key="f_level")
        with f_col2:
            type_options = ["全部"] + sorted(set(s.get("source_type", "") for s in all_items if s.get("source_type")))
            f_type = st.selectbox("类型", type_options, key="f_type")
        with f_col3:
            f_dl = st.selectbox("提取状态", ["全部", "pending", "extracted", "exported", "failed"], key="f_dl")
        with f_col4:
            f_keyword = st.text_input("关键词", key="f_keyword", placeholder="搜索...", label_visibility="collapsed")

        f_hide_low = st.checkbox("隐藏低质量 (D 级)", value=True, key="f_hide_low")

        filters = build_source_filter_state(
            level=f_level,
            source_type=f_type,
            download_status=f_dl,
            keyword=f_keyword,
            hide_low_quality=f_hide_low,
        )
        filtered = apply_source_filters(all_items, filters)

        # 排序
        level_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
        filtered.sort(key=lambda x: (
            level_order.get(x.get("source_level", "D"), 4),
            -(x.get("relevance_score", 0) + x.get("authority_score", 0)),
        ))

        st.caption(f"显示 {len(filtered)} / {total_sources} 条")

        # 提取队列状态
        try:
            _queue_status = client.get_extraction_queue_status()
            _extracting = sum(1 for s in _queue_status.get("statuses", {}).values() if s.get("status") == "extracting")
            _queued = sum(1 for s in _queue_status.get("statuses", {}).values() if s.get("status") == "queued")
            if _extracting or _queued:
                st.info(f"提取队列：正在提取 {_extracting} · 排队 {_queued}")
        except Exception:
            pass

        # Source list
        for item in filtered:
            level = item.get("source_level", "?")
            level_emoji = {"S": "🏆", "A": "⭐", "B": "📄", "C": "📎", "D": "⚠️"}.get(level, "📄")
            title = item.get("title", "无标题")[:100]
            url = item.get("url", "")
            domain = item.get("domain", "")
            source_type = item.get("source_type", "")
            reason = item.get("reason_to_read", "")
            dl_status = item.get("download_status", "pending")

            with st.container():
                st.markdown(f"{level_emoji} **[{level}]** [{title}]({url})")

                meta_parts = []
                if domain:
                    meta_parts.append(domain)
                if source_type:
                    meta_parts.append(source_type)
                if reason:
                    meta_parts.append(f"💡 {reason}")
                if meta_parts:
                    st.caption(" · ".join(meta_parts))

                scores_col, action_col = st.columns([3, 1])
                with scores_col:
                    rel = item.get("relevance_score", 0)
                    auth = item.get("authority_score", 0)
                    orig = item.get("originality_score", 0)
                    if rel or auth or orig:
                        st.caption(f"相关 {rel:.1f} · 权威 {auth:.1f} · 原创 {orig:.1f}")

                with action_col:
                    _queued_key = f"_queued_{item['id']}"
                    _is_queued = st.session_state.get(_queued_key, False)

                    if dl_status in ("extracted", "exported"):
                        st.session_state.pop(_queued_key, None)
                        st.caption("✅ 已提取")
                    elif _is_queued or dl_status == "downloading":
                        try:
                            _ext_st = client.get_extraction_status(item["id"])
                            _ext_status = _ext_st.get("status", "")
                        except Exception:
                            _ext_status = "queued"

                        if _ext_status == "done":
                            st.session_state.pop(_queued_key, None)
                            st.caption("✅ 已提取")
                        elif _ext_status == "failed":
                            st.session_state.pop(_queued_key, None)
                            st.caption("❌ 失败")
                        else:
                            st.button("⏳ 提取中", key=f"src_extract_{item['id']}", disabled=True)
                    elif dl_status == "pending":
                        def _on_extract(sid=item["id"], qk=_queued_key):
                            try:
                                client.extract_source_async(sid)
                                st.session_state[qk] = True
                            except Exception:
                                pass
                        st.button("提取", key=f"src_extract_{item['id']}", on_click=_on_extract)
                    elif dl_status == "failed":
                        st.caption("❌ 失败")
                    elif dl_status == "skipped":
                        st.caption("⏭️ 跳过")

                # 已提取内容预览
                if dl_status in ("extracted", "exported"):
                    with st.expander("查看内容", expanded=False):
                        try:
                            content_data = client.get_extracted_content(item["id"])
                            if content_data.get("found"):
                                if content_data.get("summary"):
                                    st.markdown(f"**摘要:** {content_data['summary']}")
                                if content_data.get("concepts"):
                                    st.caption(f"概念: {', '.join(content_data['concepts'][:8])}")
                                st.caption(f"字数: {content_data.get('content_length', 0)}")
                            else:
                                st.caption("内容未找到")
                        except Exception as e:
                            st.caption(f"加载失败: {e}")

                st.markdown("---")


# --- Synthesis Tab ---
with tab_synthesis:
    extracted_count = sum(1 for s in all_items if s.get("download_status") in ("extracted", "exported"))

    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("已提取正文", extracted_count)
    col_s2.metric("可参与合成", extracted_count)
    col_s3.metric("总来源", total_sources)

    syn_state = get_synthesis_button_state(status, extracted_count, vault_usable)

    if not syn_state["enabled"]:
        render_warning_callout("无法合成", syn_state["reason"])
    else:
        st.caption(f"将从 sources/ 目录读取 {extracted_count} 篇 .md 文件，合并为 research.md。")

        if st.button(syn_state["label"], type="primary", key="synthesize_btn"):
            with st.spinner("正在合成研究文档..."):
                try:
                    syn_result = client.synthesize_task(selected_id)
                    if syn_result.get("synthesized"):
                        st.success("✅ 研究文档合成完成")
                        st.metric("合并来源数", syn_result.get("source_count", 0))
                        if syn_result.get("research_path"):
                            st.caption(f"路径: `{syn_result['research_path']}`")
                    else:
                        st.error(f"合成失败: {syn_result.get('error', '未知错误')}")
                except Exception as e:
                    st.error(f"合成失败: {e}")


# --- Trace Tab ---
with tab_trace:
    from ui.components.trace_panel import render_trace_panel
    render_trace_panel(selected_id, client)


# --- Export Tab ---
with tab_export:
    export_state = get_export_button_state(status, vault_usable, vault_path)

    if vault_usable:
        st.markdown(f"✅ Vault: `{vault_path}`")
        st.caption(f"目标: `{vault_path}/Research/{topic}/research.md`")
    elif vault_path:
        render_warning_callout("Vault 路径无效", f"路径 `{vault_path}` 不存在或不可写。请到 Settings 修复。")
    else:
        render_info_callout("Obsidian Vault 未配置", "研究可以继续运行，但导出功能不可用。请到 Settings 配置默认 Vault。")
        st.page_link("pages/9_Settings.py", label="前往 Settings 配置", icon="⚙️")

    if export_state["enabled"]:
        if st.button(export_state["label"], type="primary", key="export_btn"):
            with st.spinner("正在导出..."):
                try:
                    result = client.export_index(selected_id)
                    if result.get("success"):
                        st.success(f"✅ 已导出: `{result.get('path', '')}`")
                        st.caption(f"包含 {result.get('source_count', 0)} 个来源")
                    else:
                        st.error(f"导出失败: {result.get('message', '未知错误')}")
                except Exception as e:
                    st.error(f"导出失败: {e}")
    elif export_state["reason"]:
        render_warning_callout("无法导出", export_state["reason"])
