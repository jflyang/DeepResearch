"""Research 页面纯函数逻辑测试。"""

import sys
sys.path.insert(0, ".")

from ui.pages import _research_helpers as rh


class TestBuildResearchFormPayload:
    def test_basic_payload(self):
        payload = rh.build_research_form_payload("Tim Cook 童年")
        assert payload["topic"] == "Tim Cook 童年"
        assert payload["mode"] == "auto"
        assert payload["depth"] == "standard"
        assert payload["include_gossip"] is False
        assert payload["include_books"] is True

    def test_custom_options(self):
        payload = rh.build_research_form_payload(
            "OpenAI 宫斗",
            mode="event",
            depth="deep",
            include_gossip=True,
            include_books=False,
        )
        assert payload["topic"] == "OpenAI 宫斗"
        assert payload["mode"] == "event"
        assert payload["depth"] == "deep"
        assert payload["include_gossip"] is True
        assert payload["include_books"] is False

    def test_strips_whitespace(self):
        payload = rh.build_research_form_payload("  hello world  ")
        assert payload["topic"] == "hello world"

    def test_obsidian_path(self):
        payload = rh.build_research_form_payload("test", obsidian_path="/vault")
        assert payload["obsidian_path"] == "/vault"


class TestFormatIntentPreview:
    def test_basic_preview(self):
        preview = rh.format_intent_preview("Tim Cook", "person", "standard")
        assert preview["topic"] == "Tim Cook"
        assert preview["mode_label"] == "人物研究"
        assert preview["depth_label"] == "标准（~60 来源）"

    def test_auto_mode(self):
        preview = rh.format_intent_preview("test", "auto", "shallow")
        assert preview["mode_label"] == "自动识别"
        assert preview["depth_label"] == "快速（~30 来源）"

    def test_deep_depth(self):
        preview = rh.format_intent_preview("test", "auto", "deep")
        assert preview["depth_label"] == "深度（~120 来源）"

    def test_auto_flags(self):
        preview = rh.format_intent_preview("test", "auto", "standard", auto_fetch=True, auto_synthesize=True)
        assert preview["auto_fetch"] is True
        assert preview["auto_synthesize"] is True


class TestShouldShowLiveTrace:
    def test_running(self):
        assert rh.should_show_live_trace("running") is True

    def test_pending(self):
        assert rh.should_show_live_trace("pending") is True

    def test_completed(self):
        assert rh.should_show_live_trace("completed") is False

    def test_failed(self):
        assert rh.should_show_live_trace("failed") is False

    def test_empty(self):
        assert rh.should_show_live_trace("") is False


class TestGroupQueueItems:
    def test_empty_queue(self):
        groups = rh.group_queue_items({})
        assert groups["running"] is None
        assert groups["queued"] == []
        assert groups["completed"] == []
        assert groups["failed"] == []

    def test_with_data(self):
        data = {
            "running": {"task_id": "abc"},
            "queued": [{"task_id": "def"}],
            "completed_recent": [{"task_id": "ghi"}],
            "failed_recent": [{"task_id": "jkl", "error_message": "timeout"}],
            "worker_running": True,
            "total_queued": 1,
        }
        groups = rh.group_queue_items(data)
        assert groups["running"]["task_id"] == "abc"
        assert len(groups["queued"]) == 1
        assert len(groups["completed"]) == 1
        assert len(groups["failed"]) == 1
        assert groups["worker_running"] is True


class TestFormatTraceEvent:
    def test_basic_event(self):
        event = {"step": "task_created", "level": "info", "message": ""}
        result = rh.format_trace_event(event)
        assert "任务已创建" in result
        assert "✅" in result

    def test_error_event(self):
        event = {"step": "task_failed", "level": "error", "message": "timeout"}
        result = rh.format_trace_event(event)
        assert "❌" in result
        assert "研究失败" in result

    def test_llm_event(self):
        event = {"step": "llm_call_finished", "level": "info", "message": "", "provider": "deepseek", "duration_ms": 2300}
        result = rh.format_trace_event(event)
        assert "🤖" in result
        assert "deepseek" in result
        assert "2300ms" in result

    def test_search_event(self):
        event = {"step": "search_provider_finished", "level": "info", "message": "18 results"}
        result = rh.format_trace_event(event)
        assert "🔎" in result


class TestBuildLiveProgressSummary:
    def test_basic(self):
        task = {"task_id": "abc", "status": "running", "topic": "test"}
        trace = {"current_step": "search", "progress_percent": 40, "llm_calls": 2, "search_calls": 3}
        result = rh.build_live_progress_summary(task, trace)
        assert result["status"] == "running"
        assert result["progress_percent"] == 40
        assert result["llm_calls"] == 2

    def test_empty_trace(self):
        task = {"task_id": "abc", "status": "pending"}
        result = rh.build_live_progress_summary(task, {})
        assert result["progress_percent"] == 0
        assert result["current_step"] == "pending"


class TestSummarizeCompletedTask:
    def test_basic(self):
        trace = {
            "source_counts": {"raw": 100, "deduped": 60},
            "level_counts": {"S": 3, "A": 7, "B": 20, "C": 25, "D": 5},
            "llm_calls": 5,
            "search_calls": 8,
            "duration_ms": 45000,
        }
        result = rh.summarize_completed_task(trace)
        assert result["total_sources"] == 60
        assert result["high_quality"] == 10
        assert result["duration_ms"] == 45000


def _run_all():
    test_classes = [
        TestBuildResearchFormPayload,
        TestFormatIntentPreview,
        TestShouldShowLiveTrace,
        TestGroupQueueItems,
        TestFormatTraceEvent,
        TestBuildLiveProgressSummary,
        TestSummarizeCompletedTask,
    ]
    total = 0
    passed = 0
    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in methods:
            total += 1
            try:
                getattr(instance, method_name)()
                passed += 1
            except AssertionError as e:
                print(f"  FAIL {cls.__name__}.{method_name}: {e}")
            except Exception as e:
                print(f"  ERROR {cls.__name__}.{method_name}: {e}")

    print(f"\n{'✅' if passed == total else '❌'} {passed}/{total} tests passed")
    return passed == total


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
