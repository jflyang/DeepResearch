"""外部研究报告导入 API 路由。"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.repositories import SourceRepository, TaskRepository
from db.session import get_session
from models.enums import ResearchTaskType, TaskStatus
from models.schemas import ImportedReportCreate, ReportIngestionOptions

logger = logging.getLogger(__name__)

router = APIRouter()


# === Request / Response Models ===


class ImportReportRequest(BaseModel):
    topic: str
    report_text: str = Field(min_length=1)
    report_source: str | None = None
    output_language: str = "zh"
    options: ReportIngestionOptions = Field(default_factory=ReportIngestionOptions)


class ImportReportResponse(BaseModel):
    task_id: str
    status: str
    task_type: str


class ParseReportResponse(BaseModel):
    task_id: str
    url_count: int = 0
    book_count: int = 0
    paper_count: int = 0
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    references_preview: list[dict] = Field(default_factory=list)


class ImportedReportDetailResponse(BaseModel):
    task_id: str
    report_source: str | None = None
    report_text_preview: str = ""
    parsed_summary: dict = Field(default_factory=dict)
    status: str = ""


# === Routes ===


@router.post("/import-report", response_model=ImportReportResponse)
async def create_import_report(request: ImportReportRequest):
    """创建外部报告导入任务。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        create_request = ImportedReportCreate(
            topic=request.topic,
            report_text=request.report_text,
            report_source=request.report_source,
            output_language=request.output_language,
            options=request.options,
        )
        task = repo.create_report_ingestion_task(create_request)
        return ImportReportResponse(
            task_id=task.id,
            status=task.status.value,
            task_type=ResearchTaskType.REPORT_INGESTION.value,
        )
    finally:
        session.close()


@router.post("/import-report/{task_id}/parse", response_model=ParseReportResponse)
async def parse_import_report(task_id: str):
    """解析已导入的报告，返回引用摘要。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        row = repo.get_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        if row.task_type != ResearchTaskType.REPORT_INGESTION:
            raise HTTPException(
                status_code=400,
                detail=f"Task is not a report_ingestion task (type={row.task_type})",
            )
    finally:
        session.close()

    # 调用 service 解析
    service = _get_ingestion_service()
    parsed = await service.parse_task_report(task_id)

    # 构建 references_preview（前 10 条 URL）
    preview = []
    for ref in parsed.urls[:10]:
        preview.append({"type": "url", "value": ref.url, "title_hint": ref.title_hint})
    for ref in parsed.books[:5]:
        preview.append({"type": "book", "value": ref.title, "author_hint": ref.author_hint})
    for ref in parsed.papers[:5]:
        preview.append({"type": "paper", "value": ref.title, "doi_hint": ref.doi_hint, "arxiv_id": ref.arxiv_id})

    return ParseReportResponse(
        task_id=task_id,
        url_count=len(parsed.urls),
        book_count=len(parsed.books),
        paper_count=len(parsed.papers),
        people=parsed.people,
        organizations=parsed.organizations,
        places=parsed.places,
        references_preview=preview,
    )


@router.post("/import-report/{task_id}/run")
async def run_import_report(task_id: str):
    """执行报告导入任务（抓取 + 补充检索）。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        row = repo.get_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        if row.task_type != ResearchTaskType.REPORT_INGESTION:
            raise HTTPException(
                status_code=400,
                detail=f"Task is not a report_ingestion task (type={row.task_type})",
            )
        if row.status not in (TaskStatus.PENDING, TaskStatus.FAILED):
            raise HTTPException(
                status_code=400,
                detail=f"Task already in status: {row.status}",
            )
    finally:
        session.close()

    service = _get_ingestion_service()
    result = await service.run_import_task(task_id)
    return result.model_dump()


@router.get("/tasks/{task_id}/imported-report")
async def get_imported_report(
    task_id: str,
    include_full: bool = Query(default=False),
):
    """获取导入报告详情。"""
    session = get_session()
    try:
        repo = TaskRepository(session)
        row = repo.get_task(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        if row.task_type != ResearchTaskType.REPORT_INGESTION:
            raise HTTPException(
                status_code=400,
                detail=f"Task is not a report_ingestion task (type={row.task_type})",
            )

        metadata = repo.get_imported_report_metadata(task_id)

        # report_text preview（前 500 字符）
        report_text_preview = ""
        if include_full:
            full_text = repo.load_imported_report_text(task_id)
            report_text_preview = full_text or ""
        else:
            full_text = repo.load_imported_report_text(task_id)
            if full_text:
                report_text_preview = full_text[:500] + ("..." if len(full_text) > 500 else "")

        return {
            "task_id": task_id,
            "report_source": metadata.get("report_source"),
            "report_text_preview": report_text_preview,
            "parsed_summary": {
                "output_language": metadata.get("output_language"),
                "options": metadata.get("options"),
            },
            "status": row.status,
        }
    finally:
        session.close()


# === Service Factory ===


def _get_ingestion_service():
    """创建 ReportIngestionService 实例。"""
    from app.services.reference_extraction_service import ReferenceExtractionService
    from app.services.report_ingestion_service import ReportIngestionService
    from app.services.report_parser_service import ReportParserService
    from app.tracing.recorder import get_recorder
    from db.repositories import SourceRepository, TaskRepository
    from db.session import get_session
    from services.extraction_service import ExtractionService

    session = get_session()
    task_repo = TaskRepository(session)
    source_repo = SourceRepository(session)

    # 尝试创建 SearchRouter（可选）
    search_router = None
    try:
        from services.search_router import SearchRouter
        search_router = SearchRouter()
    except Exception:
        pass

    return ReportIngestionService(
        report_parser=ReportParserService(),
        reference_extractor=ReferenceExtractionService(),
        extraction_service=ExtractionService(),
        source_repository=source_repo,
        task_repository=task_repo,
        search_router=search_router,
        trace_recorder=get_recorder(),
    )
