"""数据访问层 - CRUD 操作封装。"""

import json
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from db.tables import ExtractedTable, QueryTable, SourceTable, TaskTable
from models.enums import DownloadStatus, TaskStatus

logger = logging.getLogger(__name__)


class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, task_id: str, topic: str) -> TaskTable:
        row = TaskTable(id=task_id, topic=topic, status=TaskStatus.PENDING)
        self.session.add(row)
        self.session.commit()
        logger.info("Task created: %s", task_id)
        return row

    def get(self, task_id: str) -> TaskTable | None:
        return self.session.get(TaskTable, task_id)

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        row = self.session.get(TaskTable, task_id)
        if row:
            row.status = status
            row.updated_at = datetime.now()
            self.session.commit()

    def update_queries(self, task_id: str, queries: list[str]) -> None:
        row = self.session.get(TaskTable, task_id)
        if row:
            row.expanded_queries = json.dumps(queries, ensure_ascii=False)
            row.updated_at = datetime.now()
            self.session.commit()

    def list_all(self) -> list[TaskTable]:
        return self.session.query(TaskTable).order_by(TaskTable.created_at.desc()).all()


class SourceRepository:
    def __init__(self, session: Session):
        self.session = session

    def bulk_create(self, sources: list[dict]) -> int:
        rows = [SourceTable(**s) for s in sources]
        self.session.add_all(rows)
        self.session.commit()
        logger.info("Bulk created %d sources", len(rows))
        return len(rows)

    def get_by_task(self, task_id: str) -> list[SourceTable]:
        return (
            self.session.query(SourceTable)
            .filter(SourceTable.task_id == task_id)
            .order_by(SourceTable.final_score.desc())
            .all()
        )

    def update_download_status(self, source_id: str, status: DownloadStatus) -> None:
        row = self.session.get(SourceTable, source_id)
        if row:
            row.download_status = status
            self.session.commit()


class ExtractedRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, data: dict) -> ExtractedTable:
        row = ExtractedTable(**data)
        self.session.add(row)
        self.session.commit()
        return row

    def get_by_source(self, source_id: str) -> ExtractedTable | None:
        return (
            self.session.query(ExtractedTable)
            .filter(ExtractedTable.source_id == source_id)
            .first()
        )
