"""SQLAlchemy ORM 表定义。

list 字段使用 JSON 序列化存储在 TEXT 列中。
所有时间使用 UTC。
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid_str() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TaskTable(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    task_type: Mapped[str] = mapped_column(String(30), default="search_research")
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_topic: Mapped[str] = mapped_column(String(500), default="")
    mode: Mapped[str] = mapped_column(String(20), default="auto")
    language: Mapped[str] = mapped_column(String(10), default="mixed")
    depth: Mapped[str] = mapped_column(String(10), default="standard")
    include_gossip: Mapped[bool] = mapped_column(Boolean, default=False)
    include_books: Mapped[bool] = mapped_column(Boolean, default=True)
    include_video: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    obsidian_path: Mapped[str] = mapped_column(String(500), default="")
    user_language: Mapped[str] = mapped_column(String(10), default="")
    working_language: Mapped[str] = mapped_column(String(10), default="")
    output_language: Mapped[str] = mapped_column(String(10), default="")
    search_strategy: Mapped[str] = mapped_column(String(30), default="")
    expanded_queries: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str] = mapped_column(Text, default="")
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    exported: Mapped[bool] = mapped_column(Boolean, default=False)
    export_path: Mapped[str] = mapped_column(String(500), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class QueryTable(Base):
    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    query: Mapped[str] = mapped_column(String(1000), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="tavily")
    round: Mapped[int] = mapped_column(Integer, default=1)
    purpose: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SourceTable(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    domain: Mapped[str] = mapped_column(String(200), default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    source_type: Mapped[str] = mapped_column(String(20), default="other")
    source_level: Mapped[str] = mapped_column(String(2), default="C")
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    authority_score: Mapped[float] = mapped_column(Float, default=0.0)
    originality_score: Mapped[float] = mapped_column(Float, default=0.0)
    gossip_score: Mapped[float] = mapped_column(Float, default=0.0)
    downloadable: Mapped[bool] = mapped_column(Boolean, default=True)
    download_status: Mapped[str] = mapped_column(String(20), default="pending")
    reason_to_read: Mapped[str] = mapped_column(Text, default="")


class ExtractedTable(Base):
    __tablename__ = "extracted_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    source_item_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    markdown_path: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    key_quotes: Mapped[str] = mapped_column(Text, default="[]")
    people: Mapped[str] = mapped_column(Text, default="[]")
    places: Mapped[str] = mapped_column(Text, default="[]")
    organizations: Mapped[str] = mapped_column(Text, default="[]")
    concepts: Mapped[str] = mapped_column(Text, default="[]")
    events: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class EntityTable(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), default="other")
    description: Mapped[str] = mapped_column(Text, default="")
    related_task_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    should_expand: Mapped[bool] = mapped_column(Boolean, default=False)


class ResearchCardTable(Base):
    __tablename__ = "research_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), default="fact")
    title: Mapped[str] = mapped_column(String(500), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    linked_sources: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[str] = mapped_column(String(20), default="unverified")
    markdown_path: Mapped[str] = mapped_column(String(500), default="")


class TaskEventTable(Base):
    __tablename__ = "task_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(500), default="")
    level: Mapped[str] = mapped_column(String(10), default="info")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
