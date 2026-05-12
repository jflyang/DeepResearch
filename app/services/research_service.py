"""研究合成编排 - 为 API 路由提供 synthesize_research_task 入口。

职责：
- 检查 task 和 ExtractedDocument 状态
- 调用 ResearchSynthesisService
- 调用 render_synthesized_index
- 写入 Obsidian index.md
- 返回摘要结果（不返回完整正文）
- 提供 run_auto_synthesis 供自动流程调用
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_POLICY_PATH = Path("config/research_policy.yaml")


# === Policy ===


def load_synthesis_policy() -> dict:
    """加载 auto_synthesis 策略配置。"""
    try:
        if _POLICY_PATH.exists():
            with open(_POLICY_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("auto_synthesis", {})
    except Exception:
        pass
    # 默认值
    return {
        "enabled": True,
        "include_levels": ["S", "A", "B"],
        "exclude_levels": ["C", "D"],
        "require_extracted_documents": True,
        "min_extracted_documents": 1,
        "run_after_auto_fetch": True,
        "write_index": True,
    }


def load_fetch_policy() -> dict:
    """加载 auto_fetch 策略配置。"""
    try:
        if _POLICY_PATH.exists():
            with open(_POLICY_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("auto_fetch", {})
    except Exception:
        pass
    return {
        "include_levels": ["S", "A", "B"],
        "exclude_levels": ["C", "D"],
    }


def load_normalization_policy() -> dict:
    """加载 auto_normalization 策略配置。"""
    try:
        if _POLICY_PATH.exists():
            with open(_POLICY_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("auto_normalization", {})
    except Exception:
        pass
    return {
        "include_levels": ["S", "A", "B"],
        "exclude_levels": ["C", "D"],
    }


# === Auto Synthesis（供自动研究流程调用） ===


async def run_auto_synthesis(task_id: str, extracted_count: int = 0) -> dict:
    """自动研究流程中调用的合成入口。

    在 auto_fetch 完成后调用。根据 policy 决定是否执行合成。
    失败时不抛异常，返回错误信息并 fallback。

    Args:
        task_id: 研究任务 ID
        extracted_count: 已抓取文档数

    Returns:
        {"status": "completed"|"skipped"|"failed", ...}
    """
    from app.tracing.recorder import get_recorder

    recorder = get_recorder()
    policy = load_synthesis_policy()

    # 检查 policy 是否启用
    if not policy.get("enabled", True):
        recorder.record(
            task_id=task_id,
            step="auto_synthesis_skipped",
            phase="processing",
            service="research_synthesis",
            message="auto_synthesis disabled in policy",
        )
        return {"status": "skipped", "reason": "auto_synthesis disabled in policy"}

    if not policy.get("run_after_auto_fetch", True):
        recorder.record(
            task_id=task_id,
            step="auto_synthesis_skipped",
            phase="processing",
            service="research_synthesis",
            message="run_after_auto_fetch=false",
        )
        return {"status": "skipped", "reason": "run_after_auto_fetch=false"}

    # 检查文档数量
    min_docs = policy.get("min_extracted_documents", 1)
    if policy.get("require_extracted_documents", True) and extracted_count < min_docs:
        recorder.record(
            task_id=task_id,
            step="auto_synthesis_skipped",
            phase="processing",
            service="research_synthesis",
            message=f"skipped_no_extracted_documents (count={extracted_count}, min={min_docs})",
        )
        return {
            "status": "skipped",
            "reason": f"extracted_count={extracted_count} < min={min_docs}",
        }

    # 执行合成
    recorder.record(
        task_id=task_id,
        step="auto_synthesis_started",
        phase="processing",
        service="research_synthesis",
    )

    try:
        result = await synthesize_research_task(task_id)

        if result.get("synthesized"):
            recorder.record(
                task_id=task_id,
                step="auto_synthesis_finished",
                phase="processing",
                service="research_synthesis",
                output_summary={
                    "confirmed_fact_count": result.get("confirmed_fact_count", 0),
                    "verification_needed_count": result.get("verification_needed_count", 0),
                    "index_path": result.get("index_path", ""),
                },
            )
            return {"status": "completed", **result}
        else:
            # 合成返回了错误但没抛异常
            error_msg = result.get("error", "unknown")
            recorder.record(
                task_id=task_id,
                step="auto_synthesis_failed",
                phase="processing",
                level="warning",
                service="research_synthesis",
                error_message=error_msg[:200],
            )
            return {"status": "failed", "reason": error_msg}

    except Exception as e:
        error_msg = str(e)[:200]
        logger.warning("auto_synthesis_failed task_id=%s error=%s", task_id, error_msg)
        recorder.record(
            task_id=task_id,
            step="auto_synthesis_failed",
            phase="processing",
            level="warning",
            service="research_synthesis",
            error_message=error_msg,
        )
        return {"status": "failed", "reason": error_msg}


async def synthesize_research_task(task_id: str) -> dict:
    """执行完整合成并写 index.md。

    Returns:
        成功: {"task_id", "synthesized": True, "normalized_document_count", ...}
        失败: {"error": "..."}
    """
    try:
        # 1. 检查 task 和 sources
        task_row, source_rows = _get_task_and_sources(task_id)

        if task_row is None:
            return {"error": "任务不存在。", "synthesized": False}

        # 2. 检查是否有已抓取 ExtractedDocument
        extracted_sources = [
            s for s in source_rows
            if getattr(s, "download_status", "") in ("extracted", "exported")
        ]

        if not extracted_sources:
            return {"error": "请先抓取 A/S 级来源正文，再进行内容合成。", "synthesized": False}

        # 3. 调用 ResearchSynthesisService
        synthesis = await _run_synthesis(task_id)

        # 4. 写入 Obsidian index.md
        index_path = _write_index(synthesis, source_rows, task_row)

        # 5. 返回摘要
        return {
            "task_id": task_id,
            "synthesized": True,
            "normalized_document_count": synthesis.metadata.total_sources if hasattr(synthesis, "metadata") else len(extracted_sources),
            "deduplicated_claim_count": len(synthesis.confirmed_facts) + len(synthesis.timeline) + len(synthesis.story_points) + len(synthesis.verification_needed),
            "confirmed_fact_count": len(synthesis.confirmed_facts),
            "verification_needed_count": len(synthesis.verification_needed),
            "index_path": str(index_path) if index_path else "",
        }

    except Exception as e:
        logger.error("synthesize_research_task_failed task_id=%s error=%s", task_id, str(e))
        return {"error": f"合成失败: {str(e)[:200]}", "synthesized": False}


def _get_task_and_sources(task_id: str) -> tuple[Any, list[Any]]:
    """从 DB 读取 task 和 sources。"""
    from db.repositories import SourceRepository, TaskRepository
    from db.session import get_session

    session = get_session()
    try:
        task_repo = TaskRepository(session)
        source_repo = SourceRepository(session)

        task_row = task_repo.get_task(task_id)
        source_rows = source_repo.get_by_task(task_id) if task_row else []

        return task_row, source_rows
    finally:
        session.close()


async def _run_synthesis(task_id: str):
    """创建并运行 ResearchSynthesisService。"""
    from app.ai.gateway import AIGateway
    from app.ai.prompts import PromptStore
    from app.ai.router import LLMRouter
    from app.services.content_normalization_service import ContentNormalizationService
    from app.services.cross_source_deduplication_service import CrossSourceDeduplicationService
    from app.services.research_synthesis_service import ResearchSynthesisService
    from app.tracing.recorder import get_recorder
    from db.repositories import ExtractedRepository, SourceRepository, TaskRepository
    from db.session import get_session

    # 创建 AI Gateway
    ai_gateway = _create_ai_gateway()

    # 创建 repositories
    session = get_session()
    task_repo = TaskRepository(session)
    source_repo = SourceRepository(session)
    doc_repo = ExtractedRepository(session)
    recorder = get_recorder()

    try:
        # 创建 services
        norm_service = ContentNormalizationService(
            ai_gateway=ai_gateway,
            document_repository=doc_repo,
            source_repository=source_repo,
            trace_recorder=recorder,
        )

        dedup_service = CrossSourceDeduplicationService(
            ai_gateway=ai_gateway,
            trace_recorder=recorder,
        )

        synthesis_service = ResearchSynthesisService(
            content_normalization_service=norm_service,
            deduplication_service=dedup_service,
            ai_gateway=ai_gateway,
            task_repository=task_repo,
            document_repository=doc_repo,
            source_repository=source_repo,
            trace_recorder=recorder,
        )

        # 设置 task_id 到 gateway
        if ai_gateway:
            ai_gateway.set_task_id(task_id)

        return await synthesis_service.synthesize_task(task_id=task_id)
    finally:
        session.close()


def _write_index(synthesis, source_rows, task_row) -> str:
    """渲染并写入 index.md。"""
    from app.services.markdown_service import render_synthesized_index
    from core.config import get_settings
    from models.enums import DownloadStatus, SourceLevel, SourceType
    from models.schemas import SourceItem
    from utils.filesystem import sanitize_filename, write_file

    # 获取 vault 路径
    obsidian_path = getattr(task_row, "obsidian_path", "") or ""
    if not obsidian_path:
        settings = get_settings()
        if settings.obsidian_configured:
            obsidian_path = str(settings.obsidian_path)

    if not obsidian_path:
        logger.warning("no_obsidian_path_configured, skipping index write")
        return ""

    vault = Path(obsidian_path)
    if not vault.exists():
        logger.warning("vault_path_not_exists path=%s", vault)
        return ""

    # 转换 source_rows 为 SourceItem（用于 render）
    source_items = []
    for r in source_rows:
        try:
            source_items.append(SourceItem(
                id=r.id,
                task_id=r.task_id,
                title=r.title,
                url=r.url,
                domain=getattr(r, "domain", ""),
                source_type=SourceType(r.source_type) if r.source_type else SourceType.OTHER,
                source_level=SourceLevel(r.source_level) if r.source_level else SourceLevel.C,
                download_status=DownloadStatus(r.download_status) if r.download_status else DownloadStatus.PENDING,
                reason_to_read=getattr(r, "reason_to_read", ""),
            ))
        except Exception:
            continue

    # 渲染 markdown
    markdown_content = render_synthesized_index(synthesis, sources=source_items)

    # 写入文件
    topic = getattr(task_row, "topic", "research")
    safe_topic = sanitize_filename(topic, max_length=80)
    research_dir = vault / "Research" / safe_topic
    research_dir.mkdir(parents=True, exist_ok=True)
    index_path = research_dir / "index.md"

    write_file(index_path, markdown_content)

    # 记录 trace
    from app.tracing.recorder import get_recorder
    recorder = get_recorder()
    recorder.record(
        task_id=getattr(task_row, "id", ""),
        step="synthesized_index_write_finished",
        phase="export",
        service="research_synthesis",
        output_summary={"path": str(index_path)},
    )

    return str(index_path)


def _create_ai_gateway():
    """创建 AI Gateway 实例。"""
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
