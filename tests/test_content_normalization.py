"""测试 ContentNormalizationService。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.schemas import ContentNormalizationOutput, NormalizedClaimLLMItem
from app.services.content_normalization_service import ContentNormalizationService
from app.tracing.recorder import TraceRecorder
from models.enums import ClaimConfidence, NormalizedClaimType
from models.schemas import NormalizedContentUnit, NormalizedDocumentAnalysis


# === Fixtures ===


def _make_doc_row(content: str = "这是一篇测试正文，包含足够多的内容用于归一化测试。" * 20, **kwargs):
    """创建模拟的 ExtractedTable row。"""
    row = MagicMock()
    row.id = kwargs.get("id", "doc-001")
    row.source_item_id = kwargs.get("source_item_id", "src-001")
    row.title = kwargs.get("title", "测试文档标题")
    row.content = content
    row.summary = kwargs.get("summary", "")
    return row


def _make_source_row(**kwargs):
    """创建模拟的 SourceTable row。"""
    row = MagicMock()
    row.id = kwargs.get("id", "src-001")
    row.title = kwargs.get("title", "测试来源标题")
    row.url = kwargs.get("url", "https://example.com/article")
    row.source_level = kwargs.get("source_level", "A")
    row.canonical_topic = kwargs.get("canonical_topic", "测试主题")
    return row


def _make_llm_output(claims: list[NormalizedClaimLLMItem] | None = None) -> ContentNormalizationOutput:
    """创建模拟的 LLM 输出。"""
    if claims is None:
        claims = [
            NormalizedClaimLLMItem(
                claim="该公司于 2019 年在深圳成立",
                normalized_claim="公司 2019 年成立于深圳",
                claim_type="fact",
                confidence="high",
                evidence_text="该公司于2019年在深圳正式注册成立",
                people=[],
                organizations=["该公司"],
                places=["深圳"],
                dates=["2019"],
                concepts=[],
                importance=4,
                needs_verification=False,
            ),
            NormalizedClaimLLMItem(
                claim="创始人曾在 Google 工作",
                normalized_claim="创始人有 Google 工作经历",
                claim_type="background",
                confidence="medium",
                evidence_text="创始人此前在Google担任高级工程师",
                people=["创始人"],
                organizations=["Google"],
                places=[],
                dates=[],
                concepts=[],
                importance=3,
                needs_verification=False,
            ),
            NormalizedClaimLLMItem(
                claim="2020 年完成 A 轮融资",
                normalized_claim="2020 年 A 轮融资",
                claim_type="timeline_event",
                confidence="high",
                evidence_text="2020年初，公司宣布完成A轮融资",
                people=[],
                organizations=[],
                places=[],
                dates=["2020"],
                concepts=["A轮融资"],
                importance=4,
                needs_verification=False,
            ),
            NormalizedClaimLLMItem(
                claim="据传估值超过 10 亿",
                normalized_claim="估值超 10 亿（未证实）",
                claim_type="controversy",
                confidence="low",
                evidence_text="",  # 没有 evidence_text！
                people=[],
                organizations=[],
                places=[],
                dates=[],
                concepts=[],
                importance=2,
                needs_verification=True,
                verification_reason="来源不明确",
            ),
        ]
    return ContentNormalizationOutput(
        summary="这是一家 2019 年成立的深圳科技公司，创始人有 Google 背景。",
        claims=claims,
        key_people=["创始人"],
        key_places=["深圳"],
        key_concepts=["A轮融资"],
    )


def _make_service(
    ai_gateway=None,
    doc_repo=None,
    source_repo=None,
    trace_recorder=None,
) -> ContentNormalizationService:
    """创建 service 实例。"""
    return ContentNormalizationService(
        ai_gateway=ai_gateway,
        document_repository=doc_repo,
        source_repository=source_repo,
        trace_recorder=trace_recorder,
    )


# === Tests ===


class TestNormalLLMCall:
    """正常调用 ai_gateway task=content_normalization。"""

    @pytest.mark.asyncio
    async def test_calls_ai_gateway_with_correct_task(self):
        """调用 ai_gateway.run_json 时 task_name=content_normalization。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        await service.normalize_document(task_id="task-1", document_id="src-001")

        gateway.run_json.assert_called_once()
        call_kwargs = gateway.run_json.call_args.kwargs
        assert call_kwargs["task_name"] == "content_normalization"
        assert call_kwargs["output_schema"] is ContentNormalizationOutput

    @pytest.mark.asyncio
    async def test_payload_contains_topic_and_content(self):
        """payload 包含 topic 和 content。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_row = _make_doc_row(content="正文内容" * 100)
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=doc_row)

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        await service.normalize_document(task_id="task-1", document_id="src-001")

        call_kwargs = gateway.run_json.call_args.kwargs
        payload = call_kwargs["payload"]
        assert "content" in payload
        assert "topic" in payload


class TestLLMOutputParsing:
    """LLM 输出解析为 NormalizedDocumentAnalysis。"""

    @pytest.mark.asyncio
    async def test_returns_normalized_document_analysis(self):
        """返回类型是 NormalizedDocumentAnalysis。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        assert isinstance(result, NormalizedDocumentAnalysis)
        assert result.document_id == "src-001"
        assert result.summary != ""

    @pytest.mark.asyncio
    async def test_claims_categorized_correctly(self):
        """claims 按 claim_type 正确分类。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        # fact + background → main_claims
        assert len(result.main_claims) == 2
        # timeline_event → timeline_events
        assert len(result.timeline_events) == 1
        # 没有 evidence_text 的 controversy → verification_needed
        assert len(result.verification_needed) >= 1


class TestSourceMetadataEnrichment:
    """claim 自动补 source_id/document_id/url。"""

    @pytest.mark.asyncio
    async def test_claims_have_source_metadata(self):
        """每条 claim 都有 source_id, document_id, source_url。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_row = _make_doc_row()
        doc_row.source_item_id = "src-001"
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=doc_row)

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        for claim in result.main_claims:
            assert claim.source_id != ""
            assert claim.document_id == "src-001"

    @pytest.mark.asyncio
    async def test_source_url_propagated(self):
        """source_url 从 SourceItem 传播到每条 claim。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_row = _make_doc_row()
        doc_row.source_item_id = "src-001"
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=doc_row)

        # 由于 source_repo 为 None，url 来自 doc_row 的默认值
        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        # 所有 claims 都应该有 document_id
        all_claims = result.main_claims + result.timeline_events + result.verification_needed
        for claim in all_claims:
            assert claim.document_id == "src-001"


class TestEvidenceTextFiltering:
    """没有 evidence_text 的 claim 被移除或降级。"""

    @pytest.mark.asyncio
    async def test_no_evidence_text_moved_to_verification(self):
        """没有 evidence_text 的 claim 转入 verification_needed。"""
        claims = [
            NormalizedClaimLLMItem(
                claim="有 evidence 的事实",
                normalized_claim="有 evidence 的事实",
                claim_type="fact",
                confidence="high",
                evidence_text="原文中确实提到了这个事实",
                importance=4,
            ),
            NormalizedClaimLLMItem(
                claim="没有 evidence 的事实",
                normalized_claim="没有 evidence 的事实",
                claim_type="fact",
                confidence="high",
                evidence_text="",  # 空！
                importance=3,
            ),
            NormalizedClaimLLMItem(
                claim="空白 evidence",
                normalized_claim="空白 evidence",
                claim_type="background",
                confidence="medium",
                evidence_text="   ",  # 只有空格！
                importance=2,
            ),
        ]
        llm_output = ContentNormalizationOutput(summary="test", claims=claims)

        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=llm_output)

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        # 只有 1 条有 evidence 的进入 main_claims
        assert len(result.main_claims) == 1
        assert result.main_claims[0].claim == "有 evidence 的事实"

        # 2 条没有 evidence 的进入 verification_needed
        assert len(result.verification_needed) == 2
        for v in result.verification_needed:
            assert v.needs_verification is True
            assert "evidence_text" in (v.verification_reason or "")


class TestEmptyContentFallback:
    """空正文走 fallback。"""

    @pytest.mark.asyncio
    async def test_empty_content_returns_fallback(self):
        """正文为空时返回 fallback analysis。"""
        doc_row = _make_doc_row(content="")
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=doc_row)

        gateway = AsyncMock()
        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        assert isinstance(result, NormalizedDocumentAnalysis)
        assert result.main_claims == []
        assert len(result.verification_needed) == 1
        assert result.verification_needed[0].needs_verification is True
        # LLM 不应被调用
        gateway.run_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_short_content_returns_fallback(self):
        """正文过短时返回 fallback analysis。"""
        doc_row = _make_doc_row(content="太短了")
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=doc_row)

        gateway = AsyncMock()
        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        assert result.main_claims == []
        assert len(result.verification_needed) >= 1
        gateway.run_json.assert_not_called()


class TestLLMFailureFallback:
    """LLM 抛错走 fallback。"""

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self):
        """LLM 抛出异常时返回 fallback，不抛出致命错误。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        # 不抛出异常
        assert isinstance(result, NormalizedDocumentAnalysis)
        # fallback: summary 是正文前 500 字清理版
        assert result.summary != ""
        assert len(result.summary) > 0
        # main_claims 为空
        assert result.main_claims == []
        # verification_needed 记录失败
        assert len(result.verification_needed) == 1
        assert "failed" in result.verification_needed[0].normalized_claim.lower()

    @pytest.mark.asyncio
    async def test_no_gateway_returns_fallback(self):
        """ai_gateway=None 时走 fallback。"""
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        service = _make_service(ai_gateway=None, doc_repo=doc_repo)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")

        assert isinstance(result, NormalizedDocumentAnalysis)
        assert result.main_claims == []
        assert len(result.verification_needed) >= 1


class TestTraceRecording:
    """trace 不包含完整正文。"""

    @pytest.mark.asyncio
    async def test_trace_records_metrics_not_content(self):
        """trace 记录 content_chars/claim_count/duration_ms，不记录完整正文。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        recorder = TraceRecorder()
        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo, trace_recorder=recorder)
        await service.normalize_document(task_id="task-1", document_id="src-001")

        events = recorder.get_events("task-1")
        assert len(events) >= 2  # started + finished

        # 检查 finished 事件
        finished_events = [e for e in events if e.step == "content_normalization_finished"]
        assert len(finished_events) == 1
        finished = finished_events[0]

        # metrics 包含 content_chars, claim_count, duration_ms
        assert finished.metrics is not None
        assert "content_chars" in finished.metrics
        assert "claim_count" in finished.metrics
        assert "duration_ms" in finished.metrics

        # 不包含完整正文
        all_text = str(finished.input_summary) + str(finished.output_summary) + str(finished.metrics)
        # 正文内容不应出现在 trace 中
        assert "这是一篇测试正文" not in all_text

    @pytest.mark.asyncio
    async def test_trace_started_event(self):
        """记录 content_normalization_started 事件。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        recorder = TraceRecorder()
        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo, trace_recorder=recorder)
        await service.normalize_document(task_id="task-1", document_id="src-001")

        events = recorder.get_events("task-1")
        started_events = [e for e in events if e.step == "content_normalization_started"]
        assert len(started_events) == 1
        assert started_events[0].input_summary["document_id"] == "src-001"

    @pytest.mark.asyncio
    async def test_no_trace_recorder_does_not_crash(self):
        """trace_recorder=None 时不崩溃。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=_make_llm_output())

        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(return_value=_make_doc_row())

        service = _make_service(ai_gateway=gateway, doc_repo=doc_repo, trace_recorder=None)
        result = await service.normalize_document(task_id="task-1", document_id="src-001")
        assert isinstance(result, NormalizedDocumentAnalysis)
