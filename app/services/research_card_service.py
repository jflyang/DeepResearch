"""LLM 增强研究卡片服务 - 保留规则版 fallback。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from models.enums import CardType, Confidence
from models.schemas import ExtractedDocument, ResearchCard, SourceItem
from services.research_card_service import generate_cards as rule_generate_cards

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# 八卦卡片类型标识
_GOSSIP_CARD_TYPES = frozenset([CardType.CONTROVERSY])
_GOSSIP_KEYWORDS = frozenset([
    "rumor", "gossip", "scandal", "alleged", "unverified",
    "八卦", "传闻", "绯闻", "未证实",
])


class ResearchCardService:
    """研究卡片生成 - LLM 增强 + 规则 fallback。"""

    def __init__(self, ai_gateway: AIGateway | None = None) -> None:
        self._ai_gateway = ai_gateway

    async def generate(
        self,
        extracted: ExtractedDocument,
        source_item: SourceItem,
        task_id: str,
    ) -> list[ResearchCard]:
        """生成研究卡片。LLM 可用时增强，失败时 fallback 到规则版。"""
        # 尝试 LLM 生成
        llm_cards = await self._try_llm_generate(extracted, source_item, task_id)
        if llm_cards is not None:
            return llm_cards

        # fallback 到规则版
        return rule_generate_cards(extracted, source_item, task_id)

    async def _try_llm_generate(
        self,
        extracted: ExtractedDocument,
        source_item: SourceItem,
        task_id: str,
    ) -> list[ResearchCard] | None:
        """尝试 LLM 生成卡片，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        try:
            from app.ai.schemas import DocumentAnalysisOutput

            output: DocumentAnalysisOutput = await self._ai_gateway.run_json(
                task_name="research_card_generation",
                payload={
                    "topic": extracted.title,
                    "content": extracted.content[:8000],
                    "source_url": source_item.url,
                    "source_level": source_item.source_level.value,
                },
                output_schema=DocumentAnalysisOutput,
                language="zh",
            )
        except Exception as e:
            logger.warning(
                "llm_card_generation_failed source=%s error=%s",
                source_item.url, str(e),
            )
            return None

        # 转换 LLM 输出为 ResearchCard 列表
        cards = self._build_cards_from_output(output, source_item, task_id)
        return cards

    def _build_cards_from_output(
        self,
        output: Any,
        source_item: SourceItem,
        task_id: str,
    ) -> list[ResearchCard]:
        """从 LLM 输出构建 ResearchCard 列表。"""
        cards: list[ResearchCard] = []

        # summary 卡片
        if output.summary:
            cards.append(ResearchCard(
                task_id=task_id,
                type=CardType.SUMMARY,
                title=f"摘要: {source_item.title[:50]}",
                content=output.summary,
                linked_sources=[source_item.url],
                confidence=self._base_confidence(source_item),
            ))

        # key_points 卡片
        for point in output.key_points:
            cards.append(ResearchCard(
                task_id=task_id,
                type=CardType.FACT,
                title=point[:80],
                content=point,
                linked_sources=[source_item.url],
                confidence=self._base_confidence(source_item),
            ))

        # story_points 卡片
        for story in output.story_points:
            cards.append(ResearchCard(
                task_id=task_id,
                type=CardType.TIMELINE,
                title=f"故事线索: {story[:60]}",
                content=story,
                linked_sources=[source_item.url],
                confidence=self._base_confidence(source_item),
            ))

        # gossip 卡片 - 必须标记 rumor/unverified
        for claim in output.gossip_or_unverified_claims:
            cards.append(ResearchCard(
                task_id=task_id,
                type=CardType.CONTROVERSY,
                title=f"未证实: {claim[:60]}",
                content=claim,
                linked_sources=[source_item.url],
                confidence=Confidence.RUMOR,
            ))

        # 人物卡片
        for person in output.people:
            cards.append(ResearchCard(
                task_id=task_id,
                type=CardType.FACT,
                title=person,
                content=f"人物「{person}」出现在来源《{source_item.title}》中。",
                linked_sources=[source_item.url],
                confidence=self._base_confidence(source_item),
            ))

        # 确保所有卡片绑定 source URL
        for card in cards:
            if source_item.url not in card.linked_sources:
                card.linked_sources.append(source_item.url)

        # 强制八卦卡片 confidence
        self._enforce_gossip_confidence(cards)

        return cards

    def _base_confidence(self, source_item: SourceItem) -> Confidence:
        """根据来源等级确定基础 confidence。"""
        from models.enums import SourceLevel
        if source_item.source_level == SourceLevel.S:
            return Confidence.CONFIRMED
        if source_item.source_level == SourceLevel.A:
            return Confidence.LIKELY
        if source_item.gossip_score >= 0.3:
            return Confidence.RUMOR
        return Confidence.LIKELY

    def _enforce_gossip_confidence(self, cards: list[ResearchCard]) -> None:
        """确保八卦卡片不会被标记为 confirmed。"""
        for card in cards:
            if card.type in _GOSSIP_CARD_TYPES:
                if card.confidence == Confidence.CONFIRMED:
                    card.confidence = Confidence.UNVERIFIED
            # 标题/内容包含八卦关键词的也强制降级
            title_lower = card.title.lower()
            content_lower = card.content.lower()
            if any(kw in title_lower or kw in content_lower for kw in _GOSSIP_KEYWORDS):
                if card.confidence == Confidence.CONFIRMED:
                    card.confidence = Confidence.UNVERIFIED
