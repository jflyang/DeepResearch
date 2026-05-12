"""任务队列路由 - 批量提交、队列管理、worker 控制。"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.task_queue_service import get_queue_service

logger = logging.getLogger(__name__)

router = APIRouter()


class EnqueueRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1)
    priority: int = 100


class BatchCreateRequest(BaseModel):
    """批量创建并入队。"""

    topics: list[str] = Field(min_length=1)
    mode: str = "auto"
    depth: str = "standard"
    include_gossip: bool = False
    include_books: bool = True
    include_video: bool = False
    obsidian_path: str = ""
    priority: int = 100


@router.get("/tasks/queue")
async def get_queue_status():
    """获取队列状态。"""
    service = get_queue_service()
    status = service.get_queue_status()
    return {
        "running": status.running.model_dump(mode="json") if status.running else None,
        "queued": [item.model_dump(mode="json") for item in status.queued],
        "completed_recent": [item.model_dump(mode="json") for item in status.completed_recent],
        "failed_recent": [item.model_dump(mode="json") for item in status.failed_recent],
        "total_queued": status.total_queued,
        "total_completed": status.total_completed,
        "total_failed": status.total_failed,
        "worker_running": status.worker_running,
    }


@router.post("/tasks/enqueue")
async def enqueue_tasks(request: EnqueueRequest):
    """将已创建的任务加入队列。"""
    service = get_queue_service()
    items = service.enqueue_many(request.task_ids, priority=request.priority)
    return {
        "enqueued": len(items),
        "items": [item.model_dump(mode="json") for item in items],
    }


@router.post("/tasks/batch-create")
async def batch_create_and_enqueue(request: BatchCreateRequest):
    """批量创建研究任务并加入队列。"""
    from db.repositories import TaskRepository
    from db.session import get_session
    from models.enums import TaskMode, TaskStatus
    from services.research_service import CreateResearchTaskRequest, ResearchService

    service = ResearchService()
    queue_service = get_queue_service()
    created_task_ids = []

    for topic in request.topics:
        topic = topic.strip()
        if not topic:
            continue

        # 创建任务
        task = service.create_task(CreateResearchTaskRequest(
            topic=topic,
            mode=TaskMode(request.mode),
            depth=request.depth,
            include_gossip=request.include_gossip,
            include_books=request.include_books,
            include_video=request.include_video,
        ))

        # 持久化到 DB
        session = get_session()
        try:
            repo = TaskRepository(session)
            repo.create_task(
                task_id=task.id,
                topic=task.topic,
                mode=task.mode.value,
                depth=task.depth if hasattr(task, 'depth') else "standard",
                include_gossip=task.include_gossip,
                include_books=task.include_books,
                include_video=task.include_video,
                obsidian_path=request.obsidian_path,
            )
        finally:
            session.close()

        created_task_ids.append(task.id)

    # 批量入队
    items = queue_service.enqueue_many(created_task_ids, priority=request.priority)

    # 自动启动 worker（如果未运行）
    if not queue_service.worker_running:
        asyncio.create_task(_start_worker_background())

    return {
        "created": len(created_task_ids),
        "enqueued": len(items),
        "task_ids": created_task_ids,
        "items": [item.model_dump(mode="json") for item in items],
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消排队中的任务。"""
    service = get_queue_service()
    success = service.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法取消：任务不在队列中或已在执行")
    return {"task_id": task_id, "status": "cancelled"}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    """重试失败的任务。"""
    service = get_queue_service()
    item = service.retry_task(task_id)
    if not item:
        raise HTTPException(status_code=400, detail="无法重试：任务不存在或不是失败状态")

    # 确保 worker 在运行
    if not service.worker_running:
        asyncio.create_task(_start_worker_background())

    return {"task_id": task_id, "status": "queued", "message": "已重新加入队列"}


@router.get("/tasks/{task_id}/queue-status")
async def get_task_queue_status(task_id: str):
    """获取单个任务的队列状态。"""
    from services.task_queue_service import get_queue_repo

    repo = get_queue_repo()
    item = repo.get_by_task_id(task_id)
    if not item:
        return {"task_id": task_id, "in_queue": False}
    return {
        "task_id": task_id,
        "in_queue": True,
        "queue_status": item.status,
        "priority": item.priority,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "error_message": item.error_message,
    }


@router.post("/tasks/worker/start")
async def start_worker():
    """启动队列 worker。"""
    service = get_queue_service()
    if service.worker_running:
        return {"status": "already_running"}

    asyncio.create_task(_start_worker_background())
    return {"status": "started"}


@router.post("/tasks/worker/stop")
async def stop_worker():
    """停止队列 worker。"""
    service = get_queue_service()
    service.stop_worker()
    return {"status": "stopped"}


async def _start_worker_background():
    """后台启动 worker。"""
    service = get_queue_service()
    await service.start_worker()
