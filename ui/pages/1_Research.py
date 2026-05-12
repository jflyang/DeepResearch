"""研究任务页面 - 创建并运行研究任务，实时显示执行流程。"""

import time

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
        st.warning(f"📁 **Obsidian Vault**　⚠️ 默认 Vault 路径无效：路径不存在 — `{vault_path_setting}`　[前往 Settings 修复](/9_Settings)")
    elif configured and not writable:
        st.warning(f"📁 **Obsidian Vault**　⚠️ 默认 Vault 路径无效：路径不可写 — `{vault_path_setting}`　[前往 Settings 修复](/9_Settings)")
    else:
        st.info("📁 **Obsidian Vault**　⚠️ 未配置默认 Vault。研究可以运行，但 Markdown/Obsidian 导出功能不可用。请到 [Settings](/9_Settings) 配置。")
except Exception:
    st.info("📁 **Obsidian Vault**　⚠️ 无法获取 Vault 配置（后端未连接？）。研究仍可运行，但导出不可用。")

st.divider()


# === Helper: 事件格式化 ===


def get_event_icon(event: dict) -> str:
    """根据事件类型返回 icon。"""
    step = event.get("step", "")
    level = event.get("level", "info")

    if level == "error" or "failed" in step:
        return "❌"
    if level == "warning":
        return "⚠️"
    if "llm_call" in step:
        return "🤖"
    if "search" in step:
        return "🔎"
    if "export" in step:
        return "📤"
    if "db_save" in step:
        return "🗄️"
    if "started" in step:
        return "🔄"
    return "✅"


def format_trace_event(event: dict) -> str:
    """格式化单条 trace 事件为显示文本。"""
    icon = get_event_icon(event)
    step = event.get("step", "unknown")
    message = event.get("message", "")
    duration = event.get("duration_ms")
    provider = event.get("provider")

    parts = [f"{icon} **{step}**"]
    if message:
        parts.append(f"— {message}")
    if duration:
        parts.append(f"({duration}ms)")
    if provider:
        parts.append(f"[{provider}]")

    return " ".join(parts)


def should_continue_polling(task_status: str) -> bool:
    """判断是否应继续轮询。"""
    return task_status in ("running", "pending")


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


# === 步骤标签映射 ===

STEP_LABELS = {
    "pending": "等待开始",
    "task_created": "任务已创建",
    "language_planning": "语言规划",
    "query_expansion": "Query 扩展",
    "search": "搜索中",
    "dedupe": "去重",
    "scoring": "来源评分",
    "db_save": "保存数据库",
    "completed": "已完成",
    "failed": "失败",
}


# === 输入表单 ===

# 如果有正在运行的任务，不显示表单
running_task_id = st.session_state.get("running_task_id")

if not running_task_id:
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
            except Exception as e:
                st.error(f"创建任务失败：{e}")
                st.stop()

            # 启动研究（后台执行）
            try:
                run_result = client.run_research(task_id)
                st.session_state["running_task_id"] = task_id
                st.rerun()
            except Exception as e:
                st.error(f"启动研究失败：{e}")
                st.stop()

# === 实时研究流程面板 ===

if running_task_id:
    st.divider()
    st.subheader("🧭 实时研究流程")

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

    # === 状态卡片 ===

    status_icon = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}.get(task_status, "❓")
    current_step_label = STEP_LABELS.get(progress["current_step"], progress["current_step"])

    st.markdown(f"**任务 ID**: `{running_task_id}`")
    st.markdown(f"**主题**: {task.get('topic', '')}")
    st.markdown(f"**状态**: {status_icon} {task_status}　|　**当前步骤**: {current_step_label}")

    # 进度条
    progress_pct = progress["progress_percent"]
    st.progress(progress_pct / 100, text=f"{progress_pct}% — {current_step_label}")

    # 指标卡片
    m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
    m_col1.metric("🤖 LLM", progress["llm_calls"])
    m_col2.metric("🔎 搜索", progress["search_calls"])
    m_col3.metric("⚠️ 警告", progress["warning_count"])
    m_col4.metric("❌ 错误", progress["error_count"])
    duration = progress.get("duration_ms")
    m_col5.metric("⏱️ 耗时", f"{duration / 1000:.1f}s" if duration else "—")

    # 来源统计（如果有）
    source_counts = progress.get("source_counts", {})
    level_counts = progress.get("level_counts", {})
    if source_counts:
        st.caption(f"来源: 原始 {source_counts.get('raw', 0)} → 去重后 {source_counts.get('deduped', 0)}")
    if level_counts:
        parts = [f"{k}={v}" for k, v in sorted(level_counts.items())]
        st.caption(f"等级分布: {', '.join(parts)}")
    if progress.get("providers_used"):
        st.caption(f"使用的服务: {', '.join(progress['providers_used'])}")

    st.divider()

    # === 事件时间线 ===

    st.markdown("### 📋 执行事件流")

    try:
        trace_data = client.get_trace(running_task_id, limit=100)
        events = trace_data.get("events", [])
    except Exception:
        events = []

    if events:
        # 按时间从新到旧显示
        events_sorted = sorted(events, key=lambda e: e.get("created_at", ""), reverse=True)

        for event in events_sorted[:50]:
            line = format_trace_event(event)
            st.markdown(line)

            # LLM 调用详情
            step = event.get("step", "")
            if "llm_call" in step and event.get("output_summary"):
                out = event["output_summary"]
                details = []
                if out.get("task_name"):
                    details.append(f"task: {out['task_name']}")
                if event.get("provider"):
                    details.append(f"provider: {event['provider']}")
                if event.get("model"):
                    details.append(f"model: {event['model']}")
                if out.get("input_chars"):
                    details.append(f"input: {out['input_chars']} chars")
                if out.get("output_chars"):
                    details.append(f"output: {out['output_chars']} chars")
                if details:
                    st.caption("　　" + " | ".join(details))

            # 搜索 Provider 详情
            elif "search_provider" in step and event.get("output_summary"):
                out = event["output_summary"]
                details = []
                if event.get("provider"):
                    details.append(f"provider: {event['provider']}")
                if out.get("result_count") is not None:
                    details.append(f"返回: {out['result_count']} 条")
                elif out.get("count") is not None:
                    details.append(f"返回: {out['count']} 条")
                if details:
                    st.caption("　　" + " | ".join(details))

            # 错误详情
            elif event.get("error_message"):
                st.caption(f"　　💬 {event['error_message'][:200]}")

    else:
        st.info("等待执行事件...")

    # === 任务完成/失败处理 ===

    if task_status == "completed":
        st.divider()
        st.subheader("✅ 研究完成")

        completed_summary = summarize_completed_task(trace_summary)

        c_col1, c_col2, c_col3, c_col4 = st.columns(4)
        c_col1.metric("来源总数", completed_summary["total_sources"])
        c_col2.metric("高质量来源 (S/A)", completed_summary["high_quality"])
        c_col3.metric("LLM 调用", completed_summary["llm_calls"])
        c_col4.metric("搜索调用", completed_summary["search_calls"])

        if completed_summary.get("duration_ms"):
            st.caption(f"总耗时: {completed_summary['duration_ms'] / 1000:.1f} 秒")

        st.markdown("""
**下一步：**
- 前往 **Results** 页面查看详细结果、筛选来源、提取正文
- 在 Results 页面可以导出研究索引到 Obsidian Vault
""")

        st.session_state["last_task_id"] = running_task_id
        st.session_state["selected_task_id"] = running_task_id

        col_a, col_b = st.columns(2)
        with col_a:
            st.page_link("pages/3_Results.py", label="📊 查看研究结果", icon="📊")
        with col_b:
            if st.button("🆕 新建研究", key="new_research_btn"):
                st.session_state.pop("running_task_id", None)
                st.rerun()

    elif task_status == "failed":
        st.divider()
        st.subheader("❌ 研究失败")

        # 显示最后几条错误
        error_events = [e for e in events if e.get("level") == "error"]
        if error_events:
            for err in error_events[-5:]:
                st.error(f"**{err.get('step', '')}** — {err.get('message', '')}")
                if err.get("error_message"):
                    st.caption(err["error_message"][:300])

        error_msg = task.get("error_message", "")
        if error_msg:
            st.error(f"错误信息: {error_msg[:300]}")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔄 重新运行", key="retry_btn"):
                try:
                    client.run_research(running_task_id)
                    st.rerun()
                except Exception as e:
                    st.error(f"重新运行失败: {e}")
        with col_b:
            if st.button("🆕 新建研究", key="new_research_failed_btn"):
                st.session_state.pop("running_task_id", None)
                st.rerun()

    else:
        # 任务仍在运行，自动刷新
        time.sleep(2)
        st.rerun()
