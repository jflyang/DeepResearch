"""产品化 Trace 面板组件 - 执行流程可视化。

使用 app/tracing/formatters.py 中的纯函数进行格式化。
"""

from __future__ import annotations

import streamlit as st
from app.tracing.formatters import (
    format_trace_event_summary,
    format_duration_ms,
    sanitize_trace_payload,
)


def render_trace_summary(trace_summary: dict):
    """渲染 Trace 顶部摘要指标。"""
    cols = st.columns(5)
    duration = trace_summary.get("duration_ms")
    cols[0].metric("耗时", format_duration_ms(duration))
    cols[1].metric("LLM", trace_summary.get("llm_calls", 0))
    cols[2].metric("搜索", trace_summary.get("search_calls", 0))
    cols[3].metric("警告", trace_summary.get("warning_count", 0))
    cols[4].metric("错误", trace_summary.get("error_count", 0))

    # 额外信息
    providers = trace_summary.get("providers_used", [])
    if providers:
        st.caption(f"服务: {', '.join(providers)}")

    source_counts = trace_summary.get("source_counts", {})
    if source_counts:
        st.caption(f"来源: {source_counts.get('raw', 0)} → {source_counts.get('deduped', 0)}")


def render_trace_timeline(events: list[dict], show_details: bool = False, max_items: int = 50):
    """渲染事件 Timeline。

    Args:
        events: trace 事件列表
        show_details: 是否默认展开详情
        max_items: 最大显示条数
    """
    if not events:
        st.caption("暂无事件记录")
        return

    for event in events[:max_items]:
        # 主行摘要
        summary = format_trace_event_summary(event)
        st.markdown(summary)

        # 详情折叠
        has_details = (
            event.get("input_summary")
            or event.get("output_summary")
            or event.get("metrics")
            or event.get("error_message")
        )
        if has_details:
            with st.expander("Details", expanded=show_details):
                if event.get("error_message"):
                    st.error(event["error_message"][:500])
                if event.get("output_summary"):
                    st.json(sanitize_trace_payload(event["output_summary"]))
                if event.get("input_summary"):
                    st.json(sanitize_trace_payload(event["input_summary"]))
                if event.get("metrics"):
                    st.json(sanitize_trace_payload(event["metrics"]))

    if len(events) > max_items:
        st.caption(f"显示前 {max_items} 条，共 {len(events)} 条")


def render_trace_panel(
    task_id: str,
    api_client,
    default_phase: str = "全部",
):
    """渲染完整 Trace 面板（摘要 + 筛选 + Timeline）。

    Args:
        task_id: 任务 ID
        api_client: APIClient 实例
        default_phase: 默认阶段筛选
    """
    # 摘要
    try:
        summary = api_client.get_trace_summary(task_id)
    except Exception:
        summary = {}

    if summary.get("total_events", 0) == 0:
        st.caption("暂无执行轨迹数据")
        return

    render_trace_summary(summary)

    st.markdown("---")

    # 筛选
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        phase = st.selectbox(
            "阶段",
            ["全部", "planning", "llm", "search", "processing", "storage", "extraction", "crawling", "export"],
            key=f"trace_phase_{task_id}",
        )
    with f_col2:
        level = st.selectbox(
            "级别",
            ["全部", "info", "warning", "error"],
            key=f"trace_level_{task_id}",
        )
    with f_col3:
        show_raw = st.checkbox("显示详情", value=False, key=f"trace_raw_{task_id}")

    # 加载事件
    try:
        params = {}
        if phase != "全部":
            params["phase"] = phase
        if level != "全部":
            params["level"] = level
        trace_data = api_client.get_trace(task_id, **params)
        events = trace_data.get("events", [])
    except Exception:
        events = []

    # Timeline
    render_trace_timeline(events, show_details=show_raw)


# === Backward-compatible exports ===

STEP_ZH_MAP = {
    "task_created": "任务已创建",
    "llm_call_finished": "AI 调用完成",
    "search_provider_finished": "搜索完成",
    "task_completed": "研究完成",
    "task_failed": "研究失败",
}

render_timeline_event = lambda event: st.markdown(format_trace_event_summary(event))
render_timeline = render_trace_timeline
