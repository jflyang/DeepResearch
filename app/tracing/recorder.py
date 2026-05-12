"""TraceRecorder - 研究任务执行轨迹记录器。

设计原则：
- record 失败不能抛出到业务流程
- 自动补充 created_at
- 支持 payload 脱敏
- 支持 no-op recorder（测试用）
"""

import logging
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import Any

from app.tracing.models import TraceEvent, TracePhase, TraceStep

logger = logging.getLogger(__name__)

# 敏感 key 列表
_SENSITIVE_KEYS = frozenset({
    "api_key", "api-key", "authorization", "token", "secret",
    "password", "passwd", "credential", "access_key", "secret_key",
})


def _sanitize(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """脱敏：替换敏感 key 的值为 '***'。"""
    if data is None:
        return None
    result = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sk in key_lower for sk in _SENSITIVE_KEYS):
            result[key] = "***"
        elif isinstance(value, dict):
            result[key] = _sanitize(value)
        else:
            result[key] = value
    return result


class TraceRecorder:
    """研究任务执行轨迹记录器（内存存储）。"""

    def __init__(self) -> None:
        self._events: dict[str, list[TraceEvent]] = {}

    def record(
        self,
        task_id: str,
        step: str,
        phase: str,
        level: str = "info",
        message: str = "",
        service: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """记录一个 trace 事件。绝不抛出异常。"""
        try:
            event = TraceEvent(
                task_id=task_id,
                step=step,
                phase=phase,
                level=level,
                message=message,
                service=service,
                provider=provider,
                model=model,
                input_summary=_sanitize(input_summary),
                output_summary=_sanitize(output_summary),
                metrics=metrics,
                error_code=error_code,
                error_message=error_message,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )
            if task_id not in self._events:
                self._events[task_id] = []
            self._events[task_id].append(event)
        except Exception as e:
            logger.debug("trace_record_failed error=%s", str(e))

    def info(self, task_id: str, step: str, phase: str, message: str = "", **kwargs) -> None:
        self.record(task_id, step, phase, level="info", message=message, **kwargs)

    def warning(self, task_id: str, step: str, phase: str, message: str = "", **kwargs) -> None:
        self.record(task_id, step, phase, level="warning", message=message, **kwargs)

    def error(self, task_id: str, step: str, phase: str, message: str = "", **kwargs) -> None:
        self.record(task_id, step, phase, level="error", message=message, **kwargs)

    def get_events(self, task_id: str, limit: int = 500, level: str | None = None, phase: str | None = None) -> list[TraceEvent]:
        """获取任务的 trace 事件。"""
        events = self._events.get(task_id, [])
        if level:
            events = [e for e in events if e.level == level]
        if phase:
            events = [e for e in events if e.phase == phase]
        return sorted(events, key=lambda e: e.created_at)[:limit]

    def get_summary(self, task_id: str) -> dict[str, Any]:
        """获取任务 trace 摘要。"""
        events = self._events.get(task_id, [])
        if not events:
            return {"task_id": task_id, "total_events": 0}

        error_count = sum(1 for e in events if e.level == "error")
        warning_count = sum(1 for e in events if e.level == "warning")
        llm_calls = sum(1 for e in events if e.step == TraceStep.LLM_CALL_FINISHED)
        search_calls = sum(1 for e in events if e.step == TraceStep.SEARCH_PROVIDER_FINISHED)

        providers_used = set()
        for e in events:
            if e.provider:
                providers_used.add(e.provider)

        # 总耗时
        total_duration_ms = None
        task_created = next((e for e in events if e.step == TraceStep.TASK_CREATED), None)
        task_completed = next((e for e in events if e.step in (TraceStep.TASK_COMPLETED, TraceStep.TASK_FAILED)), None)
        if task_created and task_completed:
            delta = task_completed.created_at - task_created.created_at
            total_duration_ms = int(delta.total_seconds() * 1000)

        # 来源统计
        source_counts = {}
        level_counts = {}
        for e in events:
            if e.step == TraceStep.DEDUPE_FINISHED and e.output_summary:
                source_counts = {
                    "raw": e.output_summary.get("before_count", 0),
                    "deduped": e.output_summary.get("after_count", 0),
                }
            if e.step == TraceStep.SCORING_FINISHED and e.output_summary:
                level_counts = e.output_summary.get("level_counts", {})

        summary = {
            "task_id": task_id,
            "total_events": len(events),
            "error_count": error_count,
            "warning_count": warning_count,
            "llm_calls": llm_calls,
            "search_calls": search_calls,
            "providers_used": sorted(providers_used),
            "duration_ms": total_duration_ms,
            "source_counts": source_counts,
            "level_counts": level_counts,
        }

        # Report ingestion 专用摘要
        ri_completed = next(
            (e for e in events if e.step == TraceStep.REPORT_INGESTION_COMPLETED), None
        )
        if ri_completed:
            summary["task_type"] = "report_ingestion"
            ri_data = ri_completed.output_summary or {}
            summary["report_ingestion"] = {
                "parsed_url_count": ri_data.get("parsed_url_count", 0),
                "parsed_book_count": ri_data.get("parsed_book_count", 0),
                "parsed_paper_count": ri_data.get("parsed_paper_count", 0),
                "extracted_document_count": ri_data.get("extracted_document_count", 0),
                "enriched_source_count": ri_data.get("enriched_source_count", 0),
                "failed_count": ri_data.get("failed_count", 0),
                "source_count": ri_data.get("source_count", 0),
            }

            # 引用合并统计
            merge_event = next(
                (e for e in events if e.step == "reference_merge_finished"), None
            )
            if merge_event and merge_event.output_summary:
                summary["references"] = merge_event.output_summary

            # LLM 使用统计
            llm_steps = [e for e in events if "understanding_finished" in e.step or "extraction_finished" in e.step]
            llm_tasks_used = []
            for e in llm_steps:
                if e.output_summary and e.output_summary.get("status") == "used_llm":
                    llm_tasks_used.append(e.step.replace("_finished", ""))
            if llm_tasks_used:
                summary["llm_tasks_used"] = llm_tasks_used

        return summary

    def clear(self, task_id: str | None = None) -> None:
        """清除事件（测试用）。"""
        if task_id:
            self._events.pop(task_id, None)
        else:
            self._events.clear()


class _NoopRecorder(TraceRecorder):
    """No-op recorder，所有操作静默忽略。"""

    def record(self, *args, **kwargs) -> None:
        pass

    def get_events(self, *args, **kwargs) -> list[TraceEvent]:
        return []

    def get_summary(self, *args, **kwargs) -> dict[str, Any]:
        return {"task_id": "", "total_events": 0}


# 全局单例
_global_recorder: TraceRecorder | None = None


def get_recorder() -> TraceRecorder:
    """获取全局 TraceRecorder 单例。"""
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = TraceRecorder()
    return _global_recorder


def noop_recorder() -> TraceRecorder:
    """返回 no-op recorder（测试用）。"""
    return _NoopRecorder()


# === Trace Span Context Manager ===


class TraceSpan:
    """Trace span - 自动计算 duration_ms。"""

    def __init__(
        self,
        recorder: TraceRecorder,
        task_id: str,
        step: str,
        phase: str,
        service: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        input_summary: dict[str, Any] | None = None,
    ):
        self._recorder = recorder
        self._task_id = task_id
        self._step = step
        self._phase = phase
        self._service = service
        self._provider = provider
        self._model = model
        self._input_summary = input_summary
        self._start_time = time.perf_counter()
        self._started_at = datetime.now(UTC)
        self._finished = False

    def finish(
        self,
        output_summary: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        message: str = "",
    ) -> None:
        """标记 span 完成。"""
        if self._finished:
            return
        self._finished = True
        duration_ms = int((time.perf_counter() - self._start_time) * 1000)
        ended_at = datetime.now(UTC)

        # 自动推断 finished step name
        finished_step = self._step
        if finished_step.endswith("_started"):
            finished_step = finished_step.replace("_started", "_finished")

        self._recorder.record(
            task_id=self._task_id,
            step=finished_step,
            phase=self._phase,
            level="info",
            message=message,
            service=self._service,
            provider=self._provider,
            model=self._model,
            input_summary=self._input_summary,
            output_summary=output_summary,
            metrics=metrics,
            started_at=self._started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )

    def fail(self, error: Exception | str, error_code: str | None = None) -> None:
        """标记 span 失败。"""
        if self._finished:
            return
        self._finished = True
        duration_ms = int((time.perf_counter() - self._start_time) * 1000)
        ended_at = datetime.now(UTC)

        error_msg = str(error) if isinstance(error, Exception) else error
        failed_step = self._step
        if failed_step.endswith("_started"):
            failed_step = failed_step.replace("_started", "_failed")

        self._recorder.record(
            task_id=self._task_id,
            step=failed_step,
            phase=self._phase,
            level="error",
            message=f"Failed: {error_msg[:200]}",
            service=self._service,
            provider=self._provider,
            model=self._model,
            input_summary=self._input_summary,
            error_code=error_code or type(error).__name__ if isinstance(error, Exception) else error_code,
            error_message=error_msg[:500],
            started_at=self._started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )


@asynccontextmanager
async def trace_span(
    recorder: TraceRecorder,
    task_id: str,
    step: str,
    phase: str,
    service: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    input_summary: dict[str, Any] | None = None,
):
    """异步 trace span context manager。

    用法：
        async with trace_span(recorder, task_id, "search_provider_started", "search",
                              provider="tavily", input_summary={"query": q}) as span:
            results = await provider.search(q)
            span.finish(output_summary={"count": len(results)})
    """
    span = TraceSpan(recorder, task_id, step, phase, service, provider, model, input_summary)
    try:
        yield span
    except Exception as e:
        if not span._finished:
            span.fail(e)
        raise
    finally:
        # 如果用户没有手动 finish/fail，自动 finish
        if not span._finished:
            span.finish()
