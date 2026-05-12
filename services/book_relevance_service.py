"""图书相关性过滤服务 - LLM + 规则兜底。

职责：判断图书搜索结果是否真的与研究主题相关，过滤因关键词歧义而错误匹配的图书。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


# === 输出模型 ===


class BookRelevanceResult(BaseModel):
    """图书相关性判断结果。"""

    is_relevant: bool = False
    relevance_level: str = "irrelevant"  # high / medium / low / irrelevant
    book_title_zh: str = ""
    book_type: str = "unknown"  # biography / business / self_help / technical / fiction / reference / cookbook / unknown
    why_relevant: str = ""
    likely_contains: list[str] = Field(default_factory=list)
    risk_warning: str | None = None


# === 规则兜底：明确排除的关键词 ===

_ALWAYS_EXCLUDE_KEYWORDS = [
    "cookbook", "cooking", "recipe", "gourmet", "chocolate",
    "jamie oliver", "julia child", "gordon ramsay",
    "julius caesar", "bible", "scripture", "gospel",
    "python programming", "natural language processing",
    "nlp", "machine learning", "javascript", "programming cookbook",
    "fiction novel", "mystery novel",
]

# 人物主题下，图书标题必须包含以下之一才可能相关
_PERSON_TOPIC_REQUIRED_KEYWORDS: dict[str, list[str]] = {
    "tim cook": [
        "tim cook", "apple", "steve jobs", "leadership", "biography",
        "ceo", "leander kahney", "silicon valley", "iphone", "cook",
    ],
}


def _normalize(text: str) -> str:
    """标准化文本用于匹配。"""
    return re.sub(r'\s+', ' ', text.lower().strip())


def rule_based_book_relevance(
    topic: str,
    canonical_topic: str,
    main_entity: str,
    book_title: str,
    authors: str = "",
    snippet: str = "",
) -> BookRelevanceResult:
    """
    规则兜底过滤 - 即使 LLM 不可用也能过滤明显不相关的图书。

    Returns:
        BookRelevanceResult，is_relevant=False 表示应被过滤。
    """
    title_lower = _normalize(book_title)
    topic_lower = _normalize(topic)
    canonical_lower = _normalize(canonical_topic) if canonical_topic else topic_lower
    entity_lower = _normalize(main_entity) if main_entity else ""
    combined_text = f"{title_lower} {_normalize(authors)} {_normalize(snippet)}"

    # 1. 明确排除关键词
    for keyword in _ALWAYS_EXCLUDE_KEYWORDS:
        if keyword in title_lower:
            # 但如果主题本身就是这个领域，不排除
            if keyword not in topic_lower and keyword not in canonical_lower:
                return BookRelevanceResult(
                    is_relevant=False,
                    relevance_level="irrelevant",
                    why_relevant=f"标题含排除关键词「{keyword}」，与研究主题无关",
                    book_type=_guess_book_type(title_lower),
                )

    # 2. 人物主题特殊规则
    for person_key, required_keywords in _PERSON_TOPIC_REQUIRED_KEYWORDS.items():
        if person_key in topic_lower or person_key in canonical_lower:
            # 检查标题+作者+摘要是否包含任何必要关键词
            has_required = any(kw in combined_text for kw in required_keywords)
            if not has_required:
                return BookRelevanceResult(
                    is_relevant=False,
                    relevance_level="irrelevant",
                    why_relevant=f"主题是「{person_key}」但图书内容未提及相关关键词",
                    book_type=_guess_book_type(title_lower),
                )

            # 额外检查：标题只含 "cook" 但不含 "tim cook" 的情况
            if person_key == "tim cook":
                if "cook" in title_lower and "tim cook" not in title_lower:
                    # 检查是否有其他强信号
                    strong_signals = ["apple", "ceo", "leander kahney", "biography"]
                    if not any(sig in combined_text for sig in strong_signals):
                        return BookRelevanceResult(
                            is_relevant=False,
                            relevance_level="irrelevant",
                            why_relevant="标题含 Cook 但无法确认是 Tim Cook 相关",
                            risk_warning="可能是同名不同人",
                            book_type=_guess_book_type(title_lower),
                        )

    # 3. 通过规则检查 → 判为可能相关
    # 检查是否有强相关信号
    if entity_lower and entity_lower in title_lower:
        return BookRelevanceResult(
            is_relevant=True,
            relevance_level="high",
            why_relevant=f"标题直接包含研究主体「{main_entity}」",
            book_type=_guess_book_type(title_lower),
        )

    # 默认：通过规则过滤，标记为 medium
    return BookRelevanceResult(
        is_relevant=True,
        relevance_level="medium",
        why_relevant="通过规则过滤，待 LLM 进一步确认",
        book_type=_guess_book_type(title_lower),
    )


def _guess_book_type(title_lower: str) -> str:
    """根据标题猜测图书类型。"""
    if any(kw in title_lower for kw in ("biography", "life of", "story of", "传记")):
        return "biography"
    if any(kw in title_lower for kw in ("cookbook", "recipe", "cooking")):
        return "cookbook"
    if any(kw in title_lower for kw in ("business", "leadership", "management", "ceo")):
        return "business"
    if any(kw in title_lower for kw in ("programming", "python", "javascript", "code")):
        return "technical"
    if any(kw in title_lower for kw in ("novel", "fiction", "mystery")):
        return "fiction"
    if any(kw in title_lower for kw in ("self-help", "habits", "mindset")):
        return "self_help"
    return "unknown"


# === LLM 增强判断 ===


class BookRelevanceService:
    """图书相关性过滤服务 - LLM 优先，规则兜底。"""

    def __init__(self, ai_gateway: "AIGateway | None" = None) -> None:
        self._ai_gateway = ai_gateway

    async def check_relevance(
        self,
        topic: str,
        canonical_topic: str = "",
        main_entity: str = "",
        book_title: str = "",
        authors: str = "",
        publish_year: str = "",
        snippet: str = "",
        provider: str = "",
        matched_query: str = "",
    ) -> BookRelevanceResult:
        """
        判断图书是否与研究主题相关。

        优先使用 LLM，失败时使用规则兜底。
        """
        canonical = canonical_topic or topic

        # 先用规则快速过滤明显不相关的
        rule_result = rule_based_book_relevance(
            topic=topic,
            canonical_topic=canonical,
            main_entity=main_entity,
            book_title=book_title,
            authors=authors,
            snippet=snippet,
        )

        # 如果规则已经判为 irrelevant，直接返回（不浪费 LLM 调用）
        if not rule_result.is_relevant:
            return rule_result

        # 尝试 LLM 增强
        llm_result = await self._try_llm_review(
            topic=topic,
            canonical_topic=canonical,
            main_entity=main_entity,
            book_title=book_title,
            authors=authors,
            publish_year=publish_year,
            snippet=snippet,
            provider=provider,
            matched_query=matched_query,
        )

        if llm_result is not None:
            return llm_result

        # LLM 失败，返回规则结果
        return rule_result

    async def _try_llm_review(
        self,
        topic: str,
        canonical_topic: str,
        main_entity: str,
        book_title: str,
        authors: str,
        publish_year: str,
        snippet: str,
        provider: str,
        matched_query: str,
    ) -> BookRelevanceResult | None:
        """尝试 LLM 判断，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        try:
            result = await self._ai_gateway.run_json(
                task_name="book_relevance_review",
                payload={
                    "original_topic": topic,
                    "canonical_topic": canonical_topic,
                    "main_entity": main_entity,
                    "book_title": book_title,
                    "authors": authors,
                    "publish_year": publish_year,
                    "snippet": snippet,
                    "provider": provider,
                    "matched_query": matched_query,
                },
                output_schema=BookRelevanceResult,
                language="zh",
            )
            return result
        except Exception as e:
            logger.warning(
                "book_relevance_review_failed book=%s error=%s",
                book_title[:50], str(e)[:100],
            )
            return None
