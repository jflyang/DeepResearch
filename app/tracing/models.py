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

    # === Report Ingestion Steps ===
    REPORT_IMPORT_TASK_CREATED = "report_import_task_created"
    REPORT_PARSE_STARTED = "report_parse_started"
    REPORT_PARSE_FINISHED = "report_parse_finished"
    REPORT_PARSE_FAILED = "report_parse_failed"
    RULE_REFERENCE_EXTRACTION_FINISHED = "rule_reference_extraction_finished"
    REPORT_LLM_UNDERSTANDING_STARTED = "report_understanding_started"
    REPORT_LLM_UNDERSTANDING_FINISHED = "report_understanding_finished"
    REPORT_LLM_UNDERSTANDING_FAILED = "report_understanding_fallback"
    REPORT_LLM_REFERENCE_EXTRACTION_STARTED = "report_reference_extraction_started"
    REPORT_LLM_REFERENCE_EXTRACTION_FINISHED = "report_reference_extraction_finished"
    REPORT_LLM_REFERENCE_EXTRACTION_FAILED = "report_reference_extraction_fallback"
    REFERENCE_MERGE_FINISHED = "reference_merge_finished"
    IMPORTED_URL_EXTRACTION_STARTED = "url_extraction_started"
    IMPORTED_URL_EXTRACTION_FINISHED = "url_extraction_finished"
    IMPORTED_URL_EXTRACTION_FAILED = "imported_url_extraction_failed"
    IMPORTED_BOOK_ENRICHMENT_STARTED = "book_enrichment_started"
    IMPORTED_BOOK_ENRICHMENT_FINISHED = "book_enrichment_finished"
    IMPORTED_PAPER_ENRICHMENT_STARTED = "paper_enrichment_started"
    IMPORTED_PAPER_ENRICHMENT_FINISHED = "paper_enrichment_finished"
    REPORT_INGESTION_COMPLETED = "report_ingestion_completed"
    REPORT_INGESTION_FAILED = "report_ingestion_failed"
    LLM_ENHANCEMENT_SKIPPED = "llm_enhancement_skipped"

    # === Crawlee Steps ===
    CRAWL_CANDIDATES_COLLECTED = "crawl_candidates_collected"
    CRAWL_CANDIDATE_REVIEW_STARTED = "crawl_candidate_review_started"
    CRAWL_CANDIDATE_REVIEW_FINISHED = "crawl_candidate_review_finished"
    CRAWL_CANDIDATE_SKIPPED = "crawl_candidate_skipped"
    CRAWLEE_BATCH_STARTED = "crawlee_batch_started"
    CRAWLEE_URL_STARTED = "crawlee_url_started"
    CRAWLEE_URL_FINISHED = "crawlee_url_finished"
    CRAWLEE_URL_FAILED = "crawlee_url_failed"
    CRAWLEE_BATCH_FINISHED = "crawlee_batch_finished"
    CRAWL_SAVED_DOCUMENT = "crawl_saved_document"
    CRAWL_AUTO_EXPORT_STARTED = "crawl_auto_export_started"
    CRAWL_AUTO_EXPORT_FINISHED = "crawl_auto_export_finished"


class TracePhase:
    """Trace 阶段常量。"""

    PLANNING = "planning"
    LLM = "llm"
    SEARCH = "search"
    PROCESSING = "processing"
    STORAGE = "storage"
    EXTRACTION = "extraction"
    EXPORT = "export"
    INGESTION = "ingestion"
    CRAWLING = "crawling"


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
