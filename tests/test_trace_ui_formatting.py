"""Trace UI 格式化逻辑测试。"""

import sys
sys.path.insert(0, ".")

from app.tracing.formatters import (
    format_trace_event_summary,
    get_trace_event_icon,
    get_trace_event_title,
    format_duration_ms,
    format_count,
    sanitize_trace_payload,
)


class TestFormatTraceEventSummary:
    def test_llm_event(self):
        event = {
            "step": "llm_call_finished",
            "level": "info",
            "message": "",
            "provider": "deepseek",
            "model": "deepseek-v4",
            "duration_ms": 2300,
            "output_summary": {"task_name": "query_expansion", "output_chars": 1200},
        }
        result = format_trace_event_summary(event)
        assert "🤖" in result
        assert "LLM 调用完成" in result
        assert "deepseek" in result
        assert "query_expansion" in result
        assert "2.30s" in result

    def test_search_event(self):
        event = {
            "step": "search_provider_finished",
            "level": "info",
            "message": "",
            "provider": "searxng",
            "duration_ms": 1500,
            "output_summary": {"result_count": 18},
        }
        result = format_trace_event_summary(event)
        assert "🔎" in result
        assert "搜索完成" in result
        assert "searxng" in result
        assert "18 条结果" in result

    def test_search_event_with_count_field(self):
        event = {
            "step": "search_provider_finished",
            "level": "info",
            "provider": "tavily",
            "output_summary": {"count": 10},
        }
        result = format_trace_event_summary(event)
        assert "10 条结果" in result

    def test_error_event(self):
        event = {
            "step": "llm_call_failed",
            "level": "error",
            "message": "timeout after 30s",
        }
        result = format_trace_event_summary(event)
        assert "❌" in result

    def test_warning_event(self):
        event = {
            "step": "search_provider_failed",
            "level": "warning",
            "message": "rate limited",
        }
        result = format_trace_event_summary(event)
        assert "⚠️" in result

    def test_task_completed(self):
        event = {
            "step": "task_completed",
            "level": "info",
            "duration_ms": 45000,
        }
        result = format_trace_event_summary(event)
        assert "✅" in result
        assert "研究完成" in result
        assert "45.00s" in result

    def test_unknown_event_does_not_crash(self):
        event = {
            "step": "some_unknown_step",
            "level": "info",
            "message": "something happened",
        }
        result = format_trace_event_summary(event)
        assert "●" in result
        assert "some_unknown_step" in result
        assert "something happened" in result

    def test_empty_event_does_not_crash(self):
        result = format_trace_event_summary({})
        assert isinstance(result, str)


class TestFormatDurationMs:
    def test_milliseconds(self):
        assert format_duration_ms(450) == "450ms"

    def test_seconds(self):
        assert format_duration_ms(2300) == "2.30s"

    def test_minutes(self):
        assert format_duration_ms(65000) == "1m 5s"

    def test_none(self):
        assert format_duration_ms(None) == "—"

    def test_zero(self):
        assert format_duration_ms(0) == "0ms"

    def test_exact_second(self):
        assert format_duration_ms(1000) == "1.00s"


class TestFormatCount:
    def test_number(self):
        assert format_count(42) == "42"

    def test_none(self):
        assert format_count(None) == "—"

    def test_zero(self):
        assert format_count(0) == "0"


class TestSanitizeTracePayload:
    def test_api_key_redacted(self):
        payload = {"api_key": "sk-12345", "model": "gpt-4"}
        result = sanitize_trace_payload(payload)
        assert result["api_key"] == "***REDACTED***"
        assert result["model"] == "gpt-4"

    def test_authorization_redacted(self):
        payload = {"authorization": "Bearer token123", "status": "ok"}
        result = sanitize_trace_payload(payload)
        assert result["authorization"] == "***REDACTED***"
        assert result["status"] == "ok"

    def test_secret_redacted(self):
        payload = {"secret": "mysecret", "timeout": 30}
        result = sanitize_trace_payload(payload)
        assert result["secret"] == "***REDACTED***"

    def test_password_redacted(self):
        payload = {"password": "pass123"}
        result = sanitize_trace_payload(payload)
        assert result["password"] == "***REDACTED***"

    def test_private_key_redacted(self):
        payload = {"private_key": "-----BEGIN RSA-----"}
        result = sanitize_trace_payload(payload)
        assert result["private_key"] == "***REDACTED***"

    def test_max_output_tokens_not_redacted(self):
        payload = {"max_output_tokens": 1000, "input_chars": 5000}
        result = sanitize_trace_payload(payload)
        assert result["max_output_tokens"] == 1000
        assert result["input_chars"] == 5000

    def test_nested_dict(self):
        payload = {"config": {"api_key": "secret", "model": "gpt-4"}}
        result = sanitize_trace_payload(payload)
        assert result["config"]["api_key"] == "***REDACTED***"
        assert result["config"]["model"] == "gpt-4"

    def test_list_in_payload(self):
        payload = {"items": [{"api_key": "x"}, {"name": "y"}]}
        result = sanitize_trace_payload(payload)
        assert result["items"][0]["api_key"] == "***REDACTED***"
        assert result["items"][1]["name"] == "y"

    def test_none_payload(self):
        assert sanitize_trace_payload(None) is None

    def test_empty_dict(self):
        assert sanitize_trace_payload({}) == {}

    def test_cookie_redacted(self):
        payload = {"cookie": "session=abc123"}
        result = sanitize_trace_payload(payload)
        assert result["cookie"] == "***REDACTED***"

    def test_access_token_redacted(self):
        payload = {"access_token": "token123"}
        result = sanitize_trace_payload(payload)
        assert result["access_token"] == "***REDACTED***"


class TestGetTraceEventIcon:
    def test_llm(self):
        assert get_trace_event_icon({"step": "llm_call_finished", "level": "info"}) == "🤖"

    def test_search(self):
        assert get_trace_event_icon({"step": "search_provider_finished", "level": "info"}) == "🔎"

    def test_error_overrides(self):
        assert get_trace_event_icon({"step": "llm_call_finished", "level": "error"}) == "❌"

    def test_warning_overrides(self):
        assert get_trace_event_icon({"step": "search_provider_finished", "level": "warning"}) == "⚠️"

    def test_unknown(self):
        assert get_trace_event_icon({"step": "unknown", "level": "info"}) == "●"


class TestGetTraceEventTitle:
    def test_known_step(self):
        assert get_trace_event_title({"step": "task_created"}) == "任务已创建"
        assert get_trace_event_title({"step": "llm_call_finished"}) == "LLM 调用完成"

    def test_unknown_step(self):
        assert get_trace_event_title({"step": "custom_step"}) == "custom_step"


def _run_all():
    test_classes = [
        TestFormatTraceEventSummary,
        TestFormatDurationMs,
        TestFormatCount,
        TestSanitizeTracePayload,
        TestGetTraceEventIcon,
        TestGetTraceEventTitle,
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
