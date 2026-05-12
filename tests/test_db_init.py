"""测试数据库初始化 - 验证表创建。"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect

from db.tables import Base


def test_all_tables_created():
    """验证所有 6 张表都能正确创建。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    expected = {
        "tasks",
        "queries",
        "sources",
        "extracted_documents",
        "entities",
        "research_cards",
        "task_events",
    }
    assert expected == tables


def test_task_table_columns():
    """验证 tasks 表的列。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("tasks")}

    expected_columns = {
        "id", "task_type", "topic", "canonical_topic", "mode", "language", "depth",
        "include_gossip", "include_books", "include_video",
        "status", "obsidian_path",
        "user_language", "working_language", "output_language", "search_strategy",
        "expanded_queries", "error_message", "source_count",
        "exported", "export_path", "metadata_json",
        "created_at", "updated_at", "completed_at",
        "deleted_at", "renamed_at", "cloned_from_task_id",
    }
    assert expected_columns == columns


def test_source_table_columns():
    """验证 sources 表的列。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("sources")}

    assert "relevance_score" in columns
    assert "authority_score" in columns
    assert "originality_score" in columns
    assert "gossip_score" in columns
    assert "source_level" in columns
    assert "reason_to_read" in columns


def test_extracted_table_has_json_list_columns():
    """验证 extracted_documents 表有 JSON list 列。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("extracted_documents")}

    json_fields = {"key_quotes", "people", "places", "organizations", "concepts", "events"}
    assert json_fields.issubset(columns)
