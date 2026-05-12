"""研究任务路由。"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
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


@router.get("/tasks")
async def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
):
    """列出研究任务（按创建时间倒序）。"""
    # 从内存存储构建列表
    all_tasks = []
    for task_id, task_data in _tasks.items():
        t = task_data["task"]
        # 状态过滤
        if status and t.status.value != status:
            continue
        # 主题搜索
        if q and q.lower() not in t.topic.lower():
            continue

        # 计算来源统计
        items = _source_items.get(task_id, [])
        source_count = len(items)
        high_quality_count = sum(1 for i in items if i.source_level.value in ("S", "A"))
        extracted_count = sum(1 for i in items if i.download_status.value in ("extracted", "exported"))

        # 导出状态（从 task_data 推断）
        exported = bool(task_data.get("exported"))
        export_path = task_data.get("export_path")

        all_tasks.append({
            "task_id": t.id,
            "topic": t.topic,
            "mode": t.mode.value,
            "status": t.status.value,
            "depth": t.depth if hasattr(t, 'depth') else "standard",
            "created_at": t.created_at.isoformat(),
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "source_count": source_count,
            "high_quality_count": high_quality_count,
            "extracted_count": extracted_count,
            "exported": exported,
            "export_path": export_path,
        })

    # 按创建时间倒序
    all_tasks.sort(key=lambda x: x["created_at"], reverse=True)

    # 分页
    total = len(all_tasks)
    paginated = all_tasks[offset:offset + limit]

    return {
        "items": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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

    # 存储 source_items 到内存（供 GET /sources 和 export 使用）
    _source_items[task_id] = getattr(service, "last_source_items", [])
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
    """返回分类后的 sources（含完整字段供 UI 展示）。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]["task"]
    items = _source_items.get(task_id, [])

    if not items:
        return {"task_id": task_id, "categories": {}, "total": 0, "items": []}

    classified = classify_results(items, mode=task.mode)
    # 序列化分类结果
    result = {}
    for cat, cat_items in classified.items():
        result[cat] = [_serialize_source(item) for item in cat_items]

    # 同时返回全部 items 的完整列表（用于筛选/排序）
    all_items = [_serialize_source(item) for item in items]

    return {"task_id": task_id, "categories": result, "total": len(items), "items": all_items}


def _serialize_source(item: "SourceItem") -> dict:
    """序列化 SourceItem 为完整字典。"""
    from models.schemas import SourceItem as _SI
    return {
        "id": item.id,
        "title": item.title,
        "url": item.url,
        "domain": item.domain,
        "snippet": item.snippet,
        "source_level": item.source_level.value,
        "source_type": item.source_type.value,
        "relevance_score": item.relevance_score,
        "authority_score": item.authority_score,
        "originality_score": item.originality_score,
        "gossip_score": item.gossip_score,
        "downloadable": item.downloadable,
        "download_status": item.download_status.value,
        "reason_to_read": item.reason_to_read,
        "query_language": item.query_language.value if item.query_language else None,
        "source_language": item.source_language.value if item.source_language else None,
        "matched_query": item.matched_query,
    }


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


@router.get("/tasks/{task_id}/trace")
async def get_task_trace(task_id: str, level: str | None = None, phase: str | None = None, limit: int = 500):
    """获取任务执行轨迹。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    from app.tracing.recorder import get_recorder

    recorder = get_recorder()
    events = recorder.get_events(task_id, limit=limit, level=level, phase=phase)
    return {
        "task_id": task_id,
        "events": [e.model_dump(mode="json") for e in events],
    }


@router.get("/tasks/{task_id}/trace/summary")
async def get_task_trace_summary(task_id: str):
    """获取任务执行轨迹摘要。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    from app.tracing.recorder import get_recorder

    recorder = get_recorder()
    return recorder.get_summary(task_id)


@router.get("/tasks/{task_id}/trace/llm")
async def get_task_trace_llm(task_id: str):
    """获取任务 LLM 使用详情。"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    from app.tracing.llm_registry import get_all_task_info, RULE_ONLY_STEPS
    from app.tracing.models import TraceStep
    from app.tracing.recorder import get_recorder
    from core.config import get_settings

    settings = get_settings()
    recorder = get_recorder()
    events = recorder.get_events(task_id, limit=1000)

    # 收集 LLM 调用信息
    llm_calls = [e for e in events if e.step == TraceStep.LLM_CALL_FINISHED]
    llm_failures = [e for e in events if e.step == TraceStep.LLM_CALL_FAILED]

    # 构建每个 task 的状态
    all_task_info = get_all_task_info()
    llm_tasks_status = []

    # 已调用的 task names
    called_tasks = set()
    for e in llm_calls:
        task_name = (e.output_summary or {}).get("task_name") or (e.input_summary or {}).get("task_name", "")
        if task_name:
            called_tasks.add(task_name)
            llm_tasks_status.append({
                "task_name": task_name,
                "stage": next((t.stage for t in all_task_info if t.task_name == task_name), "unknown"),
                "status": "used_llm",
                "provider": e.provider,
                "model": e.model,
                "prompt_template": next((t.prompt_template for t in all_task_info if t.task_name == task_name), ""),
                "input_chars": (e.output_summary or {}).get("input_chars"),
                "output_chars": (e.output_summary or {}).get("output_chars"),
                "duration_ms": e.duration_ms,
            })

    for e in llm_failures:
        task_name = (e.input_summary or {}).get("task_name", "")
        if task_name and task_name not in called_tasks:
            called_tasks.add(task_name)
            llm_tasks_status.append({
                "task_name": task_name,
                "stage": next((t.stage for t in all_task_info if t.task_name == task_name), "unknown"),
                "status": "fallback",
                "provider": e.provider,
                "model": e.model,
                "error_message": e.error_message,
                "fallback_used": True,
                "fallback_name": next((t.fallback for t in all_task_info if t.task_name == task_name), ""),
            })

    # 未调用的 tasks
    for info in all_task_info:
        if info.task_name in called_tasks:
            continue
        if not info.implemented:
            llm_tasks_status.append({
                "task_name": info.task_name,
                "stage": info.stage,
                "status": "skipped_not_implemented",
                "skipped_reason": "当前版本未实现",
            })
        elif not info.enabled:
            llm_tasks_status.append({
                "task_name": info.task_name,
                "stage": info.stage,
                "status": "skipped_disabled",
                "skipped_reason": f"{info.task_name}.enabled=false",
                "fallback_name": info.fallback,
            })
        else:
            llm_tasks_status.append({
                "task_name": info.task_name,
                "stage": info.stage,
                "status": "skipped_not_reached",
                "skipped_reason": "流程未到达该阶段",
            })

    return {
        "task_id": task_id,
        "active_provider": settings.active_llm_provider,
        "active_model": settings.ollama_default_model if settings.active_llm_provider == "ollama_lan" else settings.deepseek_default_model,
        "llm_call_count": len(llm_calls),
        "llm_tasks": llm_tasks_status,
        "rule_only_steps": RULE_ONLY_STEPS,
    }
