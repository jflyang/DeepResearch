"""导出路由 - 使用 DB 持久化。"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.config import get_settings
from core.errors import ResearchError
from db.repositories import TaskRepository, SourceRepository
from db.session import get_session
from models.enums import ResearchTaskType, TaskMode
from models.schemas import ExtractedDocument, ResearchTask
from services.markdown_service import (
    export_imported_report,
    export_report_ingestion_index,
    export_research_index,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/tasks/{task_id}/export-index")
async def export_index(task_id: str):
    """生成 Obsidian 研究资料包：index.md + source notes。"""
    # 从 DB 加载任务
    session = get_session()
    try:
        repo = TaskRepository(session)
        row = repo.get_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        # 确定 vault 路径
        obsidian_path = row.obsidian_path or ""
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

        # 构建 ResearchTask pydantic 模型
        task = ResearchTask(
            id=row.id,
            topic=row.topic,
            mode=TaskMode(row.mode),
            status=row.status,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )
    finally:
        session.close()

    # 获取 sources（优先内存缓存，否则从 DB）
    from api.routes_research import _source_items, _load_sources_from_db

    sources = _source_items.get(task_id, [])
    if not sources:
        sources = _load_sources_from_db(task_id)

    # 从 DB 加载已提取的文档
    docs_map = _load_extracted_docs_from_db(task_id, sources)

    try:
        # 判断是否为报告导入任务
        task_type = getattr(row, "task_type", "search_research")
        if task_type == ResearchTaskType.REPORT_INGESTION:
            path = _export_report_ingestion(task_id, task, sources, vault, session_factory=get_session)
        else:
            # 导出 source notes（已提取的来源）
            source_note_count = 0
            if docs_map:
                from services.markdown_service import export_source_note
                for source_id, doc in docs_map.items():
                    if not doc.content:
                        continue
                    source_item = next((s for s in sources if s.id == source_id), None)
                    if source_item is None:
                        continue
                    try:
                        export_source_note(
                            source_item=source_item,
                            extracted=doc,
                            topic=task.topic,
                            vault_path=vault,
                        )
                        source_note_count += 1
                    except Exception as e:
                        logger.warning("export_source_note_failed source_id=%s error=%s", source_id, str(e)[:100])

            # 生成 index synthesis（如果有提取内容）
            synthesis = None
            if docs_map:
                try:
                    from services.markdown_service import generate_index_synthesis
                    synthesis = await generate_index_synthesis(
                        topic=task.topic,
                        mode=task.mode.value if hasattr(task.mode, 'value') else str(task.mode),
                        sources=sources,
                        extracted_docs=docs_map,
                    )
                except Exception as e:
                    logger.warning("index_synthesis_failed task_id=%s error=%s", task_id, str(e)[:100])

            # 导出 index.md
            path = export_research_index(
                task, sources, docs_map,
                vault_path=vault,
                synthesis=synthesis,
            )
    except ResearchError as e:
        raise HTTPException(status_code=400, detail=e.message)

    # 标记导出状态到 DB
    session = get_session()
    try:
        repo = TaskRepository(session)
        repo.mark_exported(task_id, str(path))
    finally:
        session.close()

    return {
        "success": True,
        "task_id": task_id,
        "status": "exported",
        "path": str(path),
        "index_path": str(path),
        "message": f"研究资料包已导出到: {path}",
        "source_count": len(sources),
        "extracted_count": len(docs_map),
        "source_note_count": source_note_count if task_type != ResearchTaskType.REPORT_INGESTION else 0,
    }


def _load_extracted_docs_from_db(task_id: str, sources: list) -> dict[str, ExtractedDocument]:
    """从 DB 加载已提取的文档，返回 {source_id: ExtractedDocument} 映射。"""
    from db.repositories import ExtractedRepository

    docs_map: dict[str, ExtractedDocument] = {}
    session = get_session()
    try:
        repo = ExtractedRepository(session)
        for source in sources:
            row = repo.get_by_source(source.id)
            if row and row.content:
                docs_map[source.id] = ExtractedDocument(
                    id=row.id,
                    source_item_id=row.source_item_id,
                    title=row.title,
                    author=row.author,
                    content=row.content,
                    summary=row.summary or "",
                    key_quotes=_parse_json_list(row.key_quotes),
                    people=_parse_json_list(row.people),
                    places=_parse_json_list(row.places),
                    organizations=_parse_json_list(row.organizations),
                    concepts=_parse_json_list(row.concepts),
                    events=_parse_json_list(row.events),
                )
    finally:
        session.close()

    return docs_map


def _parse_json_list(value: str | None) -> list[str]:
    """解析 JSON 列表字段。"""
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _export_report_ingestion(task_id, task, sources, vault, session_factory):
    """导出报告导入任务：生成 imported_report.md + index.md。"""
    session = session_factory()
    try:
        repo = TaskRepository(session)
        metadata = repo.get_imported_report_metadata(task_id)
        report_text = repo.load_imported_report_text(task_id) or ""
    finally:
        session.close()

    report_source = metadata.get("report_source") or "未知来源"

    # 解析摘要（如果有 parsed 数据）
    parsed_summary = None
    # 尝试从 report_text 解析获取引用信息
    try:
        from app.services.report_parser_service import ReportParserService
        parser = ReportParserService()
        parsed = parser.parse(report_text) if report_text else None
        if parsed:
            parsed_summary = {
                "urls": [{"url": u.url, "title_hint": u.title_hint} for u in parsed.urls],
                "books": [{"title": b.title, "author_hint": b.author_hint} for b in parsed.books],
                "papers": [{"title": p.title, "doi_hint": p.doi_hint, "arxiv_id": p.arxiv_id} for p in parsed.papers],
            }
    except Exception:
        parsed_summary = None

    # 导出 imported_report.md
    export_imported_report(
        task=task,
        report_text=report_text,
        report_source=report_source,
        parsed_summary=parsed_summary,
        vault_path=vault,
    )

    # 导出 index.md
    parsed_url_count = len(parsed_summary["urls"]) if parsed_summary else 0
    parsed_book_count = len(parsed_summary["books"]) if parsed_summary else 0
    parsed_paper_count = len(parsed_summary["papers"]) if parsed_summary else 0

    index_path = export_report_ingestion_index(
        task=task,
        sources=sources,
        report_source=report_source,
        parsed_url_count=parsed_url_count,
        parsed_book_count=parsed_book_count,
        parsed_paper_count=parsed_paper_count,
        vault_path=vault,
    )

    return index_path
