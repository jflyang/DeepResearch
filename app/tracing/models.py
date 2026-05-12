"""Trace 数据模型。"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TraceStep:
    """Trace 步骤常量。"""

    TASK_CREATED = "task_created"
    TOPIC_UNDERSTANDING_STARTED = "topic_understanding_started"
    TOPIC_UNDERSTANDING_FINISHED = "topic_understanding_finished"
    LANGUAGE_PLANNING_STARTED = "language_planning_started"
    LANGUAGE_PLANNING_FINISHED = "language_planning_finished"
    QUERY_EXPANSION_STARTED = "query_expansion_started"
    QUERY_EXPANSION_FINISHED = "query_expansion_finished"
    LLM_CALL_STARTED = "llm_call_started"
    LLM_CALL_FINISHED = "llm_call_finished"
    LLM_CALL_FAILED = "llm_call_failed"
    SEARCH_STARTED = "search_started"
    SEARCH_PROVIDER_STARTED = "search_provider_started"
    SEARCH_PROVIDER_FINISHED = "search_provider_finished"
    SEARCH_PROVIDER_FAILED = "search_provider_failed"
    DEDUPE_STARTED = "dedupe_started"
    DEDUPE_FINISHED = "dedupe_finished"
    SCORING_STARTED = "scoring_started"
    SCORING_FINISHED = "scoring_finished"
    CLASSIFICATION_STARTED = "classification_started"
    CLASSIFICATION_FINISHED = "classification_finished"
    DB_SAVE_STARTED = "db_save_started"
    DB_SAVE_FINISHED = "db_save_finished"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_FINISHED = "extraction_finished"
    EXTRACTION_FAILED = "extraction_failed"
    EXPORT_STARTED = "export_started"
    EXPORT_FINISHED = "export_finished"
    EXPORT_FAILED = "export_failed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


class TracePhase:
    """Trace 阶段常量。"""

    PLANNING = "planning"
    LLM = "llm"
    SEARCH = "search"
    PROCESSING = "processing"
    STORAGE = "storage"
    EXTRACTION = "extraction"
    EXPORT = "export"


class TraceEvent(BaseModel):
    """单个 trace 事件。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    step: str
    phase: str
    level: str = "info"  # info / warning / error / debug
    message: str = ""
    service: str | None = None
    provider: str | None = None
    model: str | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
