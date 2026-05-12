"""任务事件日志服务 - 记录每个研究步骤的状态。

设计原则：
- 日志失败不能导致任务失败
- 所有写入操作包裹 try/except
- 支持内存模式（测试）和 DB 模式
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# === 事件模型 ===


class TaskEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    event_type: str
    message: str = ""
    level: str = "info"  # info / warning / error
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# === 事件存储（内存，MVP） ===

_events_store: dict[str, list[TaskEvent]] = {}


def _store_event(event: TaskEvent) -> None:
    """存储事件到内存。"""
    if event.task_id not in _events_store:
        _events_store[event.task_id] = []
    _events_store[event.task_id].append(event)


# === 公开 API ===


def log_event(
    task_id: str,
    event_type: str,
    message: str = "",
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    """
    记录任务事件。

    绝不抛出异常 — 日志失败不影响主流程。
    """
    try:
        event = TaskEvent(
            task_id=task_id,
            event_type=event_type,
            message=message,
            level=level,
            payload=payload or {},
        )
        _store_event(event)
        logger.info(
            "task_event task_id=%s type=%s level=%s msg=%s",
            task_id,
            event_type,
            level,
            message[:100],
        )
    except Exception as e:
        # 绝不让日志系统影响主流程
        logger.debug("task_event_log_failed error=%s", str(e))


def get_events(task_id: str, limit: int = 50) -> list[TaskEvent]:
    """获取任务事件列表（最新在前）。"""
    try:
        events = _events_store.get(task_id, [])
        return sorted(events, key=lambda e: e.created_at, reverse=True)[:limit]
    except Exception:
        return []


def clear_events(task_id: str | None = None) -> None:
    """清除事件（仅测试用）。"""
    global _events_store
    if task_id:
        _events_store.pop(task_id, None)
    else:
        _events_store = {}
