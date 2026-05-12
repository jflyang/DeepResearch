"""任务队列服务 - 批量研究任务排队与逐个执行。

MVP：单 worker，FIFO + priority，SQLite 持久化，不引入 Celery/Redis。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# === 数据模型 ===


class TaskQueueItem(BaseModel):
    """队列项。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    task_type: str = "search_research"
    status: str = "queued"  # queued / running / completed / failed / cancelled
    priority: int = 100  # 越小越优先
    queue_name: str = "default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str = ""
    metadata_json: str = "{}"


class QueueStatus(BaseModel):
    """队列状态摘要。"""

    running: TaskQueueItem | None = None
    queued: list[TaskQueueItem] = Field(default_factory=list)
    completed_recent: list[TaskQueueItem] = Field(default_factory=list)
    failed_recent: list[TaskQueueItem] = Field(default_factory=list)
    total_queued: int = 0
    total_completed: int = 0
    total_failed: int = 0
    worker_running: bool = False


# === 队列存储（SQLite 持久化） ===


class TaskQueueRepository:
    """队列持久化 - 使用内存 + SQLite 双层。

    MVP 阶段使用内存列表 + 文件持久化，避免修改 DB schema。
    """

    def __init__(self):
        self._items: list[TaskQueueItem] = []
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """从磁盘加载队列状态。"""
        import json
        from pathlib import Path

        queue_file = Path("data/task_queue.json")
        if not queue_file.exists():
            return
        try:
            data = json.loads(queue_file.read_text(encoding="utf-8"))
            self._items = [TaskQueueItem(**item) for item in data]
        except Exception as e:
            logger.warning("task_queue_load_failed error=%s", str(e)[:100])

    def _save_to_disk(self) -> None:
        """保存队列状态到磁盘。"""
        import json
        from pathlib import Path

        queue_file = Path("data/task_queue.json")
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = [item.model_dump(mode="json") for item in self._items]
            queue_file.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning("task_queue_save_failed error=%s", str(e)[:100])

    def add(self, item: TaskQueueItem) -> TaskQueueItem:
        """添加队列项。"""
        self._items.append(item)
        self._save_to_disk()
        return item

    def get(self, item_id: str) -> TaskQueueItem | None:
        """按 ID 获取。"""
        return next((i for i in self._items if i.id == item_id), None)

    def get_by_task_id(self, task_id: str) -> TaskQueueItem | None:
        """按 task_id 获取。"""
        return next((i for i in self._items if i.task_id == task_id), None)

    def get_running(self) -> TaskQueueItem | None:
        """获取当前正在运行的任务。"""
        return next((i for i in self._items if i.status == "running"), None)

    def get_pending(self, limit: int = 100) -> list[TaskQueueItem]:
        """获取等待中的任务（按 priority ASC, created_at ASC）。"""
        queued = [i for i in self._items if i.status == "queued"]
        queued.sort(key=lambda x: (x.priority, x.created_at))
        return queued[:limit]

    def get_completed(self, limit: int = 10) -> list[TaskQueueItem]:
        """获取最近完成的任务。"""
        completed = [i for i in self._items if i.status == "completed"]
        completed.sort(key=lambda x: x.completed_at or x.created_at, reverse=True)
        return completed[:limit]

    def get_failed(self, limit: int = 10) -> list[TaskQueueItem]:
        """获取最近失败的任务。"""
        failed = [i for i in self._items if i.status == "failed"]
        failed.sort(key=lambda x: x.completed_at or x.created_at, reverse=True)
        return failed[:limit]

    def update_status(self, item_id: str, status: str, **kwargs) -> TaskQueueItem | None:
        """更新队列项状态。"""
        item = self.get(item_id)
        if not item:
            return None
        item.status = status
        if status == "running":
            item.started_at = datetime.now(UTC)
        if status in ("completed", "failed", "cancelled"):
            item.completed_at = datetime.now(UTC)
        if "error_message" in kwargs:
            item.error_message = kwargs["error_message"]
        self._save_to_disk()
        return item

    def count_by_status(self, status: str) -> int:
        """按状态计数。"""
        return len([i for i in self._items if i.status == status])

    def remove(self, item_id: str) -> bool:
        """移除队列项。"""
        before = len(self._items)
        self._items = [i for i in self._items if i.id != item_id]
        if len(self._items) < before:
            self._save_to_disk()
            return True
        return False


# === 全局队列仓库单例 ===

_queue_repo: TaskQueueRepository | None = None


def get_queue_repo() -> TaskQueueRepository:
    """获取全局队列仓库。"""
    global _queue_repo
    if _queue_repo is None:
        _queue_repo = TaskQueueRepository()
    return _queue_repo


def reset_queue_repo() -> None:
    """重置队列仓库（仅测试用）。"""
    global _queue_repo
    _queue_repo = None


# === TaskQueueService ===


class TaskQueueService:
    """任务队列服务。"""

    def __init__(self, repo: TaskQueueRepository | None = None):
        self._repo = repo or get_queue_repo()
        self._worker_running = False
        self._worker_task: asyncio.Task | None = None

    def enqueue_task(
        self,
        task_id: str,
        task_type: str = "search_research",
        priority: int = 100,
        queue_name: str = "default",
    ) -> TaskQueueItem:
        """将任务加入队列。"""
        # 检查是否已在队列中
        existing = self._repo.get_by_task_id(task_id)
        if existing and existing.status in ("queued", "running"):
            return existing

        item = TaskQueueItem(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            queue_name=queue_name,
        )
        self._repo.add(item)
        logger.info("task_enqueued task_id=%s priority=%d", task_id, priority)
        return item

    def enqueue_many(
        self,
        task_ids: list[str],
        task_type: str = "search_research",
        priority: int = 100,
    ) -> list[TaskQueueItem]:
        """批量入队。"""
        items = []
        for i, task_id in enumerate(task_ids):
            # 按顺序递增 priority 保持 FIFO
            item = self.enqueue_task(task_id, task_type, priority=priority + i)
            items.append(item)
        return items

    def get_queue_status(self, queue_name: str = "default") -> QueueStatus:
        """获取队列状态。"""
        return QueueStatus(
            running=self._repo.get_running(),
            queued=self._repo.get_pending(),
            completed_recent=self._repo.get_completed(),
            failed_recent=self._repo.get_failed(),
            total_queued=self._repo.count_by_status("queued"),
            total_completed=self._repo.count_by_status("completed"),
            total_failed=self._repo.count_by_status("failed"),
            worker_running=self._worker_running,
        )

    def get_current_running(self) -> TaskQueueItem | None:
        """获取当前正在运行的任务。"""
        return self._repo.get_running()

    def get_pending(self, limit: int = 100) -> list[TaskQueueItem]:
        """获取等待中的任务。"""
        return self._repo.get_pending(limit)

    def cancel_task(self, task_id: str) -> bool:
        """取消排队中的任务。只能取消 queued 状态的。"""
        item = self._repo.get_by_task_id(task_id)
        if not item:
            return False
        if item.status != "queued":
            return False
        self._repo.update_status(item.id, "cancelled")
        logger.info("task_cancelled task_id=%s", task_id)
        return True

    def retry_task(self, task_id: str) -> TaskQueueItem | None:
        """重试失败的任务。"""
        item = self._repo.get_by_task_id(task_id)
        if not item:
            return None
        if item.status != "failed":
            return None
        # 重置状态为 queued
        self._repo.update_status(item.id, "queued", error_message="")
        item.started_at = None
        item.completed_at = None
        self._repo._save_to_disk()
        logger.info("task_retried task_id=%s", task_id)
        return item

    async def run_next(self) -> TaskQueueItem | None:
        """执行队列中下一个任务。返回执行的 item，无任务返回 None。"""
        # 检查是否有正在运行的
        running = self._repo.get_running()
        if running:
            logger.debug("queue_busy running_task_id=%s", running.task_id)
            return None

        # 获取下一个
        pending = self._repo.get_pending(limit=1)
        if not pending:
            return None

        item = pending[0]
        self._repo.update_status(item.id, "running")
        logger.info("task_dequeued task_id=%s", item.task_id)

        try:
            await self._execute_task(item)
            self._repo.update_status(item.id, "completed")
            logger.info("task_queue_completed task_id=%s", item.task_id)
        except Exception as e:
            error_msg = str(e)[:500]
            self._repo.update_status(item.id, "failed", error_message=error_msg)
            logger.warning("task_queue_failed task_id=%s error=%s", item.task_id, error_msg[:100])

        return item

    async def _execute_task(self, item: TaskQueueItem) -> None:
        """执行单个任务 - 调用完整研究流程。"""
        from api.routes_research import _run_research_background
        from db.repositories import TaskRepository
        from db.session import get_session
        from models.enums import TaskMode, TaskStatus
        from models.schemas import ResearchTask

        # 从 DB 加载任务
        session = get_session()
        try:
            repo = TaskRepository(session)
            row = repo.get_task(item.task_id)
            if not row:
                raise ValueError(f"Task not found: {item.task_id}")

            # 标记为 running
            repo.update_task_status(item.task_id, TaskStatus.RUNNING)

            task = ResearchTask(
                id=row.id,
                topic=row.topic,
                mode=TaskMode(row.mode),
                depth=row.depth,
                include_gossip=row.include_gossip,
                include_books=row.include_books,
                include_video=row.include_video,
                status=TaskStatus.PENDING,
            )
        finally:
            session.close()

        # 执行研究（直接 await，不创建后台 task）
        await _run_research_background(item.task_id, task)

        # 检查任务最终状态
        session = get_session()
        try:
            repo = TaskRepository(session)
            row = repo.get_task(item.task_id)
            if row and row.status == TaskStatus.FAILED:
                raise RuntimeError(row.error_message or "Task failed")
        finally:
            session.close()

    async def worker_tick(self) -> bool:
        """Worker 单次循环。返回是否执行了任务。"""
        result = await self.run_next()
        return result is not None

    async def start_worker(self) -> None:
        """启动 worker 循环。"""
        if self._worker_running:
            logger.info("worker_already_running")
            return

        self._worker_running = True
        logger.info("task_queue_worker_started")

        try:
            while self._worker_running:
                executed = await self.worker_tick()
                if not executed:
                    # 没有任务，等待 3 秒再检查
                    await asyncio.sleep(3)
                else:
                    # 执行完一个，立即检查下一个
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            self._worker_running = False
            logger.info("task_queue_worker_stopped")

    def stop_worker(self) -> None:
        """停止 worker。"""
        self._worker_running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        logger.info("task_queue_worker_stop_requested")

    @property
    def worker_running(self) -> bool:
        return self._worker_running


# === 全局 service 单例 ===

_queue_service: TaskQueueService | None = None


def get_queue_service() -> TaskQueueService:
    """获取全局队列服务。"""
    global _queue_service
    if _queue_service is None:
        _queue_service = TaskQueueService()
    return _queue_service


def reset_queue_service() -> None:
    """重置队列服务（仅测试用）。"""
    global _queue_service
    if _queue_service:
        _queue_service.stop_worker()
    _queue_service = None
