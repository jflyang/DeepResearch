"""LLM 增强研究卡片服务测试。"""

from unittest.mock import AsyncMock

import pytest

from app.ai.errors import LLMFallbackRequired
from app.ai.schemas import DocumentAnalysisOutput
from app.services.research_card_service import ResearchCardService
from models.enums import (
    CardType,
    Confidence,
    DownloadStatus,
    SourceLevel,
    SourceType,
)
from models.schemas import ExtractedDocument, ResearchCard, SourceItem


@pytest.fixture
def source_item() -> SourceItem:
    return SourceItem(
        task_id="task-1",
        title="量子计算综述",
        url="https://arxiv.org/abs/2301.00001",
        domain="arxiv.org",
        source_type=SourceType.ACADEMIC,
        source_level=SourceLevel.A,
        relevance_score=0.9,
        authority_score=0.9,
        originality_score=0.9,
        gossip_score=0.0,
        reason_to_read="[A] Primary academic source",
        download_status=DownloadStatus.EXTRACTED,
    )


@pytest.fixture
def extracted_doc(source_item: SourceItem) -> ExtractedDocument:
    return ExtractedDocument(
        source_item_id=source_item.id,
        title="量子计算综述",
        content="量子计算是一种利用量子力学原理进行计算的技术。Richard Feynman 在1982年提出了量子计算的概念。",
        people=["Richard Feynman"],
        organizations=["IBM"],
        concepts=["量子比特"],
    )


@pytest.fixture
def mock_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_gateway: AsyncMock) -> ResearchCardService:
    return ResearchCardService(ai_gateway=mock_gateway)


@pytest.fixture
def service_no_llm() -> ResearchCardService:
    return ResearchCardService(ai_gateway=None)


# === LLM 成功生成卡片 ===


class TestLLMSuccess:
    @pytest.mark.asyncio
    async def test_generates_cards_from_llm(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="本文综述了量子计算的发展历程",
            key_points=["量子优越性已被实验验证", "纠错码是关键挑战"],
            people=["Richard Feynman", "Peter Shor"],
            story_points=["1982年Feynman提出量子计算概念"],
            gossip_or_unverified_claims=[],
        ))

        cards = await service.generate(extracted_doc, source_item, "task-1")

        assert len(cards) > 0
        assert all(isinstance(c, ResearchCard) for c in cards)

        # 有 summary 卡片
        summaries = [c for c in cards if c.type == CardType.SUMMARY]
        assert len(summaries) == 1
        assert "量子计算" in summaries[0].content

        # 有 fact 卡片
        facts = [c for c in cards if c.type == CardType.FACT]
        assert len(facts) > 0

    @pytest.mark.asyncio
    async def test_all_cards_have_source_url(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="摘要",
            key_points=["要点1"],
            people=["张三"],
        ))

        cards = await service.generate(extracted_doc, source_item, "task-1")
        for card in cards:
            assert source_item.url in card.linked_sources

    @pytest.mark.asyncio
    async def test_all_cards_have_task_id(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="摘要",
        ))

        cards = await service.generate(extracted_doc, source_item, "task-1")
        for card in cards:
            assert card.task_id == "task-1"


# === LLM 失败 fallback ===


class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_fallback_to_rules_on_exception(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=LLMFallbackRequired(
            task="research_card_generation", reason="parse failed"
        ))

        cards = await service.generate(extracted_doc, source_item, "task-1")
        # 规则版应该生成卡片（至少有 person/concept 卡片）
        assert len(cards) > 0
        assert all(isinstance(c, ResearchCard) for c in cards)

    @pytest.mark.asyncio
    async def test_fallback_on_runtime_error(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=RuntimeError("timeout"))

        cards = await service.generate(extracted_doc, source_item, "task-1")
        assert len(cards) > 0

    @pytest.mark.asyncio
    async def test_no_gateway_uses_rules(
        self, service_no_llm: ResearchCardService,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        cards = await service_no_llm.generate(extracted_doc, source_item, "task-1")
        assert len(cards) > 0
        # 规则版生成的 person 卡片
        titles = [c.title for c in cards]
        assert "Richard Feynman" in titles


# === Gossip confidence 正确 ===


class TestGossipConfidence:
    @pytest.mark.asyncio
    async def test_gossip_cards_not_confirmed(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="摘要",
            gossip_or_unverified_claims=["据传某人有不当行为", "未经证实的财务问题"],
        ))

        cards = await service.generate(extracted_doc, source_item, "task-1")
        gossip_cards = [c for c in cards if c.type == CardType.CONTROVERSY]
        assert len(gossip_cards) == 2
        for card in gossip_cards:
            assert card.confidence in (Confidence.RUMOR, Confidence.UNVERIFIED)
            assert card.confidence != Confidence.CONFIRMED

    @pytest.mark.asyncio
    async def test_gossip_keyword_in_content_not_confirmed(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        # 即使 source_level=S，包含八卦关键词的卡片也不能是 confirmed
        s_source = source_item.model_copy(update={"source_level": SourceLevel.S})
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="摘要",
            gossip_or_unverified_claims=["rumor about financial scandal"],
        ))

        cards = await service.generate(extracted_doc, s_source, "task-1")
        gossip_cards = [c for c in cards if c.type == CardType.CONTROVERSY]
        for card in gossip_cards:
            assert card.confidence != Confidence.CONFIRMED

    @pytest.mark.asyncio
    async def test_non_gossip_cards_can_be_confirmed(
        self, service: ResearchCardService, mock_gateway: AsyncMock,
        extracted_doc: ExtractedDocument, source_item: SourceItem,
    ) -> None:
        s_source = source_item.model_copy(update={"source_level": SourceLevel.S, "gossip_score": 0.0})
        mock_gateway.run_json = AsyncMock(return_value=DocumentAnalysisOutput(
            summary="严肃学术摘要",
            key_points=["经过验证的事实"],
        ))

        cards = await service.generate(extracted_doc, s_source, "task-1")
        non_gossip = [c for c in cards if c.type != CardType.CONTROVERSY]
        # S 级来源的非八卦卡片可以是 confirmed
        confirmed = [c for c in non_gossip if c.confidence == Confidence.CONFIRMED]
        assert len(confirmed) > 0
