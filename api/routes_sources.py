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


@router.post("/{source_id}/extract")
async def extract_source(source_id: str):
    """提取来源正文。"""
    # MVP: 从 routes_research 的内存存储中查找 source_item
    from api.routes_research import _source_items, _tasks

    # 在所有任务的 source_items 中查找
    target_item: SourceItem | None = None
    for task_id, items in _source_items.items():
        for item in items:
            if item.id == source_id:
                target_item = item
                break
        if target_item:
            break

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

    # 存储
    _extracted_docs[source_id] = {
        "id": doc.id,
        "source_item_id": doc.source_item_id,
        "title": doc.title,
        "author": doc.author,
        "content_length": len(doc.content),
        "people": doc.people,
        "places": doc.places,
        "organizations": doc.organizations,
        "concepts": doc.concepts,
    }

    return {
        "source_id": source_id,
        "status": "extracted",
        "title": doc.title,
        "author": doc.author,
        "content_length": len(doc.content),
        "people": doc.people,
        "concepts": doc.concepts,
    }
