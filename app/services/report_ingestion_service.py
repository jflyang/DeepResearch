"""报告导入编排服务。

流程：读取 report_text → 解析引用 → LLM 增强（可选）→ 转 candidates → 处理 URL → enrichment books/papers → 返回结果。
LLM 失败时仍可运行，不绕过 paywall，不抓书籍全文。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from models.enums import DownloadStatus, ReferenceType, SourceOrigin, TaskStatus
from models.schemas import (
    ExpandedQuery,
    ParsedReport,
    ReferenceCandidate,
    ReportIngestionResult,
    SourceItem,
)

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway
    from app.services.reference_extraction_service import ReferenceExtractionService
    from app.services.report_llm_analyzer import ReportLLMAnalyzer
    from app.services.report_parser_service import ReportParserService
    from app.tracing.recorder import TraceRecorder
    from db.repositories import SourceRepository, TaskRepository
    from providers.search.base import SearchResult
    from services.extraction_service import ExtractionService
    from services.search_router import SearchRouter

logger = logging.getLogger(__name__)


class ReportIngestionService:
    """报告导入编排服务。"""

    def __init__(
        self,
        report_parser: ReportParserService,
        reference_extractor: ReferenceExtractionService,
        extraction_service: ExtractionService,
        source_repository: SourceRepository,
        task_repository: TaskRepository,
        search_router: SearchRouter | None = None,
        trace_recorder: TraceRecorder | None = None,
        reports_dir: Path | None = None,
        llm_analyzer: ReportLLMAnalyzer | None = None,
    ):
        self._parser = report_parser
        self._ref_extractor = reference_extractor
        self._extraction_service = extraction_service
        self._source_repo = source_repository
        self._task_repo = task_repository
        self._search_router = search_router
        self._trace = trace_recorder
        self._reports_dir = reports_dir
        self._llm_analyzer = llm_analyzer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse_task_report(self, task_id: str) -> ParsedReport:
        """读取 task 的 report_text 并解析。"""
        report_text = self._task_repo.load_imported_report_text(
            task_id, reports_dir=self._reports_dir
        )
        if not report_text:
            raise ValueError(f"No report_text found for task_id={task_id}")

        self._trace_info(task_id, "report_parse_started", "开始解析报告")
        parsed = self._parser.parse(report_text)
        self._trace_info(
            task_id,
            "report_parse_finished",
            f"解析完成: urls={len(parsed.urls)} books={len(parsed.books)} papers={len(parsed.papers)}",
            output_summary={
                "url_count": len(parsed.urls),
                "book_count": len(parsed.books),
                "paper_count": len(parsed.papers),
            },
        )
        return parsed

    async def run_import_task(self, task_id: str) -> ReportIngestionResult:
        """执行完整的报告导入流程。"""
        # 更新状态为 running
        self._task_repo.update_task_status(task_id, TaskStatus.RUNNING)

        try:
            # 1. 解析报告
            parsed = await self.parse_task_report(task_id)

            # 2. LLM 增强（可选，失败不影响主流程）
            report_text = self._task_repo.load_imported_report_text(
                task_id, reports_dir=self._reports_dir
            ) or ""
            llm_refs = await self._run_llm_enhancement(task_id, report_text, parsed)

            # 3. 转换为 candidates（规则）
            candidates = self._ref_extractor.extract(parsed)
            rule_count = len(candidates)

            # 4. 合并 LLM 引用
            llm_count = len(llm_refs)
            if llm_refs:
                candidates = self._merge_llm_references(candidates, llm_refs)

            self._trace_info(
                task_id,
                "reference_merge_finished",
                f"引用合并完成: rule={rule_count} llm={llm_count} merged={len(candidates)}",
                output_summary={
                    "rule_reference_count": rule_count,
                    "llm_reference_count": llm_count,
                    "merged_reference_count": len(candidates),
                    "duplicate_removed_count": rule_count + llm_count - len(candidates),
                },
            )

            # 5. 分类 candidates
            url_candidates = [c for c in candidates if c.type == ReferenceType.URL]
            book_candidates = [c for c in candidates if c.type == ReferenceType.BOOK]
            paper_candidates = [c for c in candidates if c.type == ReferenceType.PAPER]

            # 4. 处理 URL：直接抓取
            extracted_count, url_failed_count, url_sources = await self._process_urls(
                task_id, url_candidates
            )

            # 5. 处理 books：通过 SearchRouter 补充检索
            enriched_book_count, book_failed_count, book_sources = await self._enrich_books(
                task_id, book_candidates
            )

            # 6. 处理 papers：通过 SearchRouter 补充检索
            enriched_paper_count, paper_failed_count, paper_sources = await self._enrich_papers(
                task_id, paper_candidates
            )

            # 7. 汇总
            all_sources = url_sources + book_sources + paper_sources
            total_failed = url_failed_count + book_failed_count + paper_failed_count
            enriched_source_count = enriched_book_count + enriched_paper_count

            # 8. 更新任务状态
            self._task_repo.update_task_status(task_id, TaskStatus.COMPLETED)

            result = ReportIngestionResult(
                task_id=task_id,
                parsed_url_count=len(parsed.urls),
                parsed_book_count=len(parsed.books),
                parsed_paper_count=len(parsed.papers),
                extracted_document_count=extracted_count,
                enriched_source_count=enriched_source_count,
                enriched_book_count=enriched_book_count,
                enriched_paper_count=enriched_paper_count,
                failed_count=total_failed,
                source_count=len(all_sources),
            )

            self._trace_info(
                task_id,
                "report_ingestion_completed",
                f"报告导入完成: sources={result.source_count} extracted={extracted_count} "
                f"enriched_books={enriched_book_count} enriched_papers={enriched_paper_count}",
                output_summary=result.model_dump(),
            )

            return result

        except Exception as e:
            logger.exception("report_ingestion_failed task_id=%s", task_id)
            self._task_repo.update_task_status(
                task_id, TaskStatus.FAILED, error_message=str(e)[:500]
            )
            raise

    # ------------------------------------------------------------------
    # URL processing
    # ------------------------------------------------------------------

    async def _process_urls(
        self, task_id: str, candidates: list[ReferenceCandidate]
    ) -> tuple[int, int, list[SourceItem]]:
        """处理 URL candidates：创建 SourceItem + 抓取正文。"""
        if not candidates:
            return 0, 0, []

        self._trace_info(
            task_id,
            "url_extraction_started",
            f"开始处理 {len(candidates)} 个 URL",
            input_summary={"url_count": len(candidates)},
        )

        extracted_count = 0
        failed_count = 0
        source_items: list[SourceItem] = []

        for candidate in candidates:
            source_item = self._create_source_item(
                task_id, candidate, SourceOrigin.IMPORTED_REPORT
            )
            source_items.append(source_item)
            self._save_source_item(source_item)

            try:
                doc = await self._extraction_service.extract_source(source_item)
                if doc.content:
                    extracted_count += 1
                    source_item.download_status = DownloadStatus.EXTRACTED
                else:
                    failed_count += 1
                    source_item.download_status = DownloadStatus.FAILED
            except Exception as e:
                failed_count += 1
                source_item.download_status = DownloadStatus.FAILED
                logger.warning(
                    "url_extraction_failed task_id=%s url=%s error=%s",
                    task_id, candidate.value, str(e),
                )

        self._trace_info(
            task_id,
            "url_extraction_finished",
            f"URL 处理完成: extracted={extracted_count} failed={failed_count}",
            output_summary={
                "extracted_count": extracted_count,
                "failed_count": failed_count,
                "total_urls": len(candidates),
            },
        )

        return extracted_count, failed_count, source_items

    # ------------------------------------------------------------------
    # Book enrichment
    # ------------------------------------------------------------------

    async def _enrich_books(
        self, task_id: str, candidates: list[ReferenceCandidate]
    ) -> tuple[int, int, list[SourceItem]]:
        """通过 SearchRouter 补充检索书籍来源。"""
        if not candidates or not self._search_router:
            return 0, 0, []

        self._trace_info(
            task_id,
            "book_enrichment_started",
            f"开始补充检索 {len(candidates)} 本书籍",
            input_summary={"book_count": len(candidates)},
        )

        enriched_count = 0
        failed_count = 0
        source_items: list[SourceItem] = []
        seen_urls: set[str] = set()

        for candidate in candidates:
            try:
                query = ExpandedQuery(
                    query=candidate.value,
                    source_hint="book",
                    purpose=f"enrichment for book: {candidate.value}",
                )
                results = await self._search_router.search_one(query, limit=5)

                for result in results:
                    url_key = result.url.strip().lower().rstrip("/")
                    if url_key in seen_urls:
                        continue
                    seen_urls.add(url_key)

                    source_item = self._create_enriched_source_item(
                        task_id, result, candidate
                    )
                    source_items.append(source_item)
                    self._save_source_item(source_item)
                    enriched_count += 1

            except Exception as e:
                failed_count += 1
                logger.warning(
                    "book_enrichment_failed task_id=%s book=%s error=%s",
                    task_id, candidate.value, str(e),
                )

        self._trace_info(
            task_id,
            "book_enrichment_finished",
            f"书籍补充完成: enriched={enriched_count} failed={failed_count}",
            output_summary={
                "enriched_count": enriched_count,
                "failed_count": failed_count,
            },
        )

        return enriched_count, failed_count, source_items

    # ------------------------------------------------------------------
    # Paper enrichment
    # ------------------------------------------------------------------

    async def _enrich_papers(
        self, task_id: str, candidates: list[ReferenceCandidate]
    ) -> tuple[int, int, list[SourceItem]]:
        """通过 SearchRouter 补充检索论文来源。"""
        if not candidates or not self._search_router:
            return 0, 0, []

        self._trace_info(
            task_id,
            "paper_enrichment_started",
            f"开始补充检索 {len(candidates)} 篇论文",
            input_summary={"paper_count": len(candidates)},
        )

        enriched_count = 0
        failed_count = 0
        source_items: list[SourceItem] = []
        seen_keys: set[str] = set()

        for candidate in candidates:
            try:
                # 构建查询：优先 DOI/arXiv，其次 title
                query_text = candidate.value
                query = ExpandedQuery(
                    query=query_text,
                    source_hint="paper",
                    purpose=f"enrichment for paper: {query_text}",
                )
                results = await self._search_router.search_one(query, limit=5)

                for result in results:
                    # 去重：URL + title
                    dedup_key = result.url.strip().lower().rstrip("/")
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    source_item = self._create_enriched_source_item(
                        task_id, result, candidate
                    )
                    source_items.append(source_item)
                    self._save_source_item(source_item)
                    enriched_count += 1

            except Exception as e:
                failed_count += 1
                logger.warning(
                    "paper_enrichment_failed task_id=%s paper=%s error=%s",
                    task_id, candidate.value, str(e),
                )

        self._trace_info(
            task_id,
            "paper_enrichment_finished",
            f"论文补充完成: enriched={enriched_count} failed={failed_count}",
            output_summary={
                "enriched_count": enriched_count,
                "failed_count": failed_count,
            },
        )

        return enriched_count, failed_count, source_items

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_source_item(
        self, task_id: str, candidate: ReferenceCandidate, origin: str
    ) -> SourceItem:
        """从 ReferenceCandidate 创建 SourceItem。"""
        domain = ""
        try:
            domain = urlparse(candidate.value).netloc.lower()
        except Exception:
            pass

        return SourceItem(
            task_id=task_id,
            title=candidate.title_hint or candidate.value,
            url=candidate.value,
            domain=domain,
            source_type="web",
            source_origin=origin,
            download_status=DownloadStatus.PENDING,
            reason_to_read="外部研究报告中引用的来源",
        )

    def _create_enriched_source_item(
        self, task_id: str, result, candidate: ReferenceCandidate
    ) -> SourceItem:
        """从 SearchResult 创建 enriched SourceItem。"""
        domain = ""
        try:
            domain = urlparse(result.url).netloc.lower()
        except Exception:
            pass

        return SourceItem(
            task_id=task_id,
            title=result.title or candidate.title_hint or candidate.value,
            url=result.url,
            domain=domain,
            snippet=result.snippet or "",
            source_type=result.source_type if hasattr(result, "source_type") else "web",
            source_origin=SourceOrigin.IMPORTED_REPORT_ENRICHED,
            download_status=DownloadStatus.PENDING,
            reason_to_read=f"补充检索: {candidate.value}",
        )

    def _save_source_item(self, source_item: SourceItem) -> None:
        """保存 SourceItem 到 DB。"""
        try:
            self._source_repo.bulk_create([{
                "id": source_item.id,
                "task_id": source_item.task_id,
                "title": source_item.title,
                "url": source_item.url,
                "domain": source_item.domain,
                "source_type": source_item.source_type if isinstance(source_item.source_type, str) else source_item.source_type.value,
                "download_status": source_item.download_status if isinstance(source_item.download_status, str) else source_item.download_status.value,
                "reason_to_read": source_item.reason_to_read,
            }])
        except Exception as e:
            logger.warning("save_source_item_failed id=%s error=%s", source_item.id, str(e))

    def _trace_info(
        self,
        task_id: str,
        step: str,
        message: str,
        input_summary: dict | None = None,
        output_summary: dict | None = None,
    ) -> None:
        """记录 trace 事件（如果 recorder 可用）。"""
        if self._trace:
            self._trace.record(
                task_id=task_id,
                step=step,
                phase="ingestion",
                level="info",
                message=message,
                service="ReportIngestionService",
                input_summary=input_summary,
                output_summary=output_summary,
            )

    # ------------------------------------------------------------------
    # LLM Enhancement
    # ------------------------------------------------------------------

    async def _run_llm_enhancement(
        self, task_id: str, report_text: str, parsed: ParsedReport
    ) -> list[ReferenceCandidate]:
        """运行 LLM 增强，返回额外的 ReferenceCandidate。失败返回空列表。"""
        if not self._llm_analyzer or not self._llm_analyzer.available:
            self._trace_info(task_id, "llm_enhancement_skipped", "LLM 不可用，跳过增强")
            return []

        extra_candidates: list[ReferenceCandidate] = []

        # 1. 报告理解
        try:
            self._trace_info(task_id, "report_understanding_started", "开始 LLM 报告理解")
            understanding = await self._llm_analyzer.understand_report(
                report_text=report_text, topic="", output_language="zh"
            )
            self._trace_info(
                task_id,
                "report_understanding_finished",
                f"报告理解完成: entities={len(understanding.main_entities)} "
                f"claims={len(understanding.claims_to_verify)}",
                output_summary={
                    "status": "used_llm",
                    "main_entities_count": len(understanding.main_entities),
                    "claims_count": len(understanding.claims_to_verify),
                    "search_queries_count": len(understanding.suggested_search_queries),
                },
            )
        except Exception as e:
            self._trace_info(
                task_id, "report_understanding_fallback",
                f"报告理解失败，使用 fallback: {str(e)[:100]}",
                output_summary={"status": "fallback", "reason": str(e)[:200]},
            )

        # 2. 隐性引用提取
        try:
            self._trace_info(task_id, "report_reference_extraction_started", "开始 LLM 引用提取")
            ref_output = await self._llm_analyzer.extract_implicit_references(
                report_text=report_text, parsed_report=parsed, topic="", output_language="zh"
            )
            # 转换 ImplicitReference → ReferenceCandidate
            from models.enums import ReferenceStatus
            for ref in ref_output.additional_references:
                ref_type = self._map_implicit_type(ref.type.value if hasattr(ref.type, "value") else str(ref.type))
                value = ref.url or ref.doi_hint or ref.arxiv_id or ref.title
                if not value:
                    continue
                extra_candidates.append(ReferenceCandidate(
                    type=ref_type,
                    value=value,
                    title_hint=ref.title or None,
                    source_url=ref.url,
                    status=ReferenceStatus.PARSED,
                    confidence=ref.confidence,
                    metadata={
                        "source": "llm",
                        "reason": ref.reason,
                        "search_query": ref.search_query,
                        "author_hint": ref.author_hint,
                        "year_hint": ref.year_hint,
                    },
                ))

            self._trace_info(
                task_id,
                "report_reference_extraction_finished",
                f"LLM 引用提取完成: additional={len(extra_candidates)}",
                output_summary={
                    "status": "used_llm",
                    "additional_references_count": len(extra_candidates),
                    "additional_queries_count": len(ref_output.additional_search_queries),
                },
            )
        except Exception as e:
            self._trace_info(
                task_id, "report_reference_extraction_fallback",
                f"LLM 引用提取失败，使用 fallback: {str(e)[:100]}",
                output_summary={"status": "fallback", "reason": str(e)[:200]},
            )

        return extra_candidates

    @staticmethod
    def _map_implicit_type(type_str: str) -> ReferenceType:
        """将 ImplicitReferenceType 映射到 ReferenceType。"""
        mapping = {
            "url": ReferenceType.URL,
            "book": ReferenceType.BOOK,
            "paper": ReferenceType.PAPER,
            "interview": ReferenceType.ARTICLE,
            "video": ReferenceType.VIDEO,
            "article": ReferenceType.ARTICLE,
            "archive": ReferenceType.UNKNOWN,
            "unknown": ReferenceType.UNKNOWN,
        }
        return mapping.get(type_str, ReferenceType.UNKNOWN)

    @staticmethod
    def _merge_llm_references(
        rule_candidates: list[ReferenceCandidate],
        llm_candidates: list[ReferenceCandidate],
    ) -> list[ReferenceCandidate]:
        """合并规则和 LLM 引用，去重。"""
        # 构建已有 key 集合
        seen_keys: set[str] = set()
        for c in rule_candidates:
            seen_keys.add(c.value.strip().lower().rstrip("/"))

        merged = list(rule_candidates)
        for c in llm_candidates:
            key = c.value.strip().lower().rstrip("/")
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(c)

        return merged
