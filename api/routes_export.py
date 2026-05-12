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
                detail="Obsidian Vault 未配置，请到 Settings 设置默认 Vault 路径。",
            )
        obsidian_path = str(settings.obsidian_path)

    vault = Path(obsidian_path)
    if not vault.exists() or not vault.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Vault 路径无效或不存在: {vault}",
        )

    # 获取 sources（MVP: 从内存）
    from api.routes_research import _source_items

    sources = _source_items.get(task_id, [])

    # 获取 extracted docs 映射
    from models.schemas import ExtractedDocument

    docs_map: dict[str, ExtractedDocument] = {}
    # MVP: 简化，传空映射

    try:
        path = export_research_index(task, sources, docs_map, vault_path=vault)
    except ResearchError as e:
        raise HTTPException(status_code=400, detail=e.message)

    # 标记导出状态
    task_data["exported"] = True
    task_data["export_path"] = str(path)

    return {
        "success": True,
        "task_id": task_id,
        "status": "exported",
        "path": str(path),
        "index_path": str(path),
        "message": f"研究索引已导出到: {path}",
        "source_count": len(sources),
    }
