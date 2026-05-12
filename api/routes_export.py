"""导出路由。"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.config import get_settings
from core.errors import ResearchError
from services.markdown_service import export_research_index

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/tasks/{task_id}/export-index")
async def export_index(task_id: str):
    """生成 Obsidian 研究索引页。"""
    from api.routes_research import _tasks
    from api.routes_sources import _extracted_docs

    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = _tasks[task_id]
    task = task_data["task"]

    # 确定 vault 路径
    obsidian_path = task_data.get("obsidian_path", "")
    if not obsidian_path:
        settings = get_settings()
        if not settings.obsidian_configured:
            raise HTTPException(
                status_code=400,
                detail="Obsidian vault path not configured. Set OBSIDIAN_VAULT_PATH or pass obsidian_path in request.",
            )
        obsidian_path = str(settings.obsidian_path)

    vault = Path(obsidian_path)

    # 获取 sources（MVP: 从内存）
    from api.routes_research import _source_items

    sources = _source_items.get(task_id, [])

    # 获取 extracted docs 映射
    from models.schemas import ExtractedDocument

    docs_map: dict[str, ExtractedDocument] = {}
    # MVP: 简化，传空映射
    # 未来从 DB 加载

    try:
        path = export_research_index(task, sources, docs_map, vault_path=vault)
    except ResearchError as e:
        raise HTTPException(status_code=400, detail=e.message)

    return {
        "task_id": task_id,
        "status": "exported",
        "index_path": str(path),
    }
