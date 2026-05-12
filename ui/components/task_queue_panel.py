"""任务队列面板组件 - 在 Research 和 Results 页面显示队列状态。"""

from __future__ import annotations

from datetime import datetime


def build_queue_panel_state(queue_data: dict) -> dict:
    """
    构建队列面板显示状态。

    Args:
        queue_data: 从 GET /tasks/queue 返回的数据

    Returns:
        结构化的面板状态
    """
    running = queue_data.get("running")
    queued = queue_data.get("queued", [])
    completed = queue_data.get("completed_recent", [])
    failed = queue_data.get("failed_recent", [])
    worker_running = queue_data.get("worker_running", False)

    return {
        "has_activity": bool(running or queued or completed or failed),
        "worker_running": worker_running,
        "running_task": _format_running_task(running) if running else None,
        "queued_tasks": [_format_queued_task(item) for item in queued],
        "completed_tasks": [_format_completed_task(item) for item in completed],
        "failed_tasks": [_format_failed_task(item) for item in failed],
        "total_queued": queue_data.get("total_queued", 0),
        "total_completed": queue_data.get("total_completed", 0),
        "total_failed": queue_data.get("total_failed", 0),
    }


def _format_running_task(item: dict) -> dict:
    """格式化正在运行的任务。"""
    return {
        "task_id": item.get("task_id", ""),
        "status": "running",
        "started_at": item.get("started_at", ""),
        "show_details_button": True,
    }


def _format_queued_task(item: dict) -> dict:
    """格式化排队中的任务。"""
    return {
        "task_id": item.get("task_id", ""),
        "priority": item.get("priority", 100),
        "created_at": item.get("created_at", ""),
        "show_cancel_button": True,
    }


def _format_completed_task(item: dict) -> dict:
    """格式化已完成的任务。"""
    return {
        "task_id": item.get("task_id", ""),
        "completed_at": item.get("completed_at", ""),
        "show_results_button": True,
    }


def _format_failed_task(item: dict) -> dict:
    """格式化失败的任务。"""
    return {
        "task_id": item.get("task_id", ""),
        "error_message": item.get("error_message", ""),
        "completed_at": item.get("completed_at", ""),
        "show_retry_button": True,
    }


def render_queue_panel(st, queue_data: dict, api_client=None) -> None:
    """
    渲染任务队列面板（Streamlit 组件）。

    Args:
        st: streamlit 模块
        queue_data: 从 GET /tasks/queue 返回的数据
        api_client: APIClient 实例（用于操作按钮）
    """
    state = build_queue_panel_state(queue_data)

    if not state["has_activity"]:
        return

    st.markdown("---")
    st.markdown("### 📋 任务队列")

    # Worker 状态
    if state["worker_running"]:
        st.caption("🟢 Worker 运行中")
    else:
        st.caption("🔴 Worker 未运行")

    # 当前执行
    running = state["running_task"]
    if running:
        st.markdown("**⏳ 当前执行：**")
        st.markdown(f"- 任务 ID: `{running['task_id']}`")
        if running.get("started_at"):
            st.caption(f"  开始时间: {running['started_at']}")

    # 等待队列
    queued = state["queued_tasks"]
    if queued:
        st.markdown(f"**🕐 等待队列 ({len(queued)})：**")
        for item in queued[:5]:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"- `{item['task_id'][:8]}...` (优先级: {item['priority']})")
            with col2:
                if api_client and item.get("show_cancel_button"):
                    if st.button("取消", key=f"cancel_{item['task_id']}"):
                        try:
                            api_client.cancel_queued_task(item["task_id"])
                            st.rerun()
                        except Exception:
                            pass

    # 最近完成
    completed = state["completed_tasks"]
    if completed:
        st.markdown(f"**✅ 最近完成 ({state['total_completed']})：**")
        for item in completed[:3]:
            st.markdown(f"- `{item['task_id'][:8]}...`")

    # 失败任务
    failed = state["failed_tasks"]
    if failed:
        st.markdown(f"**❌ 失败 ({state['total_failed']})：**")
        for item in failed[:3]:
            col1, col2 = st.columns([4, 1])
            with col1:
                error = item.get("error_message", "")[:50]
                st.markdown(f"- `{item['task_id'][:8]}...` — {error}")
            with col2:
                if api_client and item.get("show_retry_button"):
                    if st.button("重试", key=f"retry_{item['task_id']}"):
                        try:
                            api_client.retry_queued_task(item["task_id"])
                            st.rerun()
                        except Exception:
                            pass
