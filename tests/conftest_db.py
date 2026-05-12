"""共享测试 fixture：向 DB 注入测试任务。"""

from db.repositories import TaskRepository, SourceRepository
from db.session import get_session


def inject_task_to_db(task_id: str, topic: str, status: str = "completed", **kwargs):
    """向 DB 注入测试任务。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        # 检查是否已存在
        if repo.get_task(task_id):
            return
        repo.create_task(task_id=task_id, topic=topic, **kwargs)
        if status != "pending":
            repo.update_task_status(task_id, status)
    finally:
        session.close()


def remove_task_from_db(task_id: str):
    """从 DB 删除测试任务。"""
    from db.tables import TaskTable, SourceTable
    session = get_session()
    try:
        session.query(SourceTable).filter(SourceTable.task_id == task_id).delete()
        session.query(TaskTable).filter(TaskTable.id == task_id).delete()
        session.commit()
    finally:
        session.close()


def inject_sources_to_db(task_id: str, sources: list[dict]):
    """向 DB 注入测试 sources。"""
    session = get_session()
    try:
        repo = SourceRepository(session)
        repo.bulk_create(sources)
    finally:
        session.close()
