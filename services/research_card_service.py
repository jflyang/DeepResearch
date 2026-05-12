"""研究卡片服务 - 从 ExtractedDocument 生成基础研究卡片。

MVP 使用规则生成，保留接口未来替换为 LLM 版本。
"""

import logging
import re
from pathlib import Path

from models.enums import CardType, Confidence, SourceLevel
from models.schemas import ExtractedDocument, ResearchCard, SourceItem
from utils.filesystem import ensure_dir, ensure_unique_path, sanitize_filename, write_file

logger = logging.getLogger(__name__)

# === 故事线索关键词 ===

_STORY_KEYWORDS = [
    "childhood",
    "early life",
    "grew up",
    "founding",
    "founded",
    "co-founded",
    "controversy",
    "lawsuit",
    "failure",
    "bankrupt",
    "crisis",
    "turning point",
    "breakthrough",
    "fired",
    "resigned",
    "arrested",
    "investigation",
    "scandal",
    "secret",
    "revealed",
]

# === 八卦关键词 ===

_GOSSIP_KEYWORDS = [
    "rumor",
    "personal life",
    "controversy",
    "affair",
    "divorce",
    "dating",
    "relationship",
    "scandal",
    "net worth",
    "salary",
    "cheating",
    "alleged",
]


# === 卡片生成器 ===


def _extract_paragraphs(content: str) -> list[str]:
    """将正文拆分为段落。"""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in content.split("\n") if p.strip() and len(p.strip()) > 30]
    return paragraphs


def _determine_confidence(source_level: SourceLevel, gossip_score: float) -> Confidence:
    """根据来源等级和八卦分确定可信度。"""
    if source_level == SourceLevel.S:
        return Confidence.CONFIRMED
    if source_level == SourceLevel.A:
        return Confidence.LIKELY
    if gossip_score >= 0.3:
        return Confidence.RUMOR
    if source_level == SourceLevel.C:
        return Confidence.UNVERIFIED
    return Confidence.LIKELY


def generate_person_cards(
    extracted: ExtractedDocument,
    source_item: SourceItem,
    task_id: str,
) -> list[ResearchCard]:
    """从 people 字段生成人物卡片。"""
    cards: list[ResearchCard] = []

    for person in extracted.people:
        if not person.strip():
            continue
        cards.append(ResearchCard(
            task_id=task_id,
            type=CardType.FACT,
            title=person,
            content=f"人物「{person}」出现在来源《{extracted.title}》中。",
            linked_sources=[source_item.url],
            confidence=_determine_confidence(source_item.source_level, source_item.gossip_score),
        ))

    if cards:
        logger.info("person_cards_generated count=%d source_id=%s", len(cards), source_item.id)
    return cards


def generate_concept_cards(
    extracted: ExtractedDocument,
    source_item: SourceItem,
    task_id: str,
) -> list[ResearchCard]:
    """从 concepts、organizations、places 生成重点名词卡片。"""
    cards: list[ResearchCard] = []
    all_terms: list[tuple[str, str]] = []

    for concept in extracted.concepts:
        all_terms.append((concept, "概念"))
    for org in extracted.organizations:
        all_terms.append((org, "组织"))
    for place in extracted.places:
        all_terms.append((place, "地点"))

    for term, term_type in all_terms:
        if not term.strip():
            continue
        cards.append(ResearchCard(
            task_id=task_id,
            type=CardType.FACT,
            title=term,
            content=f"{term_type}「{term}」出现在来源《{extracted.title}》中。",
            linked_sources=[source_item.url],
            confidence=_determine_confidence(source_item.source_level, source_item.gossip_score),
        ))

    if cards:
        logger.info("concept_cards_generated count=%d source_id=%s", len(cards), source_item.id)
    return cards


def generate_story_cards(
    extracted: ExtractedDocument,
    source_item: SourceItem,
    task_id: str,
) -> list[ResearchCard]:
    """从正文中提取包含故事线索关键词的段落生成卡片。"""
    cards: list[ResearchCard] = []
    paragraphs = _extract_paragraphs(extracted.content)

    for para in paragraphs:
        para_lower = para.lower()
        matched_keywords = [kw for kw in _STORY_KEYWORDS if kw in para_lower]
        if not matched_keywords:
            continue

        # 用第一个匹配的关键词作为标题标签
        label = matched_keywords[0].replace("_", " ").title()
        title = f"故事线索: {label}"

        # 截取段落前 300 字符
        snippet = para[:300] + ("..." if len(para) > 300 else "")

        cards.append(ResearchCard(
            task_id=task_id,
            type=CardType.TIMELINE,
            title=title,
            content=snippet,
            linked_sources=[source_item.url],
            confidence=_determine_confidence(source_item.source_level, source_item.gossip_score),
        ))

    if cards:
        logger.info("story_cards_generated count=%d source_id=%s", len(cards), source_item.id)
    return cards


def generate_gossip_cards(
    extracted: ExtractedDocument,
    source_item: SourceItem,
    task_id: str,
) -> list[ResearchCard]:
    """从八卦来源或包含八卦关键词的段落生成卡片。"""
    cards: list[ResearchCard] = []

    # 条件：C 级 + 高 gossip_score，或正文包含八卦关键词
    is_gossip_source = (
        source_item.source_level == SourceLevel.C and source_item.gossip_score >= 0.3
    )

    paragraphs = _extract_paragraphs(extracted.content)

    for para in paragraphs:
        para_lower = para.lower()
        matched = [kw for kw in _GOSSIP_KEYWORDS if kw in para_lower]

        if not matched and not is_gossip_source:
            continue
        if not matched:
            continue

        label = matched[0].replace("_", " ").title()
        title = f"八卦线索: {label}"
        snippet = para[:300] + ("..." if len(para) > 300 else "")

        cards.append(ResearchCard(
            task_id=task_id,
            type=CardType.CONTROVERSY,
            title=title,
            content=snippet,
            linked_sources=[source_item.url],
            confidence=Confidence.RUMOR,
        ))

    if cards:
        logger.info("gossip_cards_generated count=%d source_id=%s", len(cards), source_item.id)
    return cards


# === 聚合入口 ===


def generate_cards(
    extracted: ExtractedDocument,
    source_item: SourceItem,
    task_id: str,
) -> list[ResearchCard]:
    """
    从单个 ExtractedDocument 生成所有类型的研究卡片。

    Returns:
        生成的 ResearchCard 列表
    """
    all_cards: list[ResearchCard] = []

    all_cards.extend(generate_person_cards(extracted, source_item, task_id))
    all_cards.extend(generate_concept_cards(extracted, source_item, task_id))
    all_cards.extend(generate_story_cards(extracted, source_item, task_id))
    all_cards.extend(generate_gossip_cards(extracted, source_item, task_id))

    logger.info(
        "cards_generated_total count=%d source_id=%s task_id=%s",
        len(all_cards),
        source_item.id,
        task_id,
    )
    return all_cards


# === 卡片导出 ===


def export_card_markdown(card: ResearchCard, cards_dir: Path) -> Path:
    """将单张卡片导出为 Markdown 文件。"""
    filename = sanitize_filename(card.title, max_length=80) + ".md"
    file_path = ensure_unique_path(cards_dir / filename)

    lines = [
        "---",
        f'title: "{card.title}"',
        f'type: "{card.type.value}"',
        f'confidence: "{card.confidence.value}"',
        f'task_id: "{card.task_id}"',
        f"linked_sources: {card.linked_sources}",
        "tags:",
        "  - research-card",
        f"  - {card.type.value}",
        "---",
        "",
        f"# {card.title}",
        "",
        f"**可信度**: {card.confidence.value}",
        "",
        card.content,
        "",
        "## 来源",
        "",
    ]

    for src in card.linked_sources:
        lines.append(f"- [{src}]({src})")

    content = "\n".join(lines) + "\n"
    write_file(file_path, content)

    card.markdown_path = str(file_path)
    return file_path
