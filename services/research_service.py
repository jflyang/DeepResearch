"""研究服务 - 编排搜索流水线。

职责：创建任务 → 语言规划 → 扩展 query → 并发搜索 → 去重 → 评分 → 保存。
不直接调用 API，通过 BaseSearchProvider 接口操作。
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.tracing import TracePhase, TraceStep
from app.tracing.recorder import get_recorder
from core.config import get_settings
from models.enums import DownloadStatus, LanguageCode, SearchSource, SearchStrategy, SourceLevel, TaskMode, TaskStatus
from models.schemas import ExpandedQuery as RichExpandedQuery, ResearchLanguagePlan, ResearchTask, SourceItem
from providers.search.base import BaseSearchProvider, SearchProviderError, SearchResult
from services.dedupe_service import DedupedSourceCandidate, dedupe_results
from services.query_expansion_service import ExpandedQuery, QueryExpansionService, expand_queries
from services.scoring_service import score_candidates
from services.task_event_service import log_event

logger = logging.getLogger(__name__)

# === 请求/响应模型 ===


class CreateResearchTaskRequest(BaseModel):
    topic: str
    mode: TaskMode = TaskMode.AUTO
    language: str = "mixed"
    depth: str = "standard"
    include_books: bool = True
    include_video: bool = False
    include_gossip: bool = False


class ResearchResultSummary(BaseModel):
    task_id: str
    topic: str
    status: TaskStatus
    total_queries: int = 0
    total_raw_results: int = 0
    total_after_dedup: int = 0
    total_saved: int = 0
    provider_errors: list[str] = Field(default_factory=list)


# === Provider Factory ===


# === Provider Factory ===


def create_search_providers() -> dict[str, list[BaseSearchProvider]]:
    """
    根据配置创建可用的搜索 Provider 实例。

    Returns:
        按 source_hint 分组的 provider 字典
    """
    from providers.search.brave import BraveSearchProvider
    from providers.search.google_books import GoogleBooksSearchProvider
    from providers.search.tavily import TavilySearchProvider

    settings = get_settings()
    web_providers: list[BaseSearchProvider] = []
    book_providers: list[BaseSearchProvider] = []

    if settings.tavily_available:
        web_providers.append(TavilySearchProvider())
    if settings.brave_available:
        web_providers.append(BraveSearchProvider())
    if settings.enable_google_books:
        book_providers.append(GoogleBooksSearchProvider())

    logger.info(
        "providers_created web=%d book=%d",
        len(web_providers),
        len(book_providers),
    )

    return {
        "web": web_providers,
        "general": web_providers,
        "book": book_providers,
        "video": [],  # 未来扩展
        "archive": [],  # 未来扩展
    }


# === 核心服务类 ===


class ResearchService:
    """研究服务 - 编排整个搜索流水线。"""

    def __init__(
        self,
        providers: dict[str, list[BaseSearchProvider]] | None = None,
        max_concurrency: int = 3,
        ai_gateway=None,
        search_router=None,
    ):
        self._providers = providers or create_search_providers()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._ai_gateway = ai_gateway
        self._search_router = search_router
        # 如果显式传入 providers（测试场景），不自动初始化 SearchRouter
        self._use_legacy_providers = providers is not None and search_router is None

    def create_task(self, request: CreateResearchTaskRequest) -> ResearchTask:
        """创建研究任务。"""
        task = ResearchTask(
            topic=request.topic,
            mode=request.mode,
            language=request.language,
            depth=request.depth,
            include_books=request.include_books,
            include_video=request.include_video,
            include_gossip=request.include_gossip,
            status=TaskStatus.PENDING,
        )
        logger.info("task_created task_id=%s topic=%s mode=%s", task.id, task.topic, task.mode)
        log_event(task.id, "task_created", f"Task created: {task.topic}", payload={"mode": task.mode.value})

        # Trace
        get_recorder().info(
            task.id, TraceStep.TASK_CREATED, TracePhase.PLANNING,
            message=f"Task created: {task.topic}",
            input_summary={
                "topic": task.topic,
                "mode": task.mode.value,
                "depth": task.depth.value if hasattr(task.depth, 'value') else str(task.depth),
                "include_books": task.include_books,
                "include_gossip": task.include_gossip,
                "include_video": task.include_video,
            },
        )
        return task

    async def run_initial_research(self, task: ResearchTask) -> ResearchResultSummary:
        """执行初始研究：语言规划 → 扩展 query → 搜索 → 去重 → 评分 → 保存。"""
        task.status = TaskStatus.RUNNING
        errors: list[str] = []
        _trace = get_recorder()
        _research_start = time.perf_counter()

        # 设置 AI Gateway 的 task_id（用于 LLM trace 关联）
        if self._ai_gateway:
            self._ai_gateway.set_task_id(task.id)

        # 记录 LLM Plan
        self._record_llm_plan(task.id)

        # 0. 语言规划
        language_plan = await self._plan_language(task)

        # Trace language plan result
        if language_plan:
            _trace.info(
                task.id, TraceStep.LANGUAGE_PLANNING_FINISHED, TracePhase.PLANNING,
                message=f"Language plan: {language_plan.search_strategy.value}",
                output_summary={
                    "user_language": language_plan.user_language.value,
                    "working_language": language_plan.working_language.value,
                    "output_language": language_plan.output_language.value,
                    "search_strategy": language_plan.search_strategy.value,
                    "canonical_topic": language_plan.canonical_topic,
                    "main_entity_canonical": language_plan.main_entity_canonical,
                },
            )

        # 1. 扩展 query（语言规划感知）
        logger.info("research_step step=query_expansion task_id=%s", task.id)
        log_event(task.id, "search_started", f"Starting research for: {task.topic}")

        expanded = await self._expand_queries_with_plan(task, language_plan)
        task.expanded_queries = [q.query for q in expanded]
        log_event(task.id, "query_expanded", f"Generated {len(expanded)} queries", payload={"count": len(expanded)})

        # Trace query expansion
        en_queries = [q for q in expanded if not any('\u4e00' <= c <= '\u9fff' for c in q.query)]
        zh_queries = [q for q in expanded if any('\u4e00' <= c <= '\u9fff' for c in q.query)]
        _trace.info(
            task.id, TraceStep.QUERY_EXPANSION_FINISHED, TracePhase.PLANNING,
            message=f"Generated {len(expanded)} queries",
            service="QueryExpansionService",
            output_summary={
                "expanded_query_count": len(expanded),
                "english_query_count": len(en_queries),
                "chinese_query_count": len(zh_queries),
                "queries": [q.query for q in expanded[:30]],
            },
        )

        # 2. 并发搜索
        logger.info("research_step step=search task_id=%s queries=%d", task.id, len(expanded))
        raw_results, search_errors = await self._collect_search_results_rich(expanded)
        errors.extend(search_errors)
        for err in search_errors:
            log_event(task.id, "provider_failed", err, level="warning")

        # 3. 去重
        logger.info("research_step step=dedup task_id=%s raw=%d", task.id, len(raw_results))
        deduped = dedupe_results(raw_results)
        log_event(task.id, "dedupe_finished", f"Deduped {len(raw_results)} → {len(deduped)}", payload={"before": len(raw_results), "after": len(deduped)})

        # Trace dedupe
        _trace.info(
            task.id, TraceStep.DEDUPE_FINISHED, TracePhase.PROCESSING,
            message=f"Deduped {len(raw_results)} → {len(deduped)}",
            service="DedupeService",
            output_summary={
                "before_count": len(raw_results),
                "after_count": len(deduped),
                "removed_count": len(raw_results) - len(deduped),
            },
        )

        # 4. 评分
        logger.info("research_step step=scoring task_id=%s deduped=%d", task.id, len(deduped))
        scored = score_candidates(deduped, topic=task.topic)
        log_event(task.id, "scoring_finished", f"Scored {len(scored)} candidates", payload={"count": len(scored)})

        # 5. 转换为 SourceItem（带语言元数据）
        source_items = self._to_source_items(task.id, scored, language_plan=language_plan)

        # 保存到实例属性，供路由层读取
        self.last_source_items = source_items

        # Trace scoring (after source_items are created so we have levels)
        level_counts = {}
        for item in source_items:
            lvl = item.source_level.value
            level_counts[lvl] = level_counts.get(lvl, 0) + 1
        _trace.info(
            task.id, TraceStep.SCORING_FINISHED, TracePhase.PROCESSING,
            message=f"Scored {len(scored)} candidates",
            service="ScoringService",
            output_summary={
                "total_sources": len(source_items),
                "level_counts": level_counts,
            },
        )

        # 6. 更新任务状态
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(UTC)
        log_event(task.id, "task_completed", f"Research completed: {len(source_items)} sources saved", payload={"total_saved": len(source_items), "errors": len(errors)})

        # Trace task completed
        total_duration_ms = int((time.perf_counter() - _research_start) * 1000)
        _trace.info(
            task.id, TraceStep.TASK_COMPLETED, TracePhase.PROCESSING,
            message=f"Research completed: {len(source_items)} sources",
            output_summary={
                "total_sources": len(source_items),
                "total_queries": len(expanded),
                "total_raw_results": len(raw_results),
                "total_after_dedup": len(deduped),
                "error_count": len(errors),
            },
            metrics={"duration_ms": total_duration_ms},
        )

        summary = ResearchResultSummary(
            task_id=task.id,
            topic=task.topic,
            status=task.status,
            total_queries=len(expanded),
            total_raw_results=len(raw_results),
            total_after_dedup=len(deduped),
            total_saved=len(source_items),
            provider_errors=errors,
        )

        logger.info(
            "research_completed task_id=%s queries=%d raw=%d deduped=%d saved=%d errors=%d",
            task.id,
            summary.total_queries,
            summary.total_raw_results,
            summary.total_after_dedup,
            summary.total_saved,
            len(errors),
        )

        return summary

    # ============================================================
    # LLM Plan Recording
    # ============================================================

    def _record_llm_plan(self, task_id: str) -> None:
        """记录 LLM 使用计划 — 哪些 task 可用、哪些禁用、哪些未实现。"""
        try:
            from app.tracing.llm_registry import get_all_task_info, RULE_ONLY_STEPS
            from core.config import get_settings

            settings = get_settings()
            all_tasks = get_all_task_info()

            enabled_tasks = [t.task_name for t in all_tasks if t.enabled and t.implemented]
            disabled_tasks = [t.task_name for t in all_tasks if not t.enabled]
            planned_tasks = [t.task_name for t in all_tasks if not t.implemented]
            templates_found = [t.task_name for t in all_tasks if t.prompt_template_exists]
            templates_missing = [t.task_name for t in all_tasks if t.prompt_template and not t.prompt_template_exists]

            get_recorder().record(
                task_id=task_id,
                step="llm_plan_created",
                phase=TracePhase.PLANNING,
                message=f"LLM plan: {len(enabled_tasks)} enabled, {len(disabled_tasks)} disabled",
                service="ResearchService",
                provider=settings.active_llm_provider,
                input_summary={
                    "active_provider": settings.active_llm_provider,
                    "enabled_tasks": enabled_tasks,
                    "disabled_tasks": disabled_tasks,
                    "planned_tasks": planned_tasks,
                    "prompt_templates_found": templates_found,
                    "prompt_templates_missing": templates_missing,
                    "rule_only_steps": RULE_ONLY_STEPS,
                },
            )
        except Exception as e:
            logger.debug("llm_plan_record_failed error=%s", str(e))

    # ============================================================
    # 语言规划
    # ============================================================

    async def _plan_language(self, task: ResearchTask) -> ResearchLanguagePlan | None:
        """生成语言规划。失败时返回 None，不阻断主流程。"""
        from app.services.research_language_planner import ResearchLanguagePlannerService

        try:
            planner = ResearchLanguagePlannerService(ai_gateway=self._ai_gateway)
            plan = await planner.plan(topic=task.topic, mode=task.mode)

            logger.info(
                "language_plan_generated task_id=%s user_language=%s working_language=%s "
                "output_language=%s search_strategy=%s canonical_topic=%s",
                task.id,
                plan.user_language.value,
                plan.working_language.value,
                plan.output_language.value,
                plan.search_strategy.value,
                plan.canonical_topic,
            )
            log_event(
                task.id,
                "language_plan_generated",
                f"Language plan: strategy={plan.search_strategy.value}, "
                f"working={plan.working_language.value}",
                payload={
                    "user_language": plan.user_language.value,
                    "working_language": plan.working_language.value,
                    "output_language": plan.output_language.value,
                    "search_strategy": plan.search_strategy.value,
                    "canonical_topic": plan.canonical_topic,
                },
            )
            return plan

        except Exception as e:
            logger.warning(
                "language_plan_failed task_id=%s error=%s",
                task.id, str(e),
            )
            log_event(
                task.id,
                "language_plan_failed",
                f"Language planning failed, using fallback: {e}",
                level="warning",
            )
            # Trace: record fallback
            get_recorder().record(
                task_id=task.id,
                step=TraceStep.LLM_CALL_FAILED,
                phase=TracePhase.PLANNING,
                level="warning",
                message=f"Language planning fallback: {str(e)[:100]}",
                service="ResearchLanguagePlannerService",
                input_summary={"task_name": "language_planning"},
                error_message=str(e)[:200],
            )
            return None

    # ============================================================
    # Query Expansion（语言规划感知）
    # ============================================================

    async def _expand_queries_with_plan(
        self,
        task: ResearchTask,
        language_plan: ResearchLanguagePlan | None,
    ) -> list[RichExpandedQuery]:
        """使用 QueryExpansionService 扩展 query，带语言规划。"""
        service = QueryExpansionService(ai_gateway=self._ai_gateway)
        return await service.expand(
            topic=task.topic,
            mode=task.mode,
            include_books=task.include_books,
            include_video=task.include_video,
            include_gossip=task.include_gossip,
            language_plan=language_plan,
        )

    # ============================================================
    # 搜索（支持 RichExpandedQuery）
    # ============================================================

    async def _collect_search_results_rich(
        self, queries: list[RichExpandedQuery]
    ) -> tuple[list[SearchResult], list[str]]:
        """并发执行搜索（RichExpandedQuery 版本）。优先使用 SearchRouter。"""
        # 优先使用 SearchRouter（免费 MVP 路径）
        if self._search_router is not None:
            try:
                results = await self._search_router.search_many(queries)
                return results, []
            except Exception as e:
                logger.warning("search_router_failed fallback_to_legacy error=%s", str(e))

        # 尝试延迟初始化 SearchRouter（仅在非 legacy 模式下）
        if not self._use_legacy_providers and self._search_router is None:
            try:
                from services.search_router import SearchRouter
                self._search_router = SearchRouter()
                results = await self._search_router.search_many(queries)
                return results, []
            except Exception as e:
                logger.debug("search_router_init_failed using_legacy error=%s", str(e))

        # Legacy: 直接使用 provider dict
        settings = get_settings()
        limit = settings.default_result_limit

        tasks = []
        for query in queries:
            hint = query.source_hint if isinstance(query.source_hint, str) else query.source_hint.value
            providers = self._providers.get(hint, self._providers.get("web", []))
            for provider in providers:
                tasks.append(self._search_with_semaphore(provider, query.query, limit))

        results_nested = await asyncio.gather(*tasks)

        all_results: list[SearchResult] = []
        all_errors: list[str] = []

        for item in results_nested:
            if isinstance(item, list):
                all_results.extend(item)
            else:
                all_errors.append(item)

        return all_results, all_errors

    async def _collect_search_results(
        self, queries: list[ExpandedQuery]
    ) -> tuple[list[SearchResult], list[str]]:
        """并发执行搜索，限制并发数。返回 (结果列表, 错误列表)。"""
        settings = get_settings()
        limit = settings.default_result_limit

        tasks = []
        for query in queries:
            providers = self._providers.get(query.source_hint, self._providers.get("web", []))
            for provider in providers:
                tasks.append(self._search_with_semaphore(provider, query.query, limit))

        results_nested = await asyncio.gather(*tasks)

        all_results: list[SearchResult] = []
        all_errors: list[str] = []

        for item in results_nested:
            if isinstance(item, list):
                all_results.extend(item)
            else:
                all_errors.append(item)

        return all_results, all_errors

    async def _search_with_semaphore(
        self, provider: BaseSearchProvider, query: str, limit: int
    ) -> list[SearchResult] | str:
        """带并发限制的搜索。成功返回结果列表，失败返回错误字符串。"""
        async with self._semaphore:
            try:
                return await provider.search(query, limit)
            except SearchProviderError as e:
                error_msg = f"{e.provider}: {e.message}"
                logger.error(
                    "provider_search_failed provider=%s query=%s error=%s",
                    e.provider,
                    query,
                    e.message,
                )
                return error_msg
            except Exception as e:
                error_msg = f"{provider.provider_name}: {type(e).__name__}: {e}"
                logger.error(
                    "provider_search_failed provider=%s query=%s error=%s",
                    provider.provider_name,
                    query,
                    str(e),
                )
                return error_msg

    def _to_source_items(self, task_id: str, scored_results: list, language_plan: ResearchLanguagePlan | None = None) -> list[SourceItem]:
        """将评分结果转换为 SourceItem 列表，附加语言元数据。"""
        items: list[SourceItem] = []

        for scored in scored_results:
            candidate = scored.candidate
            s = scored.scoring
            domain = urlparse(candidate.url).netloc.lower()

            item = SourceItem(
                task_id=task_id,
                title=candidate.title,
                url=candidate.url,
                domain=domain,
                snippet=candidate.snippet,
                published_at=None,
                source_type=candidate.source_type,
                source_level=s.source_level,
                relevance_score=s.relevance_score,
                authority_score=s.authority_score,
                originality_score=s.originality_score,
                gossip_score=s.gossip_score,
                downloadable=True,
                download_status=DownloadStatus.PENDING,
                reason_to_read=s.reason_to_read,
            )

            # 附加语言元数据（runtime only，不影响 DB）
            if language_plan:
                item.canonical_topic = language_plan.canonical_topic or None
                item.original_topic = language_plan.original_topic or None
                # query_language 和 matched_query 在搜索阶段更精确，
                # 这里用 working_language 作为默认
                if language_plan.working_language != LanguageCode.UNKNOWN:
                    item.query_language = language_plan.working_language
                # source_language 先设为 query_language，后续由正文检测覆盖
                item.source_language = item.query_language

            items.append(item)

        return items
