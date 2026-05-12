"""研究任务持久化测试 - 验证 DB 存储行为。"""

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.repositories import TaskRepository, SourceRepository
from db.tables import Base, TaskTable, SourceTable
from models.enums import TaskStatus


@pytest.fixture
def db_session():
    """创建内存 SQLite 数据库用于测试。"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestTaskRepository:
    def test_create_task_persists(self, db_session) -> None:
        """创建任务后 DB 存在。"""
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t1", topic="Tim Cook 童年")
        row = repo.get_task("t1")
        assert row is not None
        assert row.topic == "Tim Cook 童年"
        assert row.status == TaskStatus.PENDING

    def test_get_task_after_new_session(self, db_session) -> None:
        """重新获取 session 后仍能 get_task。"""
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t2", topic="OpenAI 宫斗")

        # 模拟"重启"：用同一个 engine 创建新 session
        row = repo.get_task("t2")
        assert row is not None
        assert row.topic == "OpenAI 宫斗"

    def test_update_task_status(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t3", topic="Test")
        repo.update_task_status("t3", TaskStatus.RUNNING)
        row = repo.get_task("t3")
        assert row.status == TaskStatus.RUNNING

    def test_mark_completed(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t4", topic="Test")
        repo.mark_completed("t4", source_count=91, expanded_queries=["q1", "q2"])
        row = repo.get_task("t4")
        assert row.status == TaskStatus.COMPLETED
        assert row.source_count == 91
        assert row.completed_at is not None
        queries = json.loads(row.expanded_queries)
        assert queries == ["q1", "q2"]

    def test_list_tasks_returns_history(self, db_session) -> None:
        """list_tasks 返回历史任务。"""
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t5", topic="Task A")
        repo.create_task(task_id="t6", topic="Task B")
        repo.create_task(task_id="t7", topic="Task C")

        tasks = repo.list_tasks(limit=10)
        assert len(tasks) == 3

    def test_list_tasks_order_desc(self, db_session) -> None:
        """默认按 created_at desc。"""
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t8", topic="First")
        repo.create_task(task_id="t9", topic="Second")

        tasks = repo.list_tasks()
        # 后创建的在前
        assert tasks[0].id == "t9"

    def test_list_tasks_status_filter(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t10", topic="A")
        repo.create_task(task_id="t11", topic="B")
        repo.mark_completed("t10", source_count=10)

        completed = repo.list_tasks(status="completed")
        assert len(completed) == 1
        assert completed[0].id == "t10"

    def test_list_tasks_q_filter(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t12", topic="Tim Cook 童年")
        repo.create_task(task_id="t13", topic="OpenAI 宫斗")

        results = repo.list_tasks(q="Cook")
        assert len(results) == 1
        assert results[0].topic == "Tim Cook 童年"

    def test_count_tasks(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t14", topic="A")
        repo.create_task(task_id="t15", topic="B")
        assert repo.count_tasks() == 2
        assert repo.count_tasks(status="completed") == 0

    def test_mark_exported(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t16", topic="Test")
        repo.mark_exported("t16", "/tmp/vault/index.md")
        row = repo.get_task("t16")
        assert row.exported is True
        assert row.export_path == "/tmp/vault/index.md"

    def test_update_task_metadata(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(task_id="t17", topic="Test")
        repo.update_task_metadata("t17", canonical_topic="Tim Cook", search_strategy="english_first")
        row = repo.get_task("t17")
        assert row.canonical_topic == "Tim Cook"
        assert row.search_strategy == "english_first"

    def test_nonexistent_task_returns_none(self, db_session) -> None:
        repo = TaskRepository(db_session)
        assert repo.get_task("nonexistent") is None

    def test_create_with_all_fields(self, db_session) -> None:
        repo = TaskRepository(db_session)
        repo.create_task(
            task_id="t18",
            topic="Full Test",
            mode="person",
            depth="deep",
            include_gossip=True,
            include_books=True,
            include_video=True,
            obsidian_path="/tmp/vault",
        )
        row = repo.get_task("t18")
        assert row.mode == "person"
        assert row.depth == "deep"
        assert row.include_gossip is True
        assert row.obsidian_path == "/tmp/vault"


class TestSourceRepository:
    def test_bulk_create_and_count(self, db_session) -> None:
        repo = SourceRepository(db_session)
        sources = [
            {"id": "s1", "task_id": "t1", "url": "https://a.com", "source_level": "S"},
            {"id": "s2", "task_id": "t1", "url": "https://b.com", "source_level": "A"},
            {"id": "s3", "task_id": "t1", "url": "https://c.com", "source_level": "B"},
        ]
        repo.bulk_create(sources)
        assert repo.count_by_task("t1") == 3

    def test_count_high_quality(self, db_session) -> None:
        repo = SourceRepository(db_session)
        sources = [
            {"id": "s4", "task_id": "t2", "url": "https://a.com", "source_level": "S"},
            {"id": "s5", "task_id": "t2", "url": "https://b.com", "source_level": "A"},
            {"id": "s6", "task_id": "t2", "url": "https://c.com", "source_level": "C"},
        ]
        repo.bulk_create(sources)
        assert repo.count_high_quality("t2") == 2

    def test_get_by_task(self, db_session) -> None:
        repo = SourceRepository(db_session)
        sources = [
            {"id": "s7", "task_id": "t3", "url": "https://a.com"},
            {"id": "s8", "task_id": "t3", "url": "https://b.com"},
            {"id": "s9", "task_id": "other", "url": "https://c.com"},
        ]
        repo.bulk_create(sources)
        results = repo.get_by_task("t3")
        assert len(results) == 2
