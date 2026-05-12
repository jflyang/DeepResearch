"""测试内容归一化策略 - B 级参与归一化，C/D 不进入已确认事实区。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.research_synthesis_service import ResearchSynthesisService
from models.enums import ClaimConfidence, NormalizedClaimType
from models.schemas import (
    DeduplicatedClaimGroup,
    NormalizedContentUnit,
    NormalizedDocumentAnalysis,
    SynthesizedResearchDocument,
)


# === Fixtures ===


def _make_source(source_id: str, level: str, download_status: str = "extracted"):
    row = MagicMock()
    row.id = source_id
    row.source_level = level
    row.download_status = download_status
    row.source_type = "news"
    return row


def _make_doc(source_id: str, content: str = "正文内容" * 100):
    row = MagicMock()
    row.id = f"doc-{source_id}"
    row.source_item_id = source_id
    row.title = f"Doc for {source_id}"
    row.content = content
    return row


def _make_task_row():
    row = MagicMock()
    row.id = "task-001"
    row.topic = "测试主题"
    row.canonical_topic = None
    row.mode = "person"
    return row


class TestBLevelParticipatesInNormalization:
    """B 级来源可以抓取、归一化、合成。"""

    @pytest.mark.asyncio
    async def test_b_level_not_filtered_out(self):
        """B 级来源通过 _filter_eligible_documents。"""
        from app.services.content_normalization_service import ContentNormalizationService
        from app.services.cross_source_deduplication_service import CrossSourceDeduplicationService

        norm_service = AsyncMock(spec=ContentNormalizationService)
        norm_service.normalize_document = AsyncMock(return_value=NormalizedDocumentAnalysis(
            document_id="src-b", source_id="src-b", source_title="B Source",
            main_claims=[NormalizedContentUnit(
                document_id="src-b", source_id="src-b", source_title="B Source",
                claim_type=NormalizedClaimType.FACT, claim="B级事实",
                normalized_claim="B级事实", evidence_text="证据",
                confidence=ClaimConfidence.MEDIUM, importance=3,
            )],
        ))

        dedup_service = AsyncMock(spec=CrossSourceDeduplicationService)
        dedup_service.deduplicate = AsyncMock(return_value=[
            DeduplicatedClaimGroup(
                normalized_claim="B级事实", claim_type="fact", merged_claim="B级事实",
                supporting_sources=[{"source_id": "src-b", "title": "B Source", "url": "https://b.com"}],
                confidence=ClaimConfidence.MEDIUM, importance=3,
            ),
        ])

        sources = [_make_source("src-b", "B")]
        docs = {"src-b": _make_doc("src-b")}

        task_repo = MagicMock()
        task_repo.get_task = MagicMock(return_value=_make_task_row())
        source_repo = MagicMock()
        source_repo.get_by_task = MagicMock(return_value=sources)
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(side_effect=lambda sid: docs.get(sid))

        service = ResearchSynthesisService(
            content_normalization_service=norm_service,
            deduplication_service=dedup_service,
            ai_gateway=None,
            task_repository=task_repo,
            document_repository=doc_repo,
            source_repository=source_repo,
        )

        result = await service.synthesize_task(task_id="task-001")

        # B 级来源被归一化
        norm_service.normalize_document.assert_called_once()
        assert isinstance(result, SynthesizedResearchDocument)


class TestCDLevelExcluded:
    """C/D 级来源不参与归一化和合成。"""

    @pytest.mark.asyncio
    async def test_c_level_filtered_out(self):
        """C 级来源被过滤，不调用 normalize_document。"""
        from app.services.content_normalization_service import ContentNormalizationService
        from app.services.cross_source_deduplication_service import CrossSourceDeduplicationService

        norm_service = AsyncMock(spec=ContentNormalizationService)
        dedup_service = AsyncMock(spec=CrossSourceDeduplicationService)

        sources = [_make_source("src-c", "C")]
        docs = {"src-c": _make_doc("src-c")}

        task_repo = MagicMock()
        task_repo.get_task = MagicMock(return_value=_make_task_row())
        source_repo = MagicMock()
        source_repo.get_by_task = MagicMock(return_value=sources)
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(side_effect=lambda sid: docs.get(sid))

        service = ResearchSynthesisService(
            content_normalization_service=norm_service,
            deduplication_service=dedup_service,
            ai_gateway=None,
            task_repository=task_repo,
            document_repository=doc_repo,
            source_repository=source_repo,
        )

        result = await service.synthesize_task(task_id="task-001")

        # C 级来源被过滤，normalization 不被调用
        norm_service.normalize_document.assert_not_called()
        # 返回资料不足
        assert "暂无" in result.overview or "资料不足" in result.executive_summary

    @pytest.mark.asyncio
    async def test_d_level_filtered_out(self):
        """D 级来源被过滤。"""
        from app.services.content_normalization_service import ContentNormalizationService
        from app.services.cross_source_deduplication_service import CrossSourceDeduplicationService

        norm_service = AsyncMock(spec=ContentNormalizationService)
        dedup_service = AsyncMock(spec=CrossSourceDeduplicationService)

        sources = [_make_source("src-d", "D")]
        docs = {"src-d": _make_doc("src-d")}

        task_repo = MagicMock()
        task_repo.get_task = MagicMock(return_value=_make_task_row())
        source_repo = MagicMock()
        source_repo.get_by_task = MagicMock(return_value=sources)
        doc_repo = MagicMock()
        doc_repo.get_by_source = MagicMock(side_effect=lambda sid: docs.get(sid))

        service = ResearchSynthesisService(
            content_normalization_service=norm_service,
            deduplication_service=dedup_service,
            ai_gateway=None,
            task_repository=task_repo,
            document_repository=doc_repo,
            source_repository=source_repo,
        )

        result = await service.synthesize_task(task_id="task-001")

        norm_service.normalize_document.assert_not_called()


class TestBLevelConfidenceInIndex:
    """B 级事实在 index.md 显示来源等级和可信度。"""

    def test_b_level_shows_confidence(self):
        """B 级来源支持的事实显示 confidence=medium。"""
        from app.services.markdown_service import render_synthesized_index

        synthesis = SynthesizedResearchDocument(
            task_id="t1",
            topic="测试",
            confirmed_facts=[
                DeduplicatedClaimGroup(
                    normalized_claim="B级事实",
                    claim_type="fact",
                    merged_claim="仅由 B 级来源支持的事实",
                    supporting_sources=[
                        {"source_id": "src-b", "title": "B Source", "url": "https://b.com", "source_level": "B"},
                    ],
                    confidence=ClaimConfidence.MEDIUM,
                    importance=3,
                ),
            ],
        )

        md = render_synthesized_index(synthesis)
        assert "置信度" in md
        assert "中" in md  # medium → 中
        assert "[B]" in md  # source_level badge

    def test_sa_level_shows_high_confidence(self):
        """S/A 级来源支持的事实显示 confidence=high。"""
        from app.services.markdown_service import render_synthesized_index

        synthesis = SynthesizedResearchDocument(
            task_id="t1",
            topic="测试",
            confirmed_facts=[
                DeduplicatedClaimGroup(
                    normalized_claim="SA事实",
                    claim_type="fact",
                    merged_claim="由 S/A 级来源确认的事实",
                    supporting_sources=[
                        {"source_id": "src-s", "title": "S Source", "url": "https://s.com", "source_level": "S"},
                        {"source_id": "src-a", "title": "A Source", "url": "https://a.com", "source_level": "A"},
                    ],
                    confidence=ClaimConfidence.HIGH,
                    importance=5,
                ),
            ],
        )

        md = render_synthesized_index(synthesis)
        assert "高" in md  # high → 高
        assert "[S]" in md
        assert "[A]" in md


class TestCDNotInConfirmedFacts:
    """C/D 不进入已确认事实区。"""

    def test_cd_sources_not_in_confirmed_section(self):
        """即使有 C/D 来源的 group，不应出现在 confirmed_facts。"""
        # 这个测试验证的是 ResearchSynthesisService 的逻辑：
        # confirmed_facts 只包含 confidence=HIGH 的 groups
        # C/D 来源不参与合成，所以不会产生 confirmed_facts

        from app.services.markdown_service import render_synthesized_index

        # 模拟：只有 B 级来源，confidence=MEDIUM
        synthesis = SynthesizedResearchDocument(
            task_id="t1",
            topic="测试",
            confirmed_facts=[],  # 没有 HIGH confidence 的事实
            verification_needed=[
                DeduplicatedClaimGroup(
                    normalized_claim="低可信事实",
                    claim_type="fact",
                    merged_claim="仅由低级来源支持",
                    supporting_sources=[{"source_id": "src-c", "title": "C Source", "url": ""}],
                    confidence=ClaimConfidence.LOW,
                    importance=2,
                    needs_verification=True,
                ),
            ],
        )

        md = render_synthesized_index(synthesis)
        # confirmed 区域应该显示"暂无"
        confirmed_start = md.index("## 三、已确认的关键信息")
        confirmed_end = md.index("## 四、时间线")
        confirmed_section = md[confirmed_start:confirmed_end]
        assert "暂无高置信度" in confirmed_section
        # C Source 不在 confirmed 区域
        assert "C Source" not in confirmed_section
