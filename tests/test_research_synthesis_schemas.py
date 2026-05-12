"""测试内容归一化与研究合成相关 schema。"""

import pytest
from pydantic import ValidationError

from models.enums import ClaimConfidence, NormalizedClaimType, SynthesisSectionType
from models.schemas import (
    DeduplicatedClaimGroup,
    NormalizedContentUnit,
    NormalizedDocumentAnalysis,
    SynthesizedResearchDocument,
)


class TestNormalizedDocumentAnalysis:
    """NormalizedDocumentAnalysis 默认 list 正确。"""

    def test_default_lists_are_empty(self):
        """所有 list 字段默认为空列表。"""
        doc = NormalizedDocumentAnalysis(
            document_id="doc-1",
            source_id="src-1",
            source_title="Test Source",
        )
        assert doc.main_claims == []
        assert doc.timeline_events == []
        assert doc.story_points == []
        assert doc.key_people == []
        assert doc.key_places == []
        assert doc.key_concepts == []
        assert doc.quotes == []
        assert doc.verification_needed == []

    def test_default_lists_are_independent(self):
        """不同实例的 list 字段互不影响。"""
        doc1 = NormalizedDocumentAnalysis(
            document_id="doc-1", source_id="src-1", source_title="A"
        )
        doc2 = NormalizedDocumentAnalysis(
            document_id="doc-2", source_id="src-2", source_title="B"
        )
        doc1.key_people.append("Alice")
        assert doc2.key_people == []

    def test_with_content_units(self):
        """可以正常填充 NormalizedContentUnit 列表。"""
        unit = NormalizedContentUnit(
            document_id="doc-1",
            source_id="src-1",
            source_title="Test",
            claim="Tim Cook 于 2011 年接任 Apple CEO",
            normalized_claim="Tim Cook became Apple CEO in 2011",
            claim_type=NormalizedClaimType.FACT,
            confidence=ClaimConfidence.HIGH,
            importance=4,
            people=["Tim Cook"],
            organizations=["Apple"],
            dates=["2011"],
        )
        doc = NormalizedDocumentAnalysis(
            document_id="doc-1",
            source_id="src-1",
            source_title="Test",
            main_claims=[unit],
        )
        assert len(doc.main_claims) == 1
        assert doc.main_claims[0].claim_type == NormalizedClaimType.FACT


class TestDeduplicatedClaimGroup:
    """DeduplicatedClaimGroup 支持多个 supporting_sources。"""

    def test_multiple_supporting_sources(self):
        """可以有多个 supporting_sources。"""
        group = DeduplicatedClaimGroup(
            normalized_claim="Apple was founded in 1976",
            merged_claim="Apple 于 1976 年由 Steve Jobs 等人创立",
            supporting_sources=[
                {"source_id": "src-1", "url": "https://a.com", "title": "Source A"},
                {"source_id": "src-2", "url": "https://b.com", "title": "Source B"},
                {"source_id": "src-3", "url": "https://c.com", "title": "Source C"},
            ],
            confidence=ClaimConfidence.HIGH,
            importance=5,
        )
        assert len(group.supporting_sources) == 3
        assert group.confidence == ClaimConfidence.HIGH

    def test_with_conflicting_sources(self):
        """可以同时有 supporting 和 conflicting sources。"""
        group = DeduplicatedClaimGroup(
            normalized_claim="Revenue figure",
            merged_claim="公司年收入约 100 亿",
            supporting_sources=[
                {"source_id": "src-1", "title": "Annual Report"},
            ],
            conflicting_sources=[
                {"source_id": "src-2", "title": "News Article", "claim": "年收入 80 亿"},
            ],
            confidence=ClaimConfidence.CONFLICTING,
            needs_verification=True,
        )
        assert len(group.conflicting_sources) == 1
        assert group.needs_verification is True

    def test_confirmed_fact_must_have_sources(self):
        """confidence=high 时必须有 supporting_sources，否则报错。"""
        with pytest.raises(ValidationError) as exc_info:
            DeduplicatedClaimGroup(
                normalized_claim="Some fact",
                merged_claim="某个事实",
                supporting_sources=[],  # 空！
                confidence=ClaimConfidence.HIGH,
            )
        assert "confirmed fact" in str(exc_info.value).lower() or "supporting_source" in str(
            exc_info.value
        ).lower()

    def test_non_high_confidence_allows_empty_sources(self):
        """非 high confidence 允许空 supporting_sources。"""
        group = DeduplicatedClaimGroup(
            normalized_claim="Unverified claim",
            merged_claim="未验证的说法",
            supporting_sources=[],
            confidence=ClaimConfidence.UNVERIFIED,
        )
        assert group.supporting_sources == []


class TestSynthesizedResearchDocument:
    """SynthesizedResearchDocument 可以正常构造。"""

    def test_basic_construction(self):
        """基本构造正常。"""
        doc = SynthesizedResearchDocument(
            task_id="task-123",
            topic="Apple Inc. 发展史",
        )
        assert doc.task_id == "task-123"
        assert doc.topic == "Apple Inc. 发展史"
        assert doc.confirmed_facts == []
        assert doc.timeline == []
        assert doc.key_people == []
        assert doc.key_places == []
        assert doc.key_concepts == []
        assert doc.story_points == []
        assert doc.controversies == []
        assert doc.verification_needed == []
        assert doc.source_map == []
        assert doc.suggested_next_steps == []
        assert doc.generated_at != ""

    def test_full_construction(self):
        """完整构造包含所有字段。"""
        claim = DeduplicatedClaimGroup(
            normalized_claim="Apple founded 1976",
            merged_claim="Apple 于 1976 年创立",
            supporting_sources=[{"source_id": "s1", "title": "Wiki"}],
            confidence=ClaimConfidence.HIGH,
            importance=5,
        )
        doc = SynthesizedResearchDocument(
            task_id="task-456",
            topic="Apple Inc.",
            canonical_topic="Apple Inc.",
            overview="Apple 是全球最大的科技公司之一。",
            executive_summary="本研究梳理了 Apple 的发展历程。",
            confirmed_facts=[claim],
            timeline=[claim],
            key_people=[{"name": "Steve Jobs", "role": "Co-founder"}],
            key_places=[{"name": "Cupertino", "significance": "总部所在地"}],
            key_concepts=[{"name": "iPhone", "description": "核心产品"}],
            source_map=[{"source_id": "s1", "url": "https://wiki.org", "title": "Wiki"}],
            suggested_next_steps=["深入研究 iPhone 产品线"],
        )
        assert len(doc.confirmed_facts) == 1
        assert doc.key_people[0]["name"] == "Steve Jobs"


class TestClaimConfidenceEnum:
    """illegal confidence 报错。"""

    def test_valid_confidence_values(self):
        """合法枚举值正常。"""
        for val in ("high", "medium", "low", "unverified", "conflicting"):
            unit = NormalizedContentUnit(
                document_id="d1",
                source_id="s1",
                source_title="T",
                claim="test",
                normalized_claim="test",
                confidence=ClaimConfidence(val),
            )
            assert unit.confidence == val

    def test_invalid_confidence_raises(self):
        """非法 confidence 值报错。"""
        with pytest.raises((ValidationError, ValueError)):
            NormalizedContentUnit(
                document_id="d1",
                source_id="s1",
                source_title="T",
                claim="test",
                normalized_claim="test",
                confidence="definitely_true",  # type: ignore
            )


class TestImportanceRange:
    """importance 超出范围报错。"""

    def test_valid_importance(self):
        """1-5 范围内正常。"""
        for val in (1, 2, 3, 4, 5):
            unit = NormalizedContentUnit(
                document_id="d1",
                source_id="s1",
                source_title="T",
                claim="test",
                normalized_claim="test",
                importance=val,
            )
            assert unit.importance == val

    def test_importance_too_low(self):
        """importance < 1 报错。"""
        with pytest.raises(ValidationError):
            NormalizedContentUnit(
                document_id="d1",
                source_id="s1",
                source_title="T",
                claim="test",
                normalized_claim="test",
                importance=0,
            )

    def test_importance_too_high(self):
        """importance > 5 报错。"""
        with pytest.raises(ValidationError):
            NormalizedContentUnit(
                document_id="d1",
                source_id="s1",
                source_title="T",
                claim="test",
                normalized_claim="test",
                importance=6,
            )

    def test_importance_range_on_deduplicated_group(self):
        """DeduplicatedClaimGroup 的 importance 也限制 1-5。"""
        with pytest.raises(ValidationError):
            DeduplicatedClaimGroup(
                normalized_claim="test",
                merged_claim="test",
                importance=10,
            )


class TestNormalizedClaimTypeEnum:
    """NormalizedClaimType 枚举值正确。"""

    def test_all_values(self):
        expected = {
            "fact", "background", "timeline_event", "quote",
            "story_point", "controversy", "interpretation", "unknown",
        }
        actual = {e.value for e in NormalizedClaimType}
        assert actual == expected


class TestSynthesisSectionTypeEnum:
    """SynthesisSectionType 枚举值正确。"""

    def test_all_values(self):
        expected = {
            "overview", "confirmed_facts", "timeline", "key_people",
            "key_places", "key_concepts", "story_points", "books_and_sources",
            "controversies", "verification_needed", "source_notes",
        }
        actual = {e.value for e in SynthesisSectionType}
        assert actual == expected
