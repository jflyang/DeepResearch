"""测试 CrossSourceDeduplicationService。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.schemas import (
    CrossSourceDeduplicationOutput,
    DeduplicationConflictLLMItem,
    DeduplicationGroupLLMItem,
)
from app.services.cross_source_deduplication_service import CrossSourceDeduplicationService
from app.tracing.recorder import TraceRecorder
from models.enums import ClaimConfidence, NormalizedClaimType
from models.schemas import (
    DeduplicatedClaimGroup,
    NormalizedContentUnit,
    NormalizedDocumentAnalysis,
)


# === Fixtures ===


def _unit(
    claim: str,
    normalized_claim: str = "",
    source_id: str = "src-1",
    document_id: str = "doc-1",
    source_title: str = "Source A",
    source_url: str = "https://a.com",
    claim_type: NormalizedClaimType = NormalizedClaimType.FACT,
    confidence: ClaimConfidence = ClaimConfidence.MEDIUM,
    importance: int = 3,
    evidence_text: str = "原文片段",
    people: list[str] | None = None,
    dates: list[str] | None = None,
    places: list[str] | None = None,
    needs_verification: bool = False,
) -> NormalizedContentUnit:
    """快速创建 NormalizedContentUnit。"""
    return NormalizedContentUnit(
        document_id=document_id,
        source_id=source_id,
        source_title=source_title,
        source_url=source_url,
        claim_type=claim_type,
        claim=claim,
        normalized_claim=normalized_claim or claim,
        evidence_text=evidence_text,
        confidence=confidence,
        importance=importance,
        people=people or [],
        dates=dates or [],
        places=places or [],
        needs_verification=needs_verification,
    )


def _analysis(
    claims: list[NormalizedContentUnit],
    source_id: str = "src-1",
    document_id: str = "doc-1",
) -> NormalizedDocumentAnalysis:
    """快速创建 NormalizedDocumentAnalysis。"""
    return NormalizedDocumentAnalysis(
        document_id=document_id,
        source_id=source_id,
        source_title="Test Source",
        main_claims=claims,
    )


# === Tests ===


class TestSameNormalizedClaimMerge:
    """相同 normalized_claim 合并。"""

    @pytest.mark.asyncio
    async def test_identical_normalized_claims_merged(self):
        """完全相同的 normalized_claim 合并为一个 group。"""
        a1 = _analysis([
            _unit("公司于 2019 年成立", normalized_claim="公司2019年成立",
                  source_id="src-1", document_id="doc-1", source_title="Source A"),
        ], source_id="src-1", document_id="doc-1")

        a2 = _analysis([
            _unit("该公司在 2019 年创立", normalized_claim="公司2019年成立",
                  source_id="src-2", document_id="doc-2", source_title="Source B"),
        ], source_id="src-2", document_id="doc-2")

        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=[a1, a2])

        # 应该合并为 1 个 group
        assert len(result) == 1
        assert len(result[0].supporting_sources) == 2

    @pytest.mark.asyncio
    async def test_case_insensitive_merge(self):
        """normalized_claim 大小写不敏感合并。"""
        a1 = _analysis([
            _unit("Apple founded", normalized_claim="Apple Founded In 1976",
                  source_id="src-1", document_id="doc-1"),
        ])
        a2 = _analysis([
            _unit("apple founded", normalized_claim="apple founded in 1976",
                  source_id="src-2", document_id="doc-2"),
        ], source_id="src-2", document_id="doc-2")

        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=[a1, a2])

        assert len(result) == 1
        assert len(result[0].supporting_sources) == 2


class TestSupportingSources:
    """supporting_sources 保留多个来源。"""

    @pytest.mark.asyncio
    async def test_three_sources_all_preserved(self):
        """三个来源确认同一事实，全部保留在 supporting_sources。"""
        claims = [
            _unit("事实A", normalized_claim="事实a",
                  source_id="src-1", document_id="doc-1", source_title="S1"),
            _unit("事实A变体", normalized_claim="事实a",
                  source_id="src-2", document_id="doc-2", source_title="S2"),
            _unit("事实A另一种说法", normalized_claim="事实a",
                  source_id="src-3", document_id="doc-3", source_title="S3"),
        ]
        analyses = [
            _analysis([claims[0]], source_id="src-1", document_id="doc-1"),
            _analysis([claims[1]], source_id="src-2", document_id="doc-2"),
            _analysis([claims[2]], source_id="src-3", document_id="doc-3"),
        ]

        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=analyses)

        assert len(result) == 1
        assert len(result[0].supporting_sources) == 3
        source_ids = {s["source_id"] for s in result[0].supporting_sources}
        assert source_ids == {"src-1", "src-2", "src-3"}

    @pytest.mark.asyncio
    async def test_three_sources_boost_confidence_to_high(self):
        """三个独立来源确认 → confidence=high。"""
        claims = [
            _unit("X", normalized_claim="x", source_id=f"src-{i}", document_id=f"doc-{i}")
            for i in range(3)
        ]
        analyses = [_analysis([c], source_id=c.source_id, document_id=c.document_id) for c in claims]

        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=analyses)

        assert len(result) == 1
        assert result[0].confidence == ClaimConfidence.HIGH


class TestDifferentClaimsNotMerged:
    """不同 claim 不合并。"""

    @pytest.mark.asyncio
    async def test_different_claims_stay_separate(self):
        """不同含义的 claims 保持独立。"""
        a1 = _analysis([
            _unit("公司于 2019 年成立", normalized_claim="公司2019年成立",
                  source_id="src-1", document_id="doc-1"),
            _unit("创始人毕业于清华", normalized_claim="创始人毕业于清华",
                  source_id="src-1", document_id="doc-1"),
        ])

        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=[a1])

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_similar_but_different_not_merged(self):
        """相似但不同的事实不合并。"""
        a1 = _analysis([
            _unit("收入 10 亿", normalized_claim="年收入10亿",
                  source_id="src-1", document_id="doc-1"),
            _unit("利润 2 亿", normalized_claim="年利润2亿",
                  source_id="src-1", document_id="doc-1"),
        ])

        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=[a1])

        assert len(result) == 2


class TestNoSupportingSourcesDiscarded:
    """没有 supporting_sources 的 group 被丢弃。"""

    @pytest.mark.asyncio
    async def test_empty_source_id_discarded(self):
        """source_id 为空的 claim 生成的 group 没有 supporting_sources → 被丢弃。"""
        a1 = _analysis([
            _unit("有来源的事实", source_id="src-1", document_id="doc-1"),
            _unit("没来源的事实", source_id="", document_id="doc-2"),
        ])

        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=[a1])

        # 没有 source_id 的 claim 的 supporting_sources 为空 → 被丢弃
        for group in result:
            assert len(group.supporting_sources) > 0


class TestLLMSuccess:
    """LLM 成功时使用 LLM groups。"""

    @pytest.mark.asyncio
    async def test_llm_groups_used_when_available(self):
        """LLM 返回分组时使用 LLM 结果。"""
        claims_a = [
            _unit("事实1来源A", normalized_claim="事实1", source_id="src-1", document_id="doc-1"),
            _unit("事实2来源A", normalized_claim="事实2", source_id="src-1", document_id="doc-1"),
        ]
        claims_b = [
            _unit("事实1来源B", normalized_claim="事实1b", source_id="src-2", document_id="doc-2"),
        ]

        analyses = [
            _analysis(claims_a, source_id="src-1", document_id="doc-1"),
            _analysis(claims_b, source_id="src-2", document_id="doc-2"),
        ]

        # LLM 说 index 0 和 2 是同一事实
        llm_output = CrossSourceDeduplicationOutput(
            groups=[
                DeduplicationGroupLLMItem(
                    canonical_claim="事实1标准表述",
                    claim_indices=[0, 2],
                    confidence_boost=True,
                    merged_claim="事实1的合并表述",
                ),
            ],
            conflicts=[],
        )

        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=llm_output)

        service = CrossSourceDeduplicationService(ai_gateway=gateway)
        result = await service.deduplicate(task_id="t1", analyses=analyses)

        # LLM 被调用
        gateway.run_json.assert_called_once()

        # 应该有 2 个 group：LLM 合并的 + 未分组的
        merged_group = next((g for g in result if g.merged_claim == "事实1的合并表述"), None)
        assert merged_group is not None
        assert len(merged_group.supporting_sources) == 2


class TestLLMFailureFallback:
    """LLM 失败时 fallback 到规则 groups。"""

    @pytest.mark.asyncio
    async def test_llm_failure_uses_rule_groups(self):
        """LLM 抛异常时 fallback 到规则去重。"""
        a1 = _analysis([
            _unit("事实X", normalized_claim="事实x", source_id="src-1", document_id="doc-1"),
        ])
        a2 = _analysis([
            _unit("事实X变体", normalized_claim="事实x", source_id="src-2", document_id="doc-2"),
        ], source_id="src-2", document_id="doc-2")

        gateway = AsyncMock()
        gateway.run_json = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        service = CrossSourceDeduplicationService(ai_gateway=gateway)
        result = await service.deduplicate(task_id="t1", analyses=[a1, a2])

        # 不抛异常
        assert isinstance(result, list)
        # 规则去重应该合并相同 normalized_claim
        assert len(result) == 1
        assert len(result[0].supporting_sources) == 2

    @pytest.mark.asyncio
    async def test_no_gateway_uses_rule_groups(self):
        """ai_gateway=None 时使用规则去重。"""
        a1 = _analysis([
            _unit("事实Y", normalized_claim="事实y", source_id="src-1", document_id="doc-1"),
        ])

        service = CrossSourceDeduplicationService(ai_gateway=None)
        result = await service.deduplicate(task_id="t1", analyses=[a1])

        assert len(result) == 1


class TestDuplicateRemovedCount:
    """duplicate_removed_count 正确。"""

    @pytest.mark.asyncio
    async def test_removed_count_in_trace(self):
        """trace 中 duplicate_removed_count = before - after。"""
        # 3 个 claims，其中 2 个相同 → 合并为 1 → removed = 3 - 2 = 1
        a1 = _analysis([
            _unit("事实A", normalized_claim="事实a", source_id="src-1", document_id="doc-1"),
            _unit("事实B", normalized_claim="事实b", source_id="src-1", document_id="doc-1"),
        ])
        a2 = _analysis([
            _unit("事实A重复", normalized_claim="事实a", source_id="src-2", document_id="doc-2"),
        ], source_id="src-2", document_id="doc-2")

        recorder = TraceRecorder()
        service = CrossSourceDeduplicationService(trace_recorder=recorder)
        result = await service.deduplicate(task_id="t1", analyses=[a1, a2])

        # 结果：2 个 group（事实a 合并 + 事实b 独立）
        assert len(result) == 2

        # 检查 trace
        events = recorder.get_events("t1")
        finished = [e for e in events if e.step == "cross_source_deduplication_finished"]
        assert len(finished) == 1
        metrics = finished[0].metrics
        assert metrics["before_claim_count"] == 3
        assert metrics["after_group_count"] == 2
        assert metrics["duplicate_removed_count"] == 1  # 3 - 2 = 1


class TestTraceNoContent:
    """trace 不包含完整正文。"""

    @pytest.mark.asyncio
    async def test_trace_metrics_only(self):
        """trace 只记录 metrics，不记录 claim 正文。"""
        a1 = _analysis([
            _unit("这是一段很长的正文内容" * 10, normalized_claim="长正文",
                  source_id="src-1", document_id="doc-1",
                  evidence_text="这是原文证据" * 5),
        ])

        recorder = TraceRecorder()
        service = CrossSourceDeduplicationService(trace_recorder=recorder)
        await service.deduplicate(task_id="t1", analyses=[a1])

        events = recorder.get_events("t1")
        for event in events:
            # 不应包含完整正文
            all_text = str(event.input_summary) + str(event.output_summary) + str(event.metrics)
            assert "这是一段很长的正文内容" not in all_text
            assert "这是原文证据" not in all_text

    @pytest.mark.asyncio
    async def test_trace_has_expected_steps(self):
        """trace 包含 started 和 finished 步骤。"""
        a1 = _analysis([
            _unit("X", source_id="src-1", document_id="doc-1"),
        ])

        recorder = TraceRecorder()
        service = CrossSourceDeduplicationService(trace_recorder=recorder)
        await service.deduplicate(task_id="t1", analyses=[a1])

        events = recorder.get_events("t1")
        steps = [e.step for e in events]
        assert "cross_source_deduplication_started" in steps
        assert "cross_source_deduplication_finished" in steps

    @pytest.mark.asyncio
    async def test_trace_records_used_llm_flag(self):
        """trace metrics 包含 used_llm 标志。"""
        a1 = _analysis([
            _unit("X", source_id="src-1", document_id="doc-1"),
        ])

        recorder = TraceRecorder()
        service = CrossSourceDeduplicationService(trace_recorder=recorder)
        await service.deduplicate(task_id="t1", analyses=[a1])

        events = recorder.get_events("t1")
        finished = [e for e in events if e.step == "cross_source_deduplication_finished"]
        assert finished[0].metrics["used_llm"] is False


class TestEmptyInput:
    """空输入处理。"""

    @pytest.mark.asyncio
    async def test_empty_analyses_returns_empty(self):
        """空 analyses 列表返回空结果。"""
        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=[])
        assert result == []

    @pytest.mark.asyncio
    async def test_analyses_with_no_claims_returns_empty(self):
        """analyses 中没有 claims 返回空结果。"""
        a1 = NormalizedDocumentAnalysis(
            document_id="doc-1", source_id="src-1", source_title="T"
        )
        service = CrossSourceDeduplicationService()
        result = await service.deduplicate(task_id="t1", analyses=[a1])
        assert result == []
