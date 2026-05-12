"""研究任务路由 - 使用 SQLite 持久化。"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.repositories import SourceRepository, TaskRepository
from db.session import get_session
from models.enums import TaskMode, TaskStatus
from services.research_service import (
    CreateResearchTaskRequest,
    ResearchResultSummary,
    ResearchService,
)
from services.result_classification_service import classify_results

logger = logging.getLogger(__name__)

router = APIRouter()

# 内存缓存：source_items（研究完成后的 SourceItem 对象，用于分类和导出）
# 这些对象在 DB 中也有持久化（SourceTable），但分类需要 Pydantic 模型
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
    """创建研究任务（持久化到 DB）。"""
    service = ResearchService()
    task = service.create_task(CreateResearchTaskRequest(
        topic=request.topic,
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

    return CreateTaskResponse(task_id=task.id, status=task.status.value)


@router.post("/tasks/{task_id}/run")
async def run_research(task_id: str):
    """运行初始研究（后台执行，立即返回 running 状态）。"""
    import asyncio

    # 从 DB 加载任务
    session = get_session()
    try:
        repo = TaskRepository(session)
        row = repo.get_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        if row.status not in (TaskStatus.PENDING, TaskStatus.FAILED):
            raise HTTPException(status_code=400, detail=f"Task already in status: {row.status}")

        # 读取所有需要的字段（避免 session 关闭后 DetachedInstanceError）
        task_topic = row.topic
        task_mode = row.mode
        task_depth = row.depth
        task_include_gossip = row.include_gossip
        task_include_books = row.include_books
        task_include_video = row.include_video

        # 立即标记为 running
        repo.update_task_status(task_id, TaskStatus.RUNNING)
    finally:
        session.close()

    # 构建 ResearchTask pydantic 模型
    from models.schemas import ResearchTask
    task = ResearchTask(
        id=task_id,
        topic=task_topic,
        mode=TaskMode(task_mode),
        depth=task_depth,
        include_gossip=task_include_gossip,
        include_books=task_include_books,
        include_video=task_include_video,
        status=TaskStatus.PENDING,
    )

    # 启动后台任务
    asyncio.create_task(_run_research_background(task_id, task))

    return {"task_id": task_id, "status": "running", "message": "研究任务已启动"}


async def _run_research_background(task_id: str, task):
    """后台执行研究流程，持续写 trace。"""
    import logging
    _logger = logging.getLogger(__name__)

    try:
        # 创建 AI Gateway
        ai_gateway = _create_ai_gateway()

        service = ResearchService(ai_gateway=ai_gateway)
        summary = await service.run_initial_research(task)

        # 保存 source_items 到内存缓存
        source_items = getattr(service, "last_source_items", [])
        _source_items[task_id] = source_items

        # 持久化结果到 DB
        session = get_session()
        try:
            repo = TaskRepository(session)
            repo.mark_completed(
                task_id=task_id,
                source_count=len(source_items),
                expanded_queries=task.expanded_queries,
            )

            # 保存 sources 到 DB
            src_repo = SourceRepository(session)
            source_dicts = []
            for item in source_items:
                source_dicts.append({
                    "id": item.id,
                    "task_id": item.task_id,
                    "title": item.title,
                    "url": item.url,
                    "domain": item.domain,
                    "snippet": item.snippet,
                    "source_type": item.source_type.value,
                    "source_level": item.source_level.value,
                    "relevance_score": item.relevance_score,
                    "authority_score": item.authority_score,
                    "originality_score": item.originality_score,
                    "gossip_score": item.gossip_score,
                    "downloadable": item.downloadable,
                    "download_status": item.download_status.value,
                    "reason_to_read": item.reason_to_read,
                })
            if source_dicts:
                src_repo.bulk_create(source_dicts)
        finally:
            session.close()

        # === Auto Fetch & Export ===
        await _run_auto_fetch_export(task_id, task, source_items, ai_gateway)

    except Exception as e:
        _logger.error("background_research_failed task_id=%s error=%s", task_id, str(e))
        # 标记任务失败
        session = get_session()
        try:
            repo = TaskRepository(session)
            repo.update_task_status(task_id, TaskStatus.FAILED, error_message=str(e)[:500])
        finally:
            session.close()

        # 写 trace
        from app.tracing.recorder import get_recorder
        from app.tracing.models import TraceStep, TracePhase
        get_recorder().error(
            task_id, TraceStep.TASK_FAILED, TracePhase.PROCESSING,
            message=f"Research failed: {str(e)[:200]}",
            error_message=str(e)[:500],
        )


async def _run_auto_fetch_export(task_id: str, task, source_items, ai_gateway):
    """执行自动抓取与导出（不影响主任务状态）。"""
    _logger = logging.getLogger(__name__)

    try:
        from services.auto_fetch_service import AutoFetchExportService

        auto_service = AutoFetchExportService(ai_gateway=ai_gateway)
        result = await auto_service.run(task=task, sources=source_items)

        _logger.info(
            "auto_fetch_export_completed task_id=%s fetched=%d failed=%d exported=%s",
            task_id, result.fetched_count, result.failed_count, result.exported,
        )

        # 更新 DB 中的 source download_status
        if result.fetched_count > 0:
            session = get_session()
            try:
                src_repo = SourceRepository(session)
                for source_id, doc in result.extracted_docs.items():
                    if doc.content:
                        src_repo.update_download_status(source_id, "extracted")
            finally:
                session.close()

    except Exception as e:
        # 自动抓取失败不影响主任务
        _logger.warning(
            "auto_fetch_export_failed task_id=%s error=%s",
            task_id, str(e)[:200],
        )


def _create_ai_gateway():
    """创建 AI Gateway 实例（如果 LLM 配置可用）。"""
    try:
        from core.config import get_settings
        settings = get_settings()
        if not settings.enable_llm:
            return None

        from app.ai.gateway import AIGateway
        from app.ai.prompts import PromptStore
        from app.ai.router import LLMRouter

        router = LLMRouter()
        prompt_store = PromptStore()
        return AIGateway(router=router, prompt_store=prompt_store)
    except Exception:
        return None


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务状态（从 DB 读取）。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        row = repo.get_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        expanded = []
        try:
            expanded = json.loads(row.expanded_queries) if row.expanded_queries else []
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "task_id": row.id,
            "task_type": getattr(row, "task_type", "search_research"),
            "topic": row.topic,
            "canonical_topic": row.canonical_topic or "",
            "mode": row.mode,
            "status": row.status,
            "depth": row.depth,
            "expanded_queries": expanded,
            "source_count": row.source_count,
            "exported": row.exported,
            "export_path": row.export_path or None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
    finally:
        session.close()


@router.get("/tasks/{task_id}/sources")
async def get_sources(task_id: str):
    """返回分类后的 sources。"""
    # 先检查任务存在
    session = get_session()
    try:
        repo = TaskRepository(session)
        row = repo.get_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        task_mode = TaskMode(row.mode)
    finally:
        session.close()

    # 优先从内存缓存读取（有 Pydantic 模型，支持分类）
    items = _source_items.get(task_id, [])

    # 如果内存没有，从 DB 加载
    if not items:
        items = _load_sources_from_db(task_id)
        if items:
            _source_items[task_id] = items

    if not items:
        return {"task_id": task_id, "categories": {}, "total": 0, "items": []}

    classified = classify_results(items, mode=task_mode)
    result = {}
    for cat, cat_items in classified.items():
        result[cat] = [_serialize_source(item) for item in cat_items]

    all_items = [_serialize_source(item) for item in items]
    return {"task_id": task_id, "categories": result, "total": len(items), "items": all_items}


def _load_sources_from_db(task_id: str) -> list:
    """从 DB 加载 sources 并转换为 SourceItem 模型。"""
    from models.enums import DownloadStatus, SourceLevel, SourceType
    from models.schemas import SourceItem

    session = get_session()
    try:
        src_repo = SourceRepository(session)
        rows = src_repo.get_by_task(task_id)
        items = []
        for r in rows:
            items.append(SourceItem(
                id=r.id,
                task_id=r.task_id,
                title=r.title,
                url=r.url,
                domain=r.domain,
                snippet=r.snippet,
                source_type=SourceType(r.source_type) if r.source_type else SourceType.OTHER,
                source_level=SourceLevel(r.source_level) if r.source_level else SourceLevel.C,
                relevance_score=r.relevance_score,
                authority_score=r.authority_score,
                originality_score=r.originality_score,
                gossip_score=r.gossip_score,
                downloadable=r.downloadable,
                download_status=DownloadStatus(r.download_status) if r.download_status else DownloadStatus.PENDING,
                reason_to_read=r.reason_to_read,
            ))
        return items
    finally:
        session.close()


def _serialize_source(item) -> dict:
    """序列化 SourceItem 为完整字典。"""
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
        "source_origin": getattr(item, "source_origin", "search_provider"),
        "query_language": item.query_language.value if item.query_language else None,
        "source_language": item.source_language.value if item.source_language else None,
        "matched_query": item.matched_query,
    }


@router.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str, limit: int = 50):
    """获取任务事件日志。"""
    _ensure_task_exists(task_id)

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
    _ensure_task_exists(task_id)

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
    _ensure_task_exists(task_id)

    from app.tracing.recorder import get_recorder
    recorder = get_recorder()
    return recorder.get_summary(task_id)


@router.get("/tasks/{task_id}/trace/llm")
async def get_task_trace_llm(task_id: str):
    """获取任务 LLM 使用详情（分组展示）。"""
    _ensure_task_exists(task_id)

    from app.tracing.llm_registry import get_all_task_info, RULE_ONLY_STEPS
    from app.tracing.models import TraceStep
    from app.tracing.recorder import get_recorder
    from core.config import get_settings

    settings = get_settings()
    recorder = get_recorder()
    events = recorder.get_events(task_id, limit=1000)

    llm_calls = [e for e in events if e.step == TraceStep.LLM_CALL_FINISHED]
    llm_failures = [e for e in events if e.step == TraceStep.LLM_CALL_FAILED]

    all_task_info = get_all_task_info()
    llm_tasks_status = []

    called_tasks = set()
    for e in llm_calls:
        task_name = (e.output_summary or {}).get("task_name") or (e.input_summary or {}).get("task_name", "")
        if task_name:
            called_tasks.add(task_name)
            info = next((t for t in all_task_info if t.task_name == task_name), None)
            llm_tasks_status.append({
                "task_name": task_name,
                "stage": info.stage if info else "unknown",
                "group": info.group if info else "executed",
                "status": "used_llm",
                "provider": e.provider,
                "model": e.model,
                "prompt_template": info.prompt_template if info else "",
                "input_chars": (e.output_summary or {}).get("input_chars"),
                "output_chars": (e.output_summary or {}).get("output_chars"),
                "duration_ms": e.duration_ms,
            })

    for e in llm_failures:
        task_name = (e.input_summary or {}).get("task_name", "")
        if task_name and task_name not in called_tasks:
            called_tasks.add(task_name)
            info = next((t for t in all_task_info if t.task_name == task_name), None)
            llm_tasks_status.append({
                "task_name": task_name,
                "stage": info.stage if info else "unknown",
                "group": info.group if info else "executed",
                "status": "fallback",
                "provider": e.provider,
                "model": e.model,
                "error_message": e.error_message,
                "fallback_used": True,
                "fallback_name": info.fallback if info else "",
            })

    for info in all_task_info:
        if info.task_name in called_tasks:
            continue
        if info.covered_by:
            llm_tasks_status.append({
                "task_name": info.task_name, "stage": info.stage, "group": "covered",
                "status": "covered_by", "skipped_reason": f"由 {info.covered_by} 覆盖",
                "covered_by": info.covered_by,
            })
        elif not info.implemented:
            llm_tasks_status.append({
                "task_name": info.task_name, "stage": info.stage, "group": "planned",
                "status": "skipped_not_implemented", "skipped_reason": "规划中",
            })
        elif not info.enabled:
            llm_tasks_status.append({
                "task_name": info.task_name, "stage": info.stage, "group": "disabled",
                "status": "skipped_disabled", "skipped_reason": f"{info.task_name}.enabled=false",
                "fallback_name": info.fallback,
            })
        elif info.wait_for:
            llm_tasks_status.append({
                "task_name": info.task_name, "stage": info.stage, "group": "waiting",
                "status": "waiting", "skipped_reason": f"等待{info.wait_for}",
                "wait_for": info.wait_for,
            })
        elif info.group == "export":
            llm_tasks_status.append({
                "task_name": info.task_name, "stage": info.stage, "group": "export",
                "status": "skipped_not_reached", "skipped_reason": "导出时触发",
            })
        else:
            llm_tasks_status.append({
                "task_name": info.task_name, "stage": info.stage, "group": info.group,
                "status": "skipped_not_reached", "skipped_reason": "流程未到达",
            })

    return {
        "task_id": task_id,
        "active_provider": settings.active_llm_provider,
        "active_model": settings.ollama_default_model if settings.active_llm_provider == "ollama_lan" else settings.deepseek_default_model,
        "llm_call_count": len(llm_calls),
        "llm_tasks": llm_tasks_status,
        "rule_only_steps": RULE_ONLY_STEPS,
    }


# === Task Management Endpoints ===


@router.get("/tasks")
async def list_tasks_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    include_deleted: bool = Query(default=False),
):
    """列出研究任务（从 DB 读取，按创建时间倒序）。支持 include_deleted 参数。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        src_repo = SourceRepository(session)

        tasks = repo.list_tasks(limit=limit, offset=offset, status=status, q=q, include_deleted=include_deleted)
        total = repo.count_tasks(status=status, q=q, include_deleted=include_deleted)

        items = []
        for t in tasks:
            source_count = src_repo.count_by_task(t.id)
            high_quality_count = src_repo.count_high_quality(t.id)
            extracted_count = src_repo.count_extracted(t.id)

            items.append({
                "task_id": t.id,
                "topic": t.topic,
                "canonical_topic": t.canonical_topic or "",
                "mode": t.mode,
                "status": t.status,
                "depth": t.depth,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "source_count": source_count,
                "high_quality_count": high_quality_count,
                "extracted_count": extracted_count,
                "exported": t.exported,
                "export_path": t.export_path or None,
                "deleted_at": t.deleted_at.isoformat() if t.deleted_at else None,
                "cloned_from_task_id": t.cloned_from_task_id or None,
            })

        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        session.close()


@router.patch("/tasks/{task_id}")
async def rename_task(task_id: str, request: dict):
    """重命名研究任务。"""
    from models.schemas import ResearchTaskRenameRequest
    from services.research_service import ResearchTaskManagementService

    topic = request.get("topic")
    if not topic or not topic.strip():
        raise HTTPException(status_code=400, detail="topic 不能为空")

    rename_req = ResearchTaskRenameRequest(
        topic=topic.strip(),
        canonical_topic=request.get("canonical_topic"),
    )

    service = ResearchTaskManagementService()
    result = service.rename_task(task_id, rename_req.topic, rename_req.canonical_topic)

    if "error" in result:
        if result["error"] == "not_found":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, request: dict | None = None):
    """删除研究任务（默认软删除）。"""
    from services.research_service import ResearchTaskManagementService

    hard_delete = False
    if request:
        hard_delete = request.get("hard_delete", False)

    service = ResearchTaskManagementService()

    if hard_delete:
        result = service.hard_delete_task(task_id)
    else:
        result = service.soft_delete_task(task_id)

    if "error" in result:
        if result["error"] == "not_found":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/tasks/{task_id}/clone")
async def clone_task(task_id: str, request: dict | None = None):
    """复制研究任务配置，创建新任务。"""
    from services.research_service import ResearchTaskManagementService

    topic_override = None
    rerun_immediately = False
    if request:
        topic_override = request.get("topic_override")
        rerun_immediately = request.get("rerun_immediately", False)

    service = ResearchTaskManagementService()
    result = service.clone_task(task_id, topic_override=topic_override, rerun_immediately=rerun_immediately)

    if "error" in result:
        if result["error"] == "not_found":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: str, request: dict | None = None):
    """重新发起研究任务。"""
    from services.research_service import ResearchTaskManagementService

    clone = True
    if request:
        clone = request.get("clone", True)

    service = ResearchTaskManagementService()
    result = service.rerun_task(task_id, clone=clone)

    if "error" in result:
        if result["error"] == "not_found":
            raise HTTPException(status_code=404, detail=result["message"])
        if result["error"] == "not_supported":
            raise HTTPException(status_code=400, detail=result["message"])
        raise HTTPException(status_code=400, detail=result["message"])

    return result


def _ensure_task_exists(task_id: str) -> None:
    """检查任务是否存在（DB），不存在则 404。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        if not repo.get_task(task_id):
            raise HTTPException(status_code=404, detail="Task not found")
    finally:
        session.close()
