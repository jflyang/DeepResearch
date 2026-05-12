"""研究任务路由。"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from models.enums import TaskMode, TaskStatus
from services.research_service import (
    CreateResearchTaskRequest,
    ResearchResultSummary,
    ResearchService,
)
from services.result_classification_service import classify_results

logger = logging.getLogger(__name__)

router = APIRouter()

# 内存存储（MVP，未来替换为 DB repository）
_tasks: dict[str, dict] = {}
_source_items: dict[str, list] = {}


class CreateTaskRequest(BaseModel):
    topic: str
    mode: str = "auto"
    depth: str = "standard"
    include_gossip: bool = False
    include_books: bool = True
    include_video: bool = False
    obsidian_path: str = ""


class CreateTaskResponse(BaseModel):
    task_id: str
    status: str


@router.post("/tasks", response_model=CreateTaskResponse)
async def create_task(request: CreateTaskRequest):
    """创建研究任务。"""
    service = ResearchService()
    task = service.create_task(CreateResearchTaskRequest(
        topic=request.topic,
        mode=TaskMode(request.mode),
        depth=request.depth,
        include_gossip=request.include_gossip,
        include_books=request.include_books,
        include_video=request.include_video,
    ))

    # 存储任务和 obsidian_path
    _tasks[task.id] = {
        "task": task,
        "obsidian_path": request.obsidian_path,
    }

    return CreateTaskResponse(task_id=task.id, status=task.status.value)


@router.post("/tasks/{task_id}/run")
async def run_research(task_id: str):
    """运行初始研究。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = _tasks[task_id]
    task = task_data["task"]

    if task.status not in (TaskStatus.PENDING, TaskStatus.FAILED):
        raise HTTPException(status_code=400, detail=f"Task already in status: {task.status}")

    service = ResearchService()
    summary = await service.run_initial_research(task)

    # 存储 source_items（从 service 内部获取）
    # MVP: 重新运行 pipeline 获取 items 不理想，但保持简单
    _tasks[task_id]["summary"] = summary.model_dump()

    return summary.model_dump()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务状态。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]["task"]
    return {
        "task_id": task.id,
        "topic": task.topic,
        "mode": task.mode.value,
        "status": task.status.value,
        "expanded_queries": task.expanded_queries,
        "created_at": task.created_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.get("/tasks/{task_id}/sources")
async def get_sources(task_id: str):
    """返回分类后的 sources。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]["task"]
    items = _source_items.get(task_id, [])

    if not items:
        return {"task_id": task_id, "categories": {}, "total": 0}

    classified = classify_results(items, mode=task.mode)
    # 序列化
    result = {}
    for cat, cat_items in classified.items():
        result[cat] = [
            {
                "id": item.id,
                "title": item.title,
                "url": item.url,
                "source_level": item.source_level.value,
                "source_type": item.source_type.value,
                "reason_to_read": item.reason_to_read,
                "download_status": item.download_status.value,
            }
            for item in cat_items
        ]

    return {"task_id": task_id, "categories": result, "total": len(items)}


@router.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str, limit: int = 50):
    """获取任务事件日志。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    from services.task_event_service import get_events

    events = get_events(task_id, limit=limit)
    return {
        "task_id": task_id,
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "message": e.message,
                "level": e.level,
                "payload": e.payload,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }
