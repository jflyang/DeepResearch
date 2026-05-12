"""测试 ResearchSynthesisService。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.schemas import ResearchSynthesisOutput, SynthesisSectionLLMItem
from app.services.content_normalization_service import ContentNormalizationService
from app.services.cross_source_deduplication_service import CrossSourceDeduplicationService
from app.services.research_synthesis_service import ResearchSynthesisService
from app.tracing.recorder import TraceRecorder
from models.enums import ClaimConfidence, NormalizedClaimType
from models.schemas import (
    DeduplicatedClaimGroup,
    NormalizedContentUnit,
    NormalizedDocumentAnalysis,
    SynthesizedResearchDocument,
)


# === Fixtures ===


def _make_task_row(topic: str = "测试主题", **kwargs):
    row = MagicMock()
    row.id = kwargs.get("id", "task-001")
    row.topic = topic
    row.canonical_topic = kwargs.get("canonical_topic", None)
    row.mode = kwargs.get("mode", "person")
    return row


def _make_source_row(source_id: str = "src-1", **kwargs):
    row = MagicMock()
    row.id = source_id
    row.title = kwargs.get("title", "Source Title")
    row.url = kwargs.get("url", "https://example.com")
    row.source_level = kwargs.get("source_level", "A")
    row.download_status = kwargs.get("download_status", "extracted")
    row.source_type = kwargs.get("source_type", "news")
    return row


def _make_doc_row(source_item_id: str = "src-1", content: str = "正文内容" * 100, **kwargs):
    row = MagicMock()
    row.id = kwargs.get("id", "doc-1")
    row.source_item_id = source_item_id
    row.title = kwargs.get("title", "文档标题")
    row.content = content
    return row


def _make_analysis(
    source_id: str = "src-1",
    claims: list[NormalizedContentUnit] | None = None,
) -> NormalizedDocumentAnalysis:
    if claims is None:
        claims = [
            NormalizedContentUnit(
                document_id=source_id,
                source_id=source_id,
                source_title="Test Source",
                source_url="https://example.com",
                claim_type=NormalizedClaimType.FACT,
                claim="测试事实",
                normalized_claim="测试事实",
                evidence_text="原文证据",
                confidence=ClaimConfidence.HIGH,
                importance=4,
            ),
        ]
    return NormalizedDocumentAnalysis(
        document_id=source_id,
        source_id=source_id,
        source_title="Test Source",
        main_claims=claims,
    )


def _make_dedup_group(
    claim: str = "合并后的事实",
    confidence: ClaimConfidence = ClaimConfidence.HIGH,
    importance: int = 4,
    source_count: int = 2,
    claim_type: str = "fact",
    needs_verification: bool = False,
    dates: list[str] | None = None,
) -> DeduplicatedClaimGroup:
    sources = [
        {"source_id": f"src-{i}", "document_id": f"doc-{i}", "title": f"Source {i}", "url": f"https://{i}.com", "evidence_text": "证据"}
        for i in range(source_count)
    ]
    return DeduplicatedClaimGroup(
        group_id=f"grp-{claim[:8]}",
        normalized_claim=claim,
        claim_type=claim_type,
        merged_claim=claim,
        supporting_sources=sources,
        confidence=confidence,
        importance=importance,
        needs_verification=needs_verification,
        dates=dates or [],
    )


def _make_service(
    normalization_result: NormalizedDocumentAnalysis | None = None,
    dedup_result: list[DeduplicatedClaimGroup] | None = None,
    ai_gateway=None,
    task_row=None,
    sources=None,
    documents=None,
    trace_recorder=None,
) -> ResearchSynthesisService:
    """创建 service 实例，注入 mock 依赖。"""
    # Mock normalization service
    norm_service = AsyncMock(spec=ContentNormalizationService)
    norm_service.normalize_document = AsyncMock(
        return_value=normalization_result or _make_analysis()
    )

    # Mock deduplication service
    dedup_service = AsyncMock(spec=CrossSourceDeduplicationService)
    dedup_service.deduplicate = AsyncMock(
        return_value=dedup_result if dedup_result is not None else [_make_dedup_group()]
    )

    # Mock task repo
    task_repo = MagicMock()
    task_repo.get_task = MagicMock(return_value=task_row or _make_task_row())

    # Mock source repo
    source_repo = MagicMock()
    source_repo.get_by_task = MagicMock(
        return_value=sources if sources is not None else [_make_source_row()]
    )

    # Mock doc repo
    doc_repo = MagicMock()
    if documents is not None:
        doc_repo.get_by_source = MagicMock(side_effect=lambda sid: documents.get(sid))
    else:
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

    return ResearchSynthesisService(
        content_normalization_service=norm_service,
        deduplication_service=dedup_service,
        ai_gateway=ai_gateway,
        task_repository=task_repo,
        document_repository=doc_repo,
        source_repository=source_repo,
        trace_recorder=trace_recorder,
    )


# === Tests ===


class TestNormalizationCalled:
    """synthesize_task 会调用 normalization service。"""

    @pytest.mark.asyncio
    async def test_normalization_called_for_each_document(self):
        """每篇合格文档都调用 normalize_document。"""
        sources = [_make_source_row("src-1"), _make_source_row("src-2")]
        documents = {
            "src-1": _make_doc_row("src-1"),
            "src-2": _make_doc_row("src-2"),
        }

        service = _make_service(sources=sources, documents=documents)
        await service.synthesize_task(task_id="task-001")

        # normalization 被调用 2 次
        assert service._normalization.normalize_document.call_count == 2


class TestDeduplicationCalled:
    """会调用 deduplication service。"""

    @pytest.mark.asyncio
    async def test_deduplication_called_with_analyses(self):
        """去重服务被调用，传入 analyses 列表。"""
        service = _make_service()
        await service.synthesize_task(task_id="task-001")

        service._deduplication.deduplicate.assert_called_once()
        call_kwargs = service._deduplication.deduplicate.call_args.kwargs
        assert call_kwargs["task_id"] == "task-001"
        assert isinstance(call_kwargs["analyses"], list)


class TestLLMSuccess:
    """LLM 成功时生成 SynthesizedResearchDocument。"""

    @pytest.mark.asyncio
    async def test_llm_output_used(self):
        """LLM 成功时使用 LLM 输出的 overview 和 executive_summary。"""
        llm_output = ResearchSynthesisOutput(
            overview="LLM 生成的研究概览",
            executive_summary="LLM 生成的摘要",
            sections=[],
            timeline=["2019：成立"],
            key_people=[{"name": "张三", "description": "创始人"}],
            suggested_next_steps=["深入研究"],
        )

        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=llm_output)

        dedup_groups = [
            _make_dedup_group("高置信度事实", ClaimConfidence.HIGH, source_count=3),
        ]

        service = _make_service(ai_gateway=gateway, dedup_result=dedup_groups)
        result = await service.synthesize_task(task_id="task-001")

        assert isinstance(result, SynthesizedResearchDocument)
        assert result.overview == "LLM 生成的研究概览"
        assert result.executive_summary == "LLM 生成的摘要"
        assert result.task_id == "task-001"
        assert result.topic == "测试主题"


class TestLLMFailureFallback:
    """LLM 失败时使用 fallback。"""

    @pytest.mark.asyncio
    async def test_llm_failure_returns_valid_document(self):
        """LLM 抛异常时 fallback 生成有效文档。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        dedup_groups = [
            _make_dedup_group("高置信度事实", ClaimConfidence.HIGH, source_count=2),
            _make_dedup_group("待核验事实", ClaimConfidence.LOW, needs_verification=True),
        ]

        service = _make_service(ai_gateway=gateway, dedup_result=dedup_groups)
        result = await service.synthesize_task(task_id="task-001")

        assert isinstance(result, SynthesizedResearchDocument)
        assert "测试主题" in result.overview
        assert result.task_id == "task-001"
        # fallback 仍然有 confirmed_facts
        assert len(result.confirmed_facts) == 1
        assert len(result.verification_needed) == 1

    @pytest.mark.asyncio
    async def test_no_gateway_uses_fallback(self):
        """ai_gateway=None 时使用 fallback。"""
        dedup_groups = [
            _make_dedup_group("事实A", ClaimConfidence.HIGH),
        ]

        service = _make_service(ai_gateway=None, dedup_result=dedup_groups)
        result = await service.synthesize_task(task_id="task-001")

        assert isinstance(result, SynthesizedResearchDocument)
        assert len(result.confirmed_facts) == 1


class TestConfirmedFactsHaveSources:
    """confirmed_facts 都有 supporting_sources。"""

    @pytest.mark.asyncio
    async def test_confirmed_facts_all_have_sources(self):
        """每个 confirmed_fact 都有至少一个 supporting_source。"""
        dedup_groups = [
            _make_dedup_group("事实1", ClaimConfidence.HIGH, source_count=2),
            _make_dedup_group("事实2", ClaimConfidence.HIGH, source_count=3),
            _make_dedup_group("低置信度", ClaimConfidence.LOW, source_count=1),
        ]

        service = _make_service(dedup_result=dedup_groups)
        result = await service.synthesize_task(task_id="task-001")

        for fact in result.confirmed_facts:
            assert len(fact.supporting_sources) > 0
            assert fact.confidence == ClaimConfidence.HIGH

    @pytest.mark.asyncio
    async def test_low_confidence_not_in_confirmed(self):
        """低置信度事实不进入 confirmed_facts。"""
        dedup_groups = [
            _make_dedup_group("低置信度事实", ClaimConfidence.LOW, source_count=1),
            _make_dedup_group("未验证事实", ClaimConfidence.UNVERIFIED, source_count=1),
        ]

        service = _make_service(dedup_result=dedup_groups)
        result = await service.synthesize_task(task_id="task-001")

        assert len(result.confirmed_facts) == 0


class TestNoDocuments:
    """没有文档时返回资料不足提示。"""

    @pytest.mark.asyncio
    async def test_no_sources_returns_insufficient(self):
        """没有 sources 时返回资料不足。"""
        service = _make_service(sources=[])
        result = await service.synthesize_task(task_id="task-001")

        assert isinstance(result, SynthesizedResearchDocument)
        assert "资料不足" in result.executive_summary or "暂无" in result.overview
        assert result.confirmed_facts == []

    @pytest.mark.asyncio
    async def test_no_extracted_docs_returns_insufficient(self):
        """sources 存在但没有已抓取文档时返回资料不足。"""
        sources = [_make_source_row("src-1", download_status="pending")]
        service = _make_service(sources=sources)
        result = await service.synthesize_task(task_id="task-001")

        assert "暂无" in result.overview or "资料不足" in result.executive_summary

    @pytest.mark.asyncio
    async def test_short_content_skipped(self):
        """正文过短的文档被跳过。"""
        sources = [_make_source_row("src-1")]
        documents = {"src-1": _make_doc_row("src-1", content="太短")}

        service = _make_service(sources=sources, documents=documents)
        result = await service.synthesize_task(task_id="task-001")

        assert "暂无" in result.overview or "资料不足" in result.executive_summary


class TestTimelineSorted:
    """timeline 按日期排序。"""

    @pytest.mark.asyncio
    async def test_timeline_sorted_by_date(self):
        """timeline groups 按 dates 排序。"""
        dedup_groups = [
            _make_dedup_group("2020事件", ClaimConfidence.HIGH, claim_type="timeline_event", dates=["2020"]),
            _make_dedup_group("2018事件", ClaimConfidence.HIGH, claim_type="timeline_event", dates=["2018"]),
            _make_dedup_group("2019事件", ClaimConfidence.HIGH, claim_type="timeline_event", dates=["2019"]),
        ]

        service = _make_service(dedup_result=dedup_groups)
        result = await service.synthesize_task(task_id="task-001")

        assert len(result.timeline) == 3
        # 验证排序
        timeline_dates = [g.dates[0] for g in result.timeline if g.dates]
        assert timeline_dates == ["2018", "2019", "2020"]


class TestTraceMetrics:
    """trace 记录 synthesis metrics。"""

    @pytest.mark.asyncio
    async def test_trace_records_all_metrics(self):
        """trace finished 事件包含所有要求的 metrics。"""
        dedup_groups = [
            _make_dedup_group("事实", ClaimConfidence.HIGH),
            _make_dedup_group("待验证", ClaimConfidence.LOW, needs_verification=True),
        ]

        recorder = TraceRecorder()
        service = _make_service(dedup_result=dedup_groups, trace_recorder=recorder)
        await service.synthesize_task(task_id="task-001")

        events = recorder.get_events("task-001")
        started = [e for e in events if e.step == "research_synthesis_started"]
        finished = [e for e in events if e.step == "research_synthesis_finished"]

        assert len(started) == 1
        assert len(finished) == 1

        metrics = finished[0].metrics
        assert "document_count" in metrics
        assert "normalized_count" in metrics
        assert "skipped_count" in metrics
        assert "claim_count" in metrics
        assert "deduplicated_group_count" in metrics
        assert "confirmed_fact_count" in metrics
        assert "verification_needed_count" in metrics
        assert "used_llm" in metrics
        assert "duration_ms" in metrics

    @pytest.mark.asyncio
    async def test_trace_no_content_leak(self):
        """trace 不包含完整正文。"""
        recorder = TraceRecorder()
        service = _make_service(trace_recorder=recorder)
        await service.synthesize_task(task_id="task-001")

        events = recorder.get_events("task-001")
        for event in events:
            all_text = str(event.input_summary) + str(event.output_summary) + str(event.metrics)
            # 不应包含大段正文
            assert "正文内容正文内容" not in all_text
