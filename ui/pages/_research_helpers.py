"""Research 页面纯函数 - 可独立测试，不依赖 Streamlit。"""

from __future__ import annotations


# ============================================================
# Form Payload
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


# ============================================================
# Intent Preview
# ============================================================


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


# ============================================================
# Live Trace
# ============================================================


def should_show_live_trace(task_status: str) -> bool:
    """判断是否应显示实时 trace 面板。"""
    return task_status in ("running", "pending")


# ============================================================
# Queue Grouping
# ============================================================


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


# ============================================================
# Trace Formatting
# ============================================================

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


def format_trace_event(event: dict) -> str:
    """格式化单条 trace 事件为紧凑显示文本。"""
    step = event.get("step", "unknown")
    level = event.get("level", "info")
    message = event.get("message", "")
    duration = event.get("duration_ms")
    provider = event.get("provider")

    if level == "error" or "failed" in step:
        icon = "❌"
    elif level == "warning":
        icon = "⚠️"
    elif "llm_call" in step:
        icon = "🤖"
    elif "search" in step:
        icon = "🔎"
    elif "export" in step:
        icon = "📤"
    else:
        icon = "✅"

    step_zh = _STEP_ZH_MAP.get(step, step)
    parts = [f"{icon} **{step_zh}**"]
    if message:
        parts.append(f"— {message}")
    if duration:
        parts.append(f"({duration}ms)")
    if provider:
        parts.append(f"[{provider}]")
    return " ".join(parts)


# ============================================================
# Progress Summary
# ============================================================


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
