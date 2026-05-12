"""来源管理路由。"""

import asyncio
import logging
from collections import deque

from fastapi import APIRouter, BackgroundTasks, HTTPException

from models.enums import DownloadStatus
from models.schemas import SourceItem
from services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)

router = APIRouter()

# 内存存储（MVP）
_extracted_docs: dict[str, dict] = {}

# === 异步提取队列 ===
_extraction_queue: deque[str] = deque()  # source_id 队列
_extraction_status: dict[str, dict] = {}  # source_id → {status, error, ...}
_extraction_lock = asyncio.Lock()
_extraction_worker_running = False


@router.get("/{source_id}/content")
async def get_extracted_content(source_id: str):
    """获取已提取的正文内容。"""
    # 先从内存查找
    if source_id in _extracted_docs:
        doc_info = _extracted_docs[source_id]
        return {
            "source_id": source_id,
            "found": True,
            **doc_info,
        }

    # 从 DB 查找
    from db.session import get_session
    from db.repositories import ExtractedRepository

    session = get_session()
    try:
        repo = ExtractedRepository(session)
        row = repo.get_by_source(source_id)
        if row:
            import json
            return {
                "source_id": source_id,
                "found": True,
                "id": row.id,
                "title": row.title,
                "author": row.author,
                "content": row.content[:5000] if row.content else "",
                "content_length": len(row.content) if row.content else 0,
                "summary": row.summary,
                "people": json.loads(row.people) if row.people else [],
                "places": json.loads(row.places) if row.places else [],
                "organizations": json.loads(row.organizations) if row.organizations else [],
                "concepts": json.loads(row.concepts) if row.concepts else [],
                "key_quotes": json.loads(row.key_quotes) if row.key_quotes else [],
            }
    finally:
        session.close()

    raise HTTPException(status_code=404, detail="未找到提取内容。请先点击提取按钮。")


@router.post("/{source_id}/extract")
async def extract_source(source_id: str):
    """提取来源正文。"""
    # MVP: 从 routes_research 的内存存储中查找 source_item
    from api.routes_research import _source_items

    # 在所有任务的 source_items 中查找
    target_item: SourceItem | None = None
    for task_id, items in _source_items.items():
        for item in items:
            if item.id == source_id:
                target_item = item
                break
        if target_item:
            break

    # 如果内存中没有，从 DB 加载
    if target_item is None:
        from db.session import get_session
        from db.repositories import SourceRepository
        session = get_session()
        try:
            src_repo = SourceRepository(session)
            row = session.get(
                __import__("db.tables", fromlist=["SourceTable"]).SourceTable,
                source_id,
            )
            if row:
                from models.enums import SourceLevel, SourceType
                target_item = SourceItem(
                    id=row.id,
                    task_id=row.task_id,
                    title=row.title,
                    url=row.url,
                    domain=row.domain,
                    snippet=row.snippet,
                    source_type=SourceType(row.source_type) if row.source_type else SourceType.OTHER,
                    source_level=SourceLevel(row.source_level) if row.source_level else SourceLevel.C,
                    relevance_score=row.relevance_score,
                    authority_score=row.authority_score,
                    originality_score=row.originality_score,
                    gossip_score=row.gossip_score,
                    downloadable=row.downloadable,
                    download_status=DownloadStatus(row.download_status) if row.download_status else DownloadStatus.PENDING,
                    reason_to_read=row.reason_to_read,
                )
        finally:
            session.close()

    if target_item is None:
        raise HTTPException(status_code=404, detail="Source item not found")

    if target_item.download_status == DownloadStatus.EXTRACTED:
        raise HTTPException(status_code=400, detail="Source already extracted")

    service = ExtractionService()
    doc = await service.extract_source(target_item)

    if target_item.download_status == DownloadStatus.FAILED:
        return {
            "source_id": source_id,
            "status": "failed",
            "error": "Extraction failed",
        }

    if target_item.download_status == DownloadStatus.SKIPPED:
        return {
            "source_id": source_id,
            "status": "skipped",
            "error": "此来源为图书信息页，不包含可提取正文。需手动获取图书内容。",
        }

    # 存储
    _extracted_docs[source_id] = {
        "id": doc.id,
        "source_item_id": doc.source_item_id,
        "title": doc.title,
        "author": doc.author,
        "content": doc.content[:5000],
        "content_length": len(doc.content),
        "summary": doc.summary,
        "people": doc.people,
        "places": doc.places,
        "organizations": doc.organizations,
        "concepts": doc.concepts,
        "key_quotes": doc.key_quotes,
    }

    # 持久化到 DB
    try:
        import json
        from db.session import get_session
        from db.repositories import ExtractedRepository

        session = get_session()
        try:
            repo = ExtractedRepository(session)
            repo.create({
                "id": doc.id,
                "source_item_id": doc.source_item_id,
                "title": doc.title,
                "author": doc.author,
                "content": doc.content,
                "summary": doc.summary or "",
                "key_quotes": json.dumps(doc.key_quotes, ensure_ascii=False),
                "people": json.dumps(doc.people, ensure_ascii=False),
                "places": json.dumps(doc.places, ensure_ascii=False),
                "organizations": json.dumps(doc.organizations, ensure_ascii=False),
                "concepts": json.dumps(doc.concepts, ensure_ascii=False),
                "events": json.dumps(doc.events, ensure_ascii=False),
            })
            # 更新 source download_status
            from db.repositories import SourceRepository
            src_repo = SourceRepository(session)
            src_repo.update_download_status(source_id, "extracted")
        finally:
            session.close()
    except Exception as e:
        logger.warning("extracted_doc_persist_failed source_id=%s error=%s", source_id, str(e)[:100])

    return {
        "source_id": source_id,
        "status": "extracted",
        "title": doc.title,
        "author": doc.author,
        "content_length": len(doc.content),
        "content_preview": doc.content[:500] if doc.content else "",
        "people": doc.people,
        "concepts": doc.concepts,
    }


# === 异步提取：队列 worker ===


async def _run_extraction_worker():
    """后台 worker：逐个处理提取队列中的任务。"""
    global _extraction_worker_running
    _extraction_worker_running = True
    try:
        while True:
            async with _extraction_lock:
                if not _extraction_queue:
                    break
                source_id = _extraction_queue.popleft()

            # 标记为进行中
            _extraction_status[source_id] = {"status": "extracting", "error": None}

            try:
                await _do_extract_and_save(source_id)
                _extraction_status[source_id] = {"status": "done", "error": None}
            except Exception as e:
                logger.warning("async_extraction_failed source_id=%s error=%s", source_id, str(e)[:200])
                _extraction_status[source_id] = {"status": "failed", "error": str(e)[:200]}
    finally:
        _extraction_worker_running = False


async def _do_extract_and_save(source_id: str):
    """提取正文并直接保存 .md 到 sources/ 文件夹。"""
    from api.routes_research import _source_items

    # 查找 source_item
    target_item: SourceItem | None = None
    task_id: str | None = None
    for tid, items in _source_items.items():
        for item in items:
            if item.id == source_id:
                target_item = item
                task_id = tid
                break
        if target_item:
            break

    # 如果内存中没有，从 DB 加载
    if target_item is None:
        from db.session import get_session
        from db.repositories import SourceRepository
        session = get_session()
        try:
            from db.tables import SourceTable
            row = session.get(SourceTable, source_id)
            if row:
                from models.enums import SourceLevel, SourceType
                target_item = SourceItem(
                    id=row.id,
                    task_id=row.task_id,
                    title=row.title,
                    url=row.url,
                    domain=row.domain,
                    snippet=row.snippet,
                    source_type=SourceType(row.source_type) if row.source_type else SourceType.OTHER,
                    source_level=SourceLevel(row.source_level) if row.source_level else SourceLevel.C,
                    relevance_score=row.relevance_score,
                    authority_score=row.authority_score,
                    originality_score=row.originality_score,
                    gossip_score=row.gossip_score,
                    downloadable=row.downloadable,
                    download_status=DownloadStatus(row.download_status) if row.download_status else DownloadStatus.PENDING,
                    reason_to_read=row.reason_to_read,
                )
                task_id = row.task_id
        finally:
            session.close()

    if target_item is None:
        raise ValueError("Source item not found")

    if target_item.download_status == DownloadStatus.EXTRACTED:
        return  # 已提取，跳过

    # 执行提取
    service = ExtractionService()
    doc = await service.extract_source(target_item)

    if target_item.download_status == DownloadStatus.FAILED:
        raise ValueError("Extraction failed")

    if target_item.download_status == DownloadStatus.SKIPPED:
        return  # 图书信息页，跳过

    # 存储到内存
    _extracted_docs[source_id] = {
        "id": doc.id,
        "source_item_id": doc.source_item_id,
        "title": doc.title,
        "author": doc.author,
        "content": doc.content[:5000],
        "content_length": len(doc.content),
        "summary": doc.summary,
        "people": doc.people,
        "places": doc.places,
        "organizations": doc.organizations,
        "concepts": doc.concepts,
        "key_quotes": doc.key_quotes,
    }

    # 持久化到 DB
    try:
        import json
        from db.session import get_session
        from db.repositories import ExtractedRepository

        session = get_session()
        try:
            repo = ExtractedRepository(session)
            repo.create({
                "id": doc.id,
                "source_item_id": doc.source_item_id,
                "title": doc.title,
                "author": doc.author,
                "content": doc.content,
                "summary": doc.summary or "",
                "key_quotes": json.dumps(doc.key_quotes, ensure_ascii=False),
                "people": json.dumps(doc.people, ensure_ascii=False),
                "places": json.dumps(doc.places, ensure_ascii=False),
                "organizations": json.dumps(doc.organizations, ensure_ascii=False),
                "concepts": json.dumps(doc.concepts, ensure_ascii=False),
                "events": json.dumps(doc.events, ensure_ascii=False),
            })
            from db.repositories import SourceRepository
            src_repo = SourceRepository(session)
            src_repo.update_download_status(source_id, "extracted")
        finally:
            session.close()
    except Exception as e:
        logger.warning("extracted_doc_persist_failed source_id=%s error=%s", source_id, str(e)[:100])

    # 如果是英文内容，调用 LLM 翻译为中英对照
    try:
        if doc.content and _is_english_content(doc.content):
            translated = await _translate_to_bilingual(doc.content, doc.title)
            if translated:
                doc.content = translated
                logger.info("content_translated source_id=%s chars=%d", source_id, len(translated))
    except Exception as e:
        logger.warning("translation_failed source_id=%s error=%s, using original", source_id, str(e)[:200])

    # 直接保存 .md 到 sources/ 文件夹
    try:
        _save_source_note_to_disk(target_item, doc, task_id)
    except Exception as e:
        logger.warning("save_source_note_failed source_id=%s error=%s", source_id, str(e)[:200])


def _save_source_note_to_disk(source_item: SourceItem, doc, task_id: str | None):
    """将提取内容直接保存为 .md 文件到 Obsidian sources/ 目录。"""
    from core.config import get_settings
    from services.markdown_service import export_source_note
    from pathlib import Path

    settings = get_settings()
    if not settings.obsidian_configured:
        logger.debug("obsidian_not_configured, skip saving source note to disk")
        return

    vault_path = settings.obsidian_path

    # 获取 topic
    topic = _get_topic_for_task(task_id)
    if not topic:
        logger.warning("cannot_determine_topic task_id=%s, skip saving source note", task_id)
        return

    export_source_note(
        source_item=source_item,
        extracted=doc,
        topic=topic,
        vault_path=vault_path,
    )
    logger.info("source_note_saved_to_disk source_id=%s topic=%s", source_item.id, topic)


def _get_topic_for_task(task_id: str | None) -> str | None:
    """从 DB 获取任务的 topic。"""
    if not task_id:
        return None

    try:
        from db.session import get_session
        from db.repositories import TaskRepository
        session = get_session()
        try:
            repo = TaskRepository(session)
            row = repo.get_task(task_id)
            if row:
                return row.topic
        finally:
            session.close()
    except Exception:
        pass

    return None


# === 异步提取 API 端点 ===


@router.post("/{source_id}/extract-async")
async def extract_source_async(source_id: str):
    """异步提取来源正文（加入队列，立即返回）。"""
    # 检查是否已在队列或已完成
    if source_id in _extraction_status:
        status = _extraction_status[source_id]["status"]
        if status in ("queued", "extracting"):
            return {"source_id": source_id, "status": status, "message": "已在队列中"}
        if status == "done":
            return {"source_id": source_id, "status": "done", "message": "已完成"}

    # 加入队列
    async with _extraction_lock:
        _extraction_queue.append(source_id)
    _extraction_status[source_id] = {"status": "queued", "error": None}

    # 如果 worker 没在运行，启动它
    global _extraction_worker_running
    if not _extraction_worker_running:
        asyncio.create_task(_run_extraction_worker())

    queue_pos = len(_extraction_queue)
    return {
        "source_id": source_id,
        "status": "queued",
        "queue_position": queue_pos,
        "message": f"已加入提取队列（第 {queue_pos} 位）",
    }


@router.post("/extract-batch-async")
async def extract_batch_async(payload: dict):
    """批量异步提取多个来源。"""
    source_ids = payload.get("source_ids", [])
    if not source_ids:
        raise HTTPException(status_code=400, detail="source_ids 不能为空")

    results = []
    for source_id in source_ids:
        if source_id in _extraction_status:
            status = _extraction_status[source_id]["status"]
            if status in ("queued", "extracting", "done"):
                results.append({"source_id": source_id, "status": status})
                continue

        async with _extraction_lock:
            _extraction_queue.append(source_id)
        _extraction_status[source_id] = {"status": "queued", "error": None}
        results.append({"source_id": source_id, "status": "queued"})

    # 启动 worker
    global _extraction_worker_running
    if not _extraction_worker_running:
        asyncio.create_task(_run_extraction_worker())

    return {
        "queued_count": len([r for r in results if r["status"] == "queued"]),
        "total": len(source_ids),
        "results": results,
    }


@router.get("/extraction-queue/status")
async def get_extraction_queue_status():
    """获取提取队列状态。"""
    return {
        "worker_running": _extraction_worker_running,
        "queue_length": len(_extraction_queue),
        "statuses": dict(_extraction_status),
    }


@router.get("/{source_id}/extraction-status")
async def get_extraction_status(source_id: str):
    """获取单个来源的提取状态。"""
    if source_id in _extraction_status:
        return {
            "source_id": source_id,
            **_extraction_status[source_id],
        }
    return {
        "source_id": source_id,
        "status": "unknown",
        "error": None,
    }


# === 英文内容检测与翻译 ===


def _is_english_content(text: str) -> bool:
    """检测内容是否主要为英文。

    策略：取前 500 个字符，统计 ASCII 字母占比。
    如果 ASCII 字母占比 > 60%，认为是英文内容。
    """
    sample = text[:500]
    if not sample:
        return False
    ascii_letters = sum(1 for c in sample if c.isascii() and c.isalpha())
    total_letters = sum(1 for c in sample if c.isalpha())
    if total_letters == 0:
        return False
    return (ascii_letters / total_letters) > 0.6


async def _translate_to_bilingual(content: str, title: str) -> str | None:
    """调用 LLM 将英文内容翻译为中英对照格式。

    如果 LLM 不可用或翻译失败，返回 None（使用原文）。
    内容过长时分段翻译。
    """
    from app.ai.gateway import AIGateway
    from app.ai.prompts import PromptStore
    from app.ai.router import LLMRouter

    try:
        router = LLMRouter()
        prompt_store = PromptStore()
        gateway = AIGateway(router=router, prompt_store=prompt_store)
    except Exception as e:
        logger.debug("llm_not_available_for_translation error=%s", str(e)[:100])
        return None

    # 限制翻译内容长度（避免超出 LLM 上下文）
    max_chars = 12000
    content_to_translate = content[:max_chars]

    try:
        translated = await gateway.run_text(
            task_name="content_translation",
            payload={"title": title, "content": content_to_translate},
            language="zh",
        )

        if not translated or len(translated.strip()) < 50:
            return None

        # 如果原文被截断，附加剩余原文
        if len(content) > max_chars:
            translated += "\n\n---\n\n# 原文剩余部分（未翻译）\n\n" + content[max_chars:]

        return translated

    except Exception as e:
        logger.warning("llm_translation_failed error=%s", str(e)[:200])
        return None
