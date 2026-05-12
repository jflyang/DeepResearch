"""数据访问层 - CRUD 操作封装。"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.tables import ExtractedTable, QueryTable, SourceTable, TaskTable
from models.enums import DownloadStatus, ResearchTaskType, TaskStatus
from models.schemas import ImportedReportCreate, ResearchTask

logger = logging.getLogger(__name__)

# 报告文件存储目录
_IMPORTED_REPORTS_DIR = Path("data/imported_reports")


class TaskRepository:
    """研究任务 CRUD。"""

    def __init__(self, session: Session):
        self.session = session

    def create_task(
        self,
        task_id: str,
        topic: str,
        mode: str = "auto",
        depth: str = "standard",
        include_gossip: bool = False,
        include_books: bool = True,
        include_video: bool = False,
        obsidian_path: str = "",
    ) -> TaskTable:
        row = TaskTable(
            id=task_id,
            topic=topic,
            mode=mode,
            depth=depth,
            include_gossip=include_gossip,
            include_books=include_books,
            include_video=include_video,
            obsidian_path=obsidian_path,
            status=TaskStatus.PENDING,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get_task(self, task_id: str) -> TaskTable | None:
        return self.session.get(TaskTable, task_id)

    def update_task_status(self, task_id: str, status: str, error_message: str = "") -> None:
        row = self.session.get(TaskTable, task_id)
        if row:
            row.status = status
            row.updated_at = datetime.now(UTC)
            if error_message:
                row.error_message = error_message
            if status == TaskStatus.COMPLETED:
                row.completed_at = datetime.now(UTC)
            self.session.commit()

    def mark_completed(
        self,
        task_id: str,
        source_count: int = 0,
        expanded_queries: list[str] | None = None,
    ) -> None:
        row = self.session.get(TaskTable, task_id)
        if row:
            row.status = TaskStatus.COMPLETED
            row.completed_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            row.source_count = source_count
            if expanded_queries is not None:
                row.expanded_queries = json.dumps(expanded_queries, ensure_ascii=False)
            self.session.commit()

    def update_task_metadata(self, task_id: str, **kwargs) -> None:
        """更新任务的任意字段。"""
        row = self.session.get(TaskTable, task_id)
        if not row:
            return
        for key, value in kwargs.items():
            if hasattr(row, key):
                setattr(row, key, value)
        row.updated_at = datetime.now(UTC)
        self.session.commit()

    def mark_exported(self, task_id: str, export_path: str) -> None:
        row = self.session.get(TaskTable, task_id)
        if row:
            row.exported = True
            row.export_path = export_path
            row.updated_at = datetime.now(UTC)
            self.session.commit()

    def list_tasks(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        q: str | None = None,
        include_deleted: bool = False,
    ) -> list[TaskTable]:
        query = self.session.query(TaskTable)
        if not include_deleted:
            query = query.filter(TaskTable.deleted_at.is_(None))
        if status:
            query = query.filter(TaskTable.status == status)
        if q:
            query = query.filter(TaskTable.topic.ilike(f"%{q}%"))
        return query.order_by(TaskTable.created_at.desc()).offset(offset).limit(limit).all()

    def count_tasks(self, status: str | None = None, q: str | None = None, include_deleted: bool = False) -> int:
        query = self.session.query(func.count(TaskTable.id))
        if not include_deleted:
            query = query.filter(TaskTable.deleted_at.is_(None))
        if status:
            query = query.filter(TaskTable.status == status)
        if q:
            query = query.filter(TaskTable.topic.ilike(f"%{q}%"))
        return query.scalar() or 0

    # ------------------------------------------------------------------
    # Task Management
    # ------------------------------------------------------------------

    def rename_task(self, task_id: str, topic: str, canonical_topic: str | None = None) -> TaskTable | None:
        """重命名任务。返回更新后的 row，不存在返回 None。"""
        row = self.session.get(TaskTable, task_id)
        if not row:
            return None
        row.topic = topic
        if canonical_topic is not None:
            row.canonical_topic = canonical_topic
        row.renamed_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        return row

    def soft_delete_task(self, task_id: str) -> TaskTable | None:
        """软删除任务。返回更新后的 row，不存在返回 None。"""
        row = self.session.get(TaskTable, task_id)
        if not row:
            return None
        row.deleted_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        return row

    def restore_task(self, task_id: str) -> TaskTable | None:
        """恢复已软删除的任务。"""
        row = self.session.get(TaskTable, task_id)
        if not row:
            return None
        row.deleted_at = None
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        return row

    def hard_delete_task(self, task_id: str) -> bool:
        """硬删除任务及其关联数据。返回是否成功。"""
        row = self.session.get(TaskTable, task_id)
        if not row:
            return False
        # 删除关联数据
        self.session.query(SourceTable).filter(SourceTable.task_id == task_id).delete()
        self.session.query(QueryTable).filter(QueryTable.task_id == task_id).delete()
        # 删除 extracted documents（通过 source_item_id 关联）
        source_ids = [
            s.id for s in self.session.query(SourceTable.id).filter(SourceTable.task_id == task_id).all()
        ]
        if source_ids:
            self.session.query(ExtractedTable).filter(
                ExtractedTable.source_item_id.in_(source_ids)
            ).delete(synchronize_session=False)
        # 删除 task events
        from db.tables import TaskEventTable
        self.session.query(TaskEventTable).filter(TaskEventTable.task_id == task_id).delete()
        # 删除任务本身
        self.session.delete(row)
        self.session.commit()
        return True

    def clone_task(self, task_id: str, topic_override: str | None = None) -> TaskTable | None:
        """复制任务配置，创建新任务。不复制 sources/documents/trace。"""
        from uuid import uuid4

        row = self.session.get(TaskTable, task_id)
        if not row:
            return None

        new_id = str(uuid4())
        new_row = TaskTable(
            id=new_id,
            task_type=row.task_type,
            topic=topic_override or row.topic,
            canonical_topic=row.canonical_topic,
            mode=row.mode,
            language=row.language,
            depth=row.depth,
            include_gossip=row.include_gossip,
            include_books=row.include_books,
            include_video=row.include_video,
            status=TaskStatus.PENDING,
            obsidian_path=row.obsidian_path,
            user_language=row.user_language,
            working_language=row.working_language,
            output_language=row.output_language,
            search_strategy=row.search_strategy,
            cloned_from_task_id=task_id,
            metadata_json=row.metadata_json,
        )
        self.session.add(new_row)
        self.session.commit()
        return new_row

    # ------------------------------------------------------------------
    # Report Ingestion
    # ------------------------------------------------------------------

    def create_report_ingestion_task(
        self,
        request: ImportedReportCreate,
        task_id: str | None = None,
        reports_dir: Path | None = None,
    ) -> ResearchTask:
        """创建报告导入任务，保存 report_text 到文件，元数据存入 metadata_json。"""
        from uuid import uuid4

        _task_id = task_id or str(uuid4())
        _reports_dir = reports_dir or _IMPORTED_REPORTS_DIR

        # 保存 report_text 到文件
        report_path = self.save_imported_report_text(
            _task_id, request.report_text, reports_dir=_reports_dir
        )

        # 构建 metadata
        metadata = {
            "report_source": request.report_source,
            "report_text_path": str(report_path),
            "output_language": request.output_language,
            "options": request.options.model_dump(),
        }

        row = TaskTable(
            id=_task_id,
            task_type=ResearchTaskType.REPORT_INGESTION,
            topic=request.topic,
            status=TaskStatus.PENDING,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        self.session.add(row)
        self.session.commit()

        return ResearchTask(
            id=_task_id,
            task_type=ResearchTaskType.REPORT_INGESTION,
            topic=request.topic,
            status=TaskStatus.PENDING,
        )

    def save_imported_report_text(
        self,
        task_id: str,
        report_text: str,
        reports_dir: Path | None = None,
    ) -> Path:
        """保存 report_text 到文件，返回文件路径。"""
        _dir = reports_dir or _IMPORTED_REPORTS_DIR
        _dir.mkdir(parents=True, exist_ok=True)
        file_path = _dir / f"{task_id}.md"
        file_path.write_text(report_text, encoding="utf-8")
        return file_path

    def load_imported_report_text(
        self,
        task_id: str,
        reports_dir: Path | None = None,
    ) -> str | None:
        """从文件加载 report_text，不存在返回 None。"""
        _dir = reports_dir or _IMPORTED_REPORTS_DIR
        file_path = _dir / f"{task_id}.md"
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return None

    def get_imported_report_metadata(self, task_id: str) -> dict:
        """获取导入报告的元数据。"""
        row = self.session.get(TaskTable, task_id)
        if not row:
            return {}
        try:
            return json.loads(row.metadata_json) if row.metadata_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class SourceRepository:
    """来源 CRUD。"""

    def __init__(self, session: Session):
        self.session = session

    def bulk_create(self, sources: list[dict]) -> int:
        rows = [SourceTable(**s) for s in sources]
        self.session.add_all(rows)
        self.session.commit()
        return len(rows)

    def get_by_task(self, task_id: str) -> list[SourceTable]:
        return (
            self.session.query(SourceTable)
            .filter(SourceTable.task_id == task_id)
            .all()
        )

    def count_by_task(self, task_id: str) -> int:
        return (
            self.session.query(func.count(SourceTable.id))
            .filter(SourceTable.task_id == task_id)
            .scalar() or 0
        )

    def count_high_quality(self, task_id: str) -> int:
        return (
            self.session.query(func.count(SourceTable.id))
            .filter(SourceTable.task_id == task_id)
            .filter(SourceTable.source_level.in_(["S", "A"]))
            .scalar() or 0
        )

    def count_extracted(self, task_id: str) -> int:
        return (
            self.session.query(func.count(SourceTable.id))
            .filter(SourceTable.task_id == task_id)
            .filter(SourceTable.download_status.in_(["extracted", "exported"]))
            .scalar() or 0
        )

    def update_download_status(self, source_id: str, status: str) -> None:
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
            .filter(ExtractedTable.source_item_id == source_id)
            .first()
        )
