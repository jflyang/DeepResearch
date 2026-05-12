"""来源管理路由。"""

import logging

from fastapi import APIRouter, HTTPException

from models.enums import DownloadStatus
from models.schemas import SourceItem
from services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)

router = APIRouter()

# 内存存储（MVP）
_extracted_docs: dict[str, dict] = {}


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
