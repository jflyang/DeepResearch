"""Research 页面实时进度 UI 逻辑测试。

抽取纯函数进行测试，不依赖 Streamlit 运行时。
"""

import pytest
import sys
from pathlib import Path

# 将 ui 目录加入 path 以便导入页面中的纯函数
sys.path.insert(0, str(Path(__file__).parent.parent))


# === 从页面中提取的纯函数（复制以便独立测试） ===


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


# === 测试 ===


class TestShouldContinuePolling:
    """轮询控制测试。"""

    def test_running_should_poll(self):
        assert should_continue_polling("running") is True

    def test_pending_should_poll(self):
        assert should_continue_polling("pending") is True

    def test_completed_should_stop(self):
        assert should_continue_polling("completed") is False

    def test_failed_should_stop(self):
        assert should_continue_polling("failed") is False


class TestGetEventIcon:
    """事件 icon 映射测试。"""

    def test_llm_event(self):
        assert get_event_icon({"step": "llm_call_finished", "level": "info"}) == "🤖"

    def test_llm_started(self):
        assert get_event_icon({"step": "llm_call_started", "level": "info"}) == "🤖"

    def test_search_event(self):
        assert get_event_icon({"step": "search_provider_finished", "level": "info"}) == "🔎"

    def test_warning_event(self):
        assert get_event_icon({"step": "some_step", "level": "warning"}) == "⚠️"

    def test_error_event(self):
        assert get_event_icon({"step": "some_step", "level": "error"}) == "❌"

    def test_failed_step(self):
        assert get_event_icon({"step": "search_provider_failed", "level": "info"}) == "❌"

    def test_started_step(self):
        assert get_event_icon({"step": "scoring_started", "level": "info"}) == "🔄"

    def test_finished_step(self):
        assert get_event_icon({"step": "scoring_finished", "level": "info"}) == "✅"

    def test_db_save(self):
        assert get_event_icon({"step": "db_save_started", "level": "info"}) == "🗄️"

    def test_export(self):
        assert get_event_icon({"step": "export_started", "level": "info"}) == "📤"


class TestFormatTraceEvent:
    """事件格式化测试。"""

    def test_basic_event(self):
        event = {"step": "task_created", "level": "info", "message": "Task created"}
        result = format_trace_event(event)
        assert "✅" in result
        assert "task_created" in result
        assert "Task created" in result

    def test_event_with_duration(self):
        event = {"step": "llm_call_finished", "level": "info", "message": "Done", "duration_ms": 2100}
        result = format_trace_event(event)
        assert "2100ms" in result

    def test_event_with_provider(self):
        event = {"step": "search_provider_finished", "level": "info", "message": "", "provider": "tavily"}
        result = format_trace_event(event)
        assert "[tavily]" in result

    def test_error_event(self):
        event = {"step": "task_failed", "level": "error", "message": "Timeout"}
        result = format_trace_event(event)
        assert "❌" in result


class TestBuildLiveProgressSummary:
    """实时进度摘要构建测试。"""

    def test_basic_summary(self):
        task = {"task_id": "t1", "status": "running", "topic": "Test"}
        trace = {
            "current_step": "search",
            "progress_percent": 45,
            "llm_calls": 2,
            "search_calls": 5,
            "warning_count": 1,
            "error_count": 0,
        }
        result = build_live_progress_summary(task, trace)
        assert result["task_id"] == "t1"
        assert result["status"] == "running"
        assert result["current_step"] == "search"
        assert result["progress_percent"] == 45
        assert result["llm_calls"] == 2

    def test_empty_trace(self):
        task = {"task_id": "t2", "status": "pending", "topic": "Test"}
        trace = {}
        result = build_live_progress_summary(task, trace)
        assert result["progress_percent"] == 0
        assert result["current_step"] == "pending"


class TestSummarizeCompletedTask:
    """完成任务摘要测试。"""

    def test_completed_summary(self):
        trace = {
            "source_counts": {"raw": 47, "deduped": 31},
            "level_counts": {"S": 2, "A": 6, "B": 15, "C": 7, "D": 1},
            "llm_calls": 3,
            "search_calls": 12,
            "warning_count": 1,
            "error_count": 0,
            "duration_ms": 15000,
        }
        result = summarize_completed_task(trace)
        assert result["total_sources"] == 31
        assert result["high_quality"] == 8  # S=2 + A=6
        assert result["llm_calls"] == 3
        assert result["duration_ms"] == 15000

    def test_empty_summary(self):
        result = summarize_completed_task({})
        assert result["total_sources"] == 0
        assert result["high_quality"] == 0


class TestPageFileIntegrity:
    """页面文件完整性测试。"""

    def test_page_has_live_progress(self):
        content = Path("ui/pages/1_Research.py").read_text(encoding="utf-8")
        assert "实时研究流程" in content

    def test_page_has_progress_bar(self):
        content = Path("ui/pages/1_Research.py").read_text(encoding="utf-8")
        assert "st.progress" in content

    def test_page_has_auto_refresh(self):
        content = Path("ui/pages/1_Research.py").read_text(encoding="utf-8")
        assert "st.rerun()" in content

    def test_page_has_trace_api_call(self):
        content = Path("ui/pages/1_Research.py").read_text(encoding="utf-8")
        assert "get_trace_summary" in content
        assert "get_trace" in content

    def test_page_has_results_link(self):
        content = Path("ui/pages/1_Research.py").read_text(encoding="utf-8")
        assert "3_Results" in content

    def test_page_no_api_key_display(self):
        """不应显示 API key。"""
        content = Path("ui/pages/1_Research.py").read_text(encoding="utf-8")
        assert "api_key" not in content.lower()
        assert "token" not in content.lower() or "token" in "input_chars"  # token 只在无关上下文
