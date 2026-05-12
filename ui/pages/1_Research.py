"""Research 页面 - 任务创建与执行控制台。

结构：
1. 顶部主操作区（Tabs: Simple / Advanced / Batch）
2. 任务队列面板
3. 实时执行流程（Live Trace）
"""

import time

import streamlit as st
from ui.api_client import APIClient
from ui.styles import apply_global_styles
from ui.components.layout import render_page_header, render_section, render_empty_state
from app.tracing.formatters import format_trace_event_summary, format_duration_ms, sanitize_trace_payload

apply_global_styles()
render_page_header("Research", "创建研究任务、批量提交热点，并实时查看执行流程。")

client = APIClient()


# ============================================================
# Pure Functions (testable, no Streamlit dependency)
# ============================================================


def build_research_form_payload(
    topic: str,
    mode: str = "auto",
    depth: str = "standard",
    include_gossip: bool = False,
    include_books: bool = True,
    include_video: bool = False,
    obsidian_path: str = "",
) -> dict:
    """构建研究任务创建 payload。"""
    return {
        "topic": topic.strip(),
        "mode": mode,
        "depth": depth,
        "include_gossip": include_gossip,
        "include_books": include_books,
        "include_video": include_video,
        "obsidian_path": obsidian_path,
    }


def format_intent_preview(topic: str, mode: str, depth: str, **kwargs) -> dict:
    """格式化意图预览卡片数据。"""
    mode_labels = {
        "auto": "自动识别",
        "person": "人物研究",
        "company": "公司研究",
        "event": "事件研究",
        "concept": "概念研究",
    }
    depth_labels = {
        "shallow": "快速（~30 来源）",
        "standard": "标准（~60 来源）",
        "deep": "深度（~120 来源）",
    }
    return {
        "topic": topic,
        "mode_label": mode_labels.get(mode, mode),
        "depth_label": depth_labels.get(depth, depth),
        "auto_fetch": kwargs.get("auto_fetch", True),
        "auto_synthesize": kwargs.get("auto_synthesize", False),
        "auto_export": kwargs.get("auto_export", False),
    }


def should_show_live_trace(task_status: str) -> bool:
    """判断是否应显示实时 trace 面板。"""
    return task_status in ("running", "pending")


def group_queue_items(queue_data: dict) -> dict:
    """将队列数据分组为 running / queued / completed / failed。"""
    return {
        "running": queue_data.get("running"),
        "queued": queue_data.get("queued", []),
        "completed": queue_data.get("completed_recent", []),
        "failed": queue_data.get("failed_recent", []),
        "worker_running": queue_data.get("worker_running", False),
        "total_queued": queue_data.get("total_queued", 0),
    }


# === Trace 格式化 ===

_STEP_ZH_MAP = {
    "task_created": "任务已创建",
    "llm_plan_created": "AI 规划完成",
    "language_planning_finished": "语言规划完成",
    "llm_call_started": "调用 AI",
    "llm_call_finished": "AI 调用完成",
    "llm_call_failed": "AI 调用失败",
    "query_expansion_finished": "搜索词扩展完成",
    "search_provider_started": "搜索中",
    "search_provider_finished": "搜索完成",
    "search_provider_failed": "搜索失败",
    "dedupe_finished": "去重完成",
    "scoring_finished": "来源评分完成",
    "task_completed": "研究完成",
    "task_failed": "研究失败",
    "auto_fetch_started": "开始抓取正文",
    "auto_fetch_source_started": "抓取来源",
    "auto_fetch_source_finished": "来源抓取成功",
    "auto_fetch_source_failed": "来源抓取失败",
    "auto_fetch_finished": "抓取完成",
    "auto_analysis_started": "开始 AI 分析",
    "auto_analysis_finished": "AI 分析完成",
    "auto_export_started": "开始导出",
    "auto_export_finished": "导出完成",
    "auto_export_failed": "导出失败",
    "task_enqueued": "加入队列",
    "task_dequeued": "开始执行",
    "task_queue_completed": "队列任务完成",
    "task_queue_failed": "队列任务失败",
    "crawl_candidates_collected": "候选已收集",
    "crawl_candidate_review_started": "候选审查中",
    "crawl_candidate_review_finished": "候选审查完成",
    "crawlee_batch_started": "批量抓取开始",
    "crawlee_url_started": "抓取 URL",
    "crawlee_url_finished": "URL 抓取成功",
    "crawlee_url_failed": "URL 抓取失败",
    "crawlee_batch_finished": "批量抓取完成",
    "crawl_saved_document": "文档已保存",
}

STEP_LABELS = {
    "pending": "等待开始",
    "task_created": "任务已创建",
    "language_planning": "规划搜索语言",
    "query_expansion": "扩展搜索词",
    "search": "搜索资料",
    "dedupe": "去重",
    "scoring": "评估来源质量",
    "db_save": "保存结果",
    "auto_fetch": "抓取正文",
    "auto_analyze": "AI 分析",
    "auto_export": "导出到 Obsidian",
    "completed": "已完成",
    "failed": "失败",
}


def format_trace_event(event: dict) -> str:
    """格式化单条 trace 事件为紧凑显示文本。"""
    return format_trace_event_summary(event)


def build_live_progress_summary(task: dict, trace_summary: dict) -> dict:
    """构建实时进度摘要。"""
    return {
        "task_id": task.get("task_id", ""),
        "status": task.get("status", "pending"),
        "topic": task.get("topic", ""),
        "current_step": trace_summary.get("current_step", "pending"),
        "progress_percent": trace_summary.get("progress_percent", 0),
        "llm_calls": trace_summary.get("llm_calls", 0),
        "search_calls": trace_summary.get("search_calls", 0),
        "warning_count": trace_summary.get("warning_count", 0),
        "error_count": trace_summary.get("error_count", 0),
        "source_counts": trace_summary.get("source_counts", {}),
        "level_counts": trace_summary.get("level_counts", {}),
        "providers_used": trace_summary.get("providers_used", []),
        "duration_ms": trace_summary.get("duration_ms"),
    }


def summarize_completed_task(trace_summary: dict) -> dict:
    """构建完成任务的摘要信息。"""
    source_counts = trace_summary.get("source_counts", {})
    level_counts = trace_summary.get("level_counts", {})
    high_quality = level_counts.get("S", 0) + level_counts.get("A", 0)
    return {
        "total_sources": source_counts.get("deduped", 0),
        "high_quality": high_quality,
        "llm_calls": trace_summary.get("llm_calls", 0),
        "search_calls": trace_summary.get("search_calls", 0),
        "warning_count": trace_summary.get("warning_count", 0),
        "error_count": trace_summary.get("error_count", 0),
        "duration_ms": trace_summary.get("duration_ms"),
        "level_counts": level_counts,
    }


# ============================================================
# Obsidian Vault 状态（静默检测）
# ============================================================

obsidian_path = ""
vault_usable = False

try:
    obsidian_config = client.get_obsidian_settings()
    if obsidian_config.get("configured") and obsidian_config.get("exists") and obsidian_config.get("writable"):
        vault_usable = True
        obsidian_path = obsidian_config.get("vault_path", "")
except Exception:
    pass


# ============================================================
# 页面主体
# ============================================================

running_task_id = st.session_state.get("running_task_id")

# === 一、主操作区 ===

if not running_task_id:
    render_section("Start a Research Task")

    tab_simple, tab_advanced, tab_batch = st.tabs(["Simple Request", "Advanced Setup", "Batch Queue"])

    # --- Simple Request ---
    with tab_simple:
        topic_simple = st.text_area(
            "研究请求",
            placeholder="例如：请帮我研究 Tim Cook 的童年故事，包括家庭背景、成长环境、早期教育经历",
            height=100,
            key="simple_topic",
            label_visibility="collapsed",
        )

        col_start, col_space = st.columns([1, 3])
        with col_start:
            simple_submitted = st.button("Start Research", type="primary", key="btn_simple_start", use_container_width=True)

        if simple_submitted:
            if not topic_simple.strip():
                st.error("请输入研究主题")
            else:
                try:
                    payload = build_research_form_payload(
                        topic=topic_simple,
                        obsidian_path=obsidian_path,
                    )
                    result = client.create_task(payload)
                    task_id = result["task_id"]
                    client.run_research(task_id)
                    st.session_state["running_task_id"] = task_id
                    st.rerun()
                except Exception as e:
                    st.error(f"启动失败：{e}")

    # --- Advanced Setup ---
    with tab_advanced:
        with st.form("advanced_form"):
            adv_topic = st.text_input("研究主题", placeholder="例如：黄仁勋早期创业、OpenAI 宫斗")

            col1, col2, col3 = st.columns(3)
            with col1:
                adv_mode = st.selectbox("研究模式", ["auto", "person", "company", "event", "concept"])
            with col2:
                adv_depth = st.selectbox("搜索深度", ["shallow", "standard", "deep"], index=1)
            with col3:
                adv_lang = st.selectbox("输出语言", ["zh", "en"], index=0)

            st.markdown("**来源类型**")
            src_col1, src_col2, src_col3 = st.columns(3)
            with src_col1:
                adv_gossip = st.checkbox("八卦线索", value=False)
            with src_col2:
                adv_books = st.checkbox("图书资料", value=True)
            with src_col3:
                adv_video = st.checkbox("视频资料", value=False)

            st.markdown("**自动化流程**")
            auto_col1, auto_col2, auto_col3 = st.columns(3)
            with auto_col1:
                adv_fetch = st.checkbox("自动抓取 S/A/B 正文", value=True)
            with auto_col2:
                adv_synthesize = st.checkbox("自动合成研究文档", value=vault_usable, disabled=not vault_usable)
            with auto_col3:
                adv_export = st.checkbox("自动导出到 Obsidian", value=vault_usable, disabled=not vault_usable)

            with st.expander("Crawlee 深度抓取", expanded=False):
                cr_col1, cr_col2 = st.columns(2)
                with cr_col1:
                    adv_crawlee = st.checkbox("启用 Crawlee", value=False)
                    adv_crawl_depth = st.selectbox("候选深度", ["top30", "top50", "top100"])
                with cr_col2:
                    adv_crawl_pages = st.selectbox("最大页面数", [10, 30, 50, 100], index=1)
                    adv_crawl_mode = st.selectbox("抓取模式", ["adaptive", "http", "browser"])

            adv_submitted = st.form_submit_button("Start Research", type="primary")

        if adv_submitted:
            if not adv_topic.strip():
                st.error("请输入研究主题")
            else:
                try:
                    payload = build_research_form_payload(
                        topic=adv_topic,
                        mode=adv_mode,
                        depth=adv_depth,
                        include_gossip=adv_gossip,
                        include_books=adv_books,
                        include_video=adv_video,
                        obsidian_path=obsidian_path,
                    )
                    result = client.create_task(payload)
                    task_id = result["task_id"]
                    client.run_research(task_id)
                    st.session_state["running_task_id"] = task_id
                    st.rerun()
                except Exception as e:
                    st.error(f"启动失败：{e}")

    # --- Batch Queue ---
    with tab_batch:
        st.caption("每行一个主题，每个主题会作为独立任务进入队列。")
        with st.form("batch_form"):
            batch_topics = st.text_area(
                "批量主题",
                placeholder="OpenAI 新模型\n黄仁勋 Computex 演讲\nTesla Robotaxi\nTim Cook 童年故事",
                height=160,
                label_visibility="collapsed",
            )
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                batch_mode = st.selectbox("模式", ["auto", "person", "company", "event", "concept"], key="b_mode")
            with b_col2:
                batch_depth = st.selectbox("深度", ["shallow", "standard", "deep"], index=1, key="b_depth")

            batch_submitted = st.form_submit_button("Add to Queue", type="primary")

        if batch_submitted:
            topics = [t.strip() for t in batch_topics.strip().split("\n") if t.strip()]
            if not topics:
                st.error("请输入至少一个主题")
            else:
                try:
                    result = client.batch_create_and_enqueue(
                        topics=topics,
                        mode=batch_mode,
                        depth=batch_depth,
                        obsidian_path=obsidian_path,
                    )
                    st.success(f"✅ 已创建 {result.get('created', len(topics))} 个任务并加入队列")
                except Exception as e:
                    st.error(f"批量创建失败：{e}")

    # === 二、任务队列面板 ===

    try:
        queue_data = client.get_queue_status()
        groups = group_queue_items(queue_data)
        has_queue_activity = groups["running"] or groups["queued"] or groups["failed"]
    except Exception:
        has_queue_activity = False
        groups = {}

    if has_queue_activity:
        render_section("Task Queue")

        # Worker 状态
        if groups.get("worker_running"):
            st.caption("🟢 Worker 运行中")
        else:
            st.caption("🔴 Worker 未运行")

        # Running
        running = groups.get("running")
        if running:
            st.markdown(f"**⏳ Running** — `{running.get('task_id', '')[:8]}...`")

        # Queued
        queued = groups.get("queued", [])
        if queued:
            st.markdown(f"**🕐 Queued** ({len(queued)})")
            for item in queued[:5]:
                q_col1, q_col2 = st.columns([4, 1])
                with q_col1:
                    st.caption(f"`{item.get('task_id', '')[:8]}...` — 优先级 {item.get('priority', 100)}")
                with q_col2:
                    if st.button("取消", key=f"cancel_{item.get('task_id', '')}"):
                        try:
                            client.cancel_queued_task(item["task_id"])
                            st.rerun()
                        except Exception:
                            pass

        # Failed
        failed = groups.get("failed", [])
        if failed:
            st.markdown(f"**❌ Failed** ({len(failed)})")
            for item in failed[:3]:
                f_col1, f_col2 = st.columns([4, 1])
                with f_col1:
                    st.caption(f"`{item.get('task_id', '')[:8]}...` — {item.get('error_message', '')[:50]}")
                with f_col2:
                    if st.button("重试", key=f"retry_{item.get('task_id', '')}"):
                        try:
                            client.retry_queued_task(item["task_id"])
                            st.rerun()
                        except Exception:
                            pass

        # Completed
        completed = groups.get("completed", [])
        if completed:
            with st.expander(f"✅ Recently Completed ({len(completed)})", expanded=False):
                for item in completed[:5]:
                    st.caption(f"`{item.get('task_id', '')[:8]}...`")


# ============================================================
# 三、实时执行流程 (Live Research Trace)
# ============================================================

if running_task_id:
    render_section("Live Research Trace")

    # 获取任务状态
    try:
        task = client.get_task(running_task_id)
    except Exception as e:
        st.error(f"获取任务状态失败：{e}")
        st.session_state.pop("running_task_id", None)
        st.stop()

    task_status = task.get("status", "pending")

    # 获取 trace summary
    try:
        trace_summary = client.get_trace_summary(running_task_id)
    except Exception:
        trace_summary = {"total_events": 0, "current_step": "pending", "progress_percent": 0}

    progress = build_live_progress_summary(task, trace_summary)
    current_step_label = STEP_LABELS.get(progress["current_step"], progress["current_step"])

    # 状态行
    status_icon = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}.get(task_status, "❓")
    st.markdown(f"{status_icon} **{task.get('topic', '')}** — {current_step_label}")
    st.caption(f"Task ID: `{running_task_id}`")

    # 进度条
    progress_pct = progress["progress_percent"]
    st.progress(progress_pct / 100, text=f"{progress_pct}%")

    # 指标行
    m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
    m_col1.metric("LLM", progress["llm_calls"])
    m_col2.metric("搜索", progress["search_calls"])
    m_col3.metric("警告", progress["warning_count"])
    m_col4.metric("错误", progress["error_count"])
    duration = progress.get("duration_ms")
    m_col5.metric("耗时", f"{duration / 1000:.1f}s" if duration else "—")

    # 来源统计
    source_counts = progress.get("source_counts", {})
    level_counts = progress.get("level_counts", {})
    meta_parts = []
    if source_counts:
        meta_parts.append(f"来源: {source_counts.get('raw', 0)} → {source_counts.get('deduped', 0)}")
    if level_counts:
        meta_parts.append(" ".join(f"{k}={v}" for k, v in sorted(level_counts.items())))
    if progress.get("providers_used"):
        meta_parts.append(f"服务: {', '.join(progress['providers_used'])}")
    if meta_parts:
        st.caption(" · ".join(meta_parts))

    # 事件 Timeline
    try:
        trace_data = client.get_trace(running_task_id, limit=100)
        events = trace_data.get("events", [])
    except Exception:
        events = []

    if events:
        events_sorted = sorted(events, key=lambda e: e.get("created_at", ""), reverse=True)
        for event in events_sorted[:30]:
            st.markdown(format_trace_event(event))
            # Error details
            if event.get("error_message"):
                st.caption(f"　　{event['error_message'][:150]}")
    else:
        st.info("等待执行事件...")

    # === 任务完成 ===

    if task_status == "completed":
        st.divider()
        completed_summary = summarize_completed_task(trace_summary)

        c_col1, c_col2, c_col3, c_col4 = st.columns(4)
        c_col1.metric("来源总数", completed_summary["total_sources"])
        c_col2.metric("高质量 (S/A)", completed_summary["high_quality"])
        c_col3.metric("LLM 调用", completed_summary["llm_calls"])
        c_col4.metric("搜索调用", completed_summary["search_calls"])

        if completed_summary.get("duration_ms"):
            st.caption(f"总耗时: {completed_summary['duration_ms'] / 1000:.1f} 秒")

        st.session_state["last_task_id"] = running_task_id
        st.session_state["selected_task_id"] = running_task_id

        col_a, col_b = st.columns(2)
        with col_a:
            st.page_link("pages/2_Results.py", label="查看研究结果", icon="📊")
        with col_b:
            if st.button("新建研究", key="new_research_btn"):
                st.session_state.pop("running_task_id", None)
                st.rerun()

    elif task_status == "failed":
        st.divider()
        st.error("研究任务失败")

        error_events = [e for e in events if e.get("level") == "error"]
        if error_events:
            for err in error_events[-3:]:
                st.caption(f"❌ {err.get('step', '')} — {err.get('message', '')}")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("重新运行", key="retry_btn"):
                try:
                    client.run_research(running_task_id)
                    st.rerun()
                except Exception as e:
                    st.error(f"重新运行失败: {e}")
        with col_b:
            if st.button("新建研究", key="new_research_failed_btn"):
                st.session_state.pop("running_task_id", None)
                st.rerun()

    elif should_show_live_trace(task_status):
        # 任务仍在运行，自动刷新
        time.sleep(2)
        st.rerun()
