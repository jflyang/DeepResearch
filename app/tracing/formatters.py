"""Trace 事件格式化 - 将原始 trace 事件转为产品化可读摘要。

纯函数，不依赖 Streamlit。供 UI 层调用。
"""

from __future__ import annotations

import re
from typing import Any


# ============================================================
# 脱敏规则
# ============================================================

_SENSITIVE_KEYS = frozenset({
    "api_key", "authorization", "access_token", "refresh_token",
    "secret", "password", "private_key", "cookie",
    "api-key", "x-api-key", "bearer",
})

_SAFE_KEYS = frozenset({
    "max_output_tokens", "input_tokens", "output_tokens", "token_count",
    "max_input_chars", "input_chars", "output_chars", "temperature",
    "timeout_seconds", "duration_ms", "result_count", "count",
})


def sanitize_trace_payload(payload: Any) -> Any:
    """递归脱敏 trace payload，隐藏敏感字段。

    保留：max_output_tokens, input_tokens 等数值字段。
    脱敏：api_key, authorization, secret 等。
    """
    if payload is None:
        return None
    if isinstance(payload, dict):
        result = {}
        for key, value in payload.items():
            key_lower = key.lower().replace("-", "_")
            if key_lower in _SENSITIVE_KEYS:
                result[key] = "***REDACTED***"
            elif isinstance(value, (dict, list)):
                result[key] = sanitize_trace_payload(value)
            else:
                result[key] = value
        return result
    if isinstance(payload, list):
        return [sanitize_trace_payload(item) for item in payload]
    return payload


# ============================================================
# Duration Formatting
# ============================================================


def format_duration_ms(ms: int | float | None) -> str:
    """格式化毫秒为可读时间。

    Examples:
        450 → "0.45s"
        2300 → "2.30s"
        65000 → "1m 5s"
    """
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    remaining = int(seconds % 60)
    return f"{minutes}m {remaining}s"


def format_count(n: int | None) -> str:
    """格式化数量。"""
    if n is None:
        return "—"
    return str(n)


# ============================================================
# Event Icon
# ============================================================

_STEP_ICON_MAP = {
    # Planning
    "task_created": "📋",
    "topic_understanding_started": "🧠",
    "topic_understanding_finished": "🧠",
    "language_planning_started": "🌐",
    "language_planning_finished": "🌐",
    "query_expansion_started": "📝",
    "query_expansion_finished": "📝",
    # LLM
    "llm_call_started": "🤖",
    "llm_call_finished": "🤖",
    "llm_call_failed": "🤖",
    # Search
    "search_started": "🔎",
    "search_provider_started": "🔎",
    "search_provider_finished": "🔎",
    "search_provider_failed": "🔎",
    # Processing
    "dedupe_started": "🔄",
    "dedupe_finished": "🔄",
    "scoring_started": "⭐",
    "scoring_finished": "⭐",
    "classification_started": "📂",
    "classification_finished": "📂",
    # Storage
    "db_save_started": "💾",
    "db_save_finished": "💾",
    # Extraction
    "extraction_started": "📥",
    "extraction_finished": "📥",
    "extraction_failed": "📥",
    # Crawling
    "crawl_candidates_collected": "🌐",
    "crawl_candidate_review_started": "🌐",
    "crawl_candidate_review_finished": "🌐",
    "crawlee_batch_started": "🕷️",
    "crawlee_url_started": "🕷️",
    "crawlee_url_finished": "🕷️",
    "crawlee_url_failed": "🕷️",
    "crawlee_batch_finished": "🕷️",
    "crawl_saved_document": "💾",
    # Export
    "export_started": "📤",
    "export_finished": "📤",
    "export_failed": "📤",
    "crawl_auto_export_started": "📤",
    "crawl_auto_export_finished": "📤",
    # Completion
    "task_completed": "✅",
    "task_failed": "❌",
}


def get_trace_event_icon(event: dict) -> str:
    """获取事件图标。"""
    step = event.get("step", "")
    level = event.get("level", "info")

    if level == "error":
        return "❌"
    if level == "warning":
        return "⚠️"

    return _STEP_ICON_MAP.get(step, "●")


# ============================================================
# Event Title
# ============================================================

_STEP_TITLE_MAP = {
    "task_created": "任务已创建",
    "topic_understanding_started": "主题理解中",
    "topic_understanding_finished": "主题理解完成",
    "language_planning_started": "语言规划中",
    "language_planning_finished": "语言规划完成",
    "query_expansion_started": "搜索词扩展中",
    "query_expansion_finished": "搜索词扩展完成",
    "llm_call_started": "LLM 调用中",
    "llm_call_finished": "LLM 调用完成",
    "llm_call_failed": "LLM 调用失败",
    "search_started": "搜索开始",
    "search_provider_started": "搜索中",
    "search_provider_finished": "搜索完成",
    "search_provider_failed": "搜索失败",
    "dedupe_started": "去重中",
    "dedupe_finished": "去重完成",
    "scoring_started": "评分中",
    "scoring_finished": "评分完成",
    "classification_started": "分类中",
    "classification_finished": "分类完成",
    "db_save_started": "保存中",
    "db_save_finished": "保存完成",
    "extraction_started": "正文提取中",
    "extraction_finished": "正文提取完成",
    "extraction_failed": "正文提取失败",
    "export_started": "导出中",
    "export_finished": "导出完成",
    "export_failed": "导出失败",
    "task_completed": "研究完成",
    "task_failed": "研究失败",
    "crawl_candidates_collected": "候选 URL 已收集",
    "crawl_candidate_review_started": "候选审查中",
    "crawl_candidate_review_finished": "候选审查完成",
    "crawl_candidate_skipped": "候选已跳过",
    "crawlee_batch_started": "批量抓取开始",
    "crawlee_url_started": "抓取 URL",
    "crawlee_url_finished": "URL 抓取完成",
    "crawlee_url_failed": "URL 抓取失败",
    "crawlee_batch_finished": "批量抓取完成",
    "crawl_saved_document": "文档已保存",
    "crawl_auto_export_started": "抓取结果导出中",
    "crawl_auto_export_finished": "抓取结果导出完成",
}


def get_trace_event_title(event: dict) -> str:
    """获取事件标题（中文可读）。"""
    step = event.get("step", "unknown")
    return _STEP_TITLE_MAP.get(step, step)


# ============================================================
# Event Summary (产品化摘要)
# ============================================================


def format_trace_event_summary(event: dict) -> str:
    """格式化单条 trace 事件为产品化可读摘要。

    Returns:
        Markdown 格式的单行摘要
    """
    icon = get_trace_event_icon(event)
    title = get_trace_event_title(event)
    step = event.get("step", "")
    message = event.get("message", "")
    duration = event.get("duration_ms")
    provider = event.get("provider")
    model = event.get("model")

    # 构建主行
    parts = [f"{icon} **{title}**"]

    # 根据事件类型添加上下文信息
    if "llm_call" in step:
        detail_parts = []
        if provider:
            detail_parts.append(provider)
        if model:
            detail_parts.append(model)
        if duration:
            detail_parts.append(format_duration_ms(duration))
        # 从 output_summary 提取 task_name
        out = event.get("output_summary") or event.get("input_summary") or {}
        task_name = out.get("task_name", "")
        if task_name:
            detail_parts.insert(0, task_name)
        if detail_parts:
            parts.append(f"— {' / '.join(detail_parts)}")

    elif "search_provider" in step:
        detail_parts = []
        if provider:
            detail_parts.append(provider)
        out = event.get("output_summary") or {}
        count = out.get("result_count") or out.get("count")
        if count is not None:
            detail_parts.append(f"{count} 条结果")
        if duration:
            detail_parts.append(format_duration_ms(duration))
        if detail_parts:
            parts.append(f"— {' / '.join(detail_parts)}")
        elif message:
            parts.append(f"— {message}")

    elif "crawlee_url" in step:
        if message:
            parts.append(f"— {message[:80]}")
        if duration:
            parts.append(f"({format_duration_ms(duration)})")

    elif step in ("task_completed", "task_failed"):
        if duration:
            parts.append(f"— 总耗时 {format_duration_ms(duration)}")

    elif message:
        parts.append(f"— {message[:100]}")

    if duration and "llm_call" not in step and "search_provider" not in step and step not in ("task_completed", "task_failed") and "crawlee" not in step:
        parts.append(f"({format_duration_ms(duration)})")

    return " ".join(parts)
