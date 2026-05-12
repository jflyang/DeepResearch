"""查询扩展服务 - 规则版 + LLM 增强。

支持 LLM 增强查询扩展，LLM 失败时自动 fallback 到规则版。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

from models.enums import TaskMode

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


# === 输出模型 ===


class ExpandedQuery(BaseModel):
    query: str
    purpose: str = ""
    source_hint: str = "general"  # web/book/video/archive/general
    priority: int = 1
    round: int = 1


# === LLM 扩展接口（未来实现） ===


class QueryExpander(Protocol):
    """LLM query expansion 接口，未来可接 Ollama。"""

    async def expand(self, topic: str, mode: TaskMode) -> list[ExpandedQuery]: ...


# === 规则模板 ===

_PERSON_TEMPLATES = [
    ("{topic} biography", "biography", "web"),
    ("{topic} early life", "early_life", "web"),
    ("{topic} childhood", "childhood", "web"),
    ("{topic} parents", "family", "web"),
    ("{topic} interview", "interview", "web"),
    ("{topic} profile", "profile", "web"),
    ("{topic} family background", "family", "web"),
    ("{topic} career", "career", "web"),
    ("{topic} achievements", "achievements", "web"),
]

_COMPANY_TEMPLATES = [
    ("{topic} founding story", "founding", "web"),
    ("{topic} founders", "founders", "web"),
    ("{topic} early history", "early_history", "web"),
    ("{topic} product history", "product", "web"),
    ("{topic} failure", "failure", "web"),
    ("{topic} business model", "business", "web"),
    ("{topic} competitors", "competitors", "web"),
]

_EVENT_TEMPLATES = [
    ("{topic} timeline", "timeline", "web"),
    ("{topic} controversy", "controversy", "web"),
    ("{topic} lawsuit", "legal", "web"),
    ("{topic} SEC", "regulatory", "web"),
    ("{topic} court", "legal", "web"),
    ("{topic} investigation", "investigation", "web"),
    ("{topic} aftermath", "aftermath", "web"),
]

_CONCEPT_TEMPLATES = [
    ("{topic} origin", "origin", "web"),
    ("{topic} history", "history", "web"),
    ("{topic} paper", "academic", "web"),
    ("{topic} key people", "people", "web"),
    ("{topic} controversy", "controversy", "web"),
    ("{topic} applications", "applications", "web"),
    ("{topic} definition", "definition", "web"),
]

_BOOK_TEMPLATES = [
    ("{topic} biography book", "book_bio", "book"),
    ("{topic} book", "book_general", "book"),
    ("{topic} memoir", "book_memoir", "book"),
]

_GOSSIP_TEMPLATES = [
    ("{topic} rumor", "gossip", "web"),
    ("{topic} personal life", "gossip", "web"),
    ("{topic} controversy", "gossip", "web"),
    ("{topic} scandal", "gossip", "web"),
]

_VIDEO_TEMPLATES = [
    ("{topic} documentary", "video", "video"),
    ("{topic} interview video", "video", "video"),
    ("{topic} lecture", "video", "video"),
]

_MODE_MAP: dict[TaskMode, list[tuple[str, str, str]]] = {
    TaskMode.PERSON: _PERSON_TEMPLATES,
    TaskMode.COMPANY: _COMPANY_TEMPLATES,
    TaskMode.EVENT: _EVENT_TEMPLATES,
    TaskMode.CONCEPT: _CONCEPT_TEMPLATES,
    TaskMode.AUTO: _CONCEPT_TEMPLATES,
}


# === 服务函数（规则版） ===


def expand_queries(
    topic: str,
    mode: TaskMode = TaskMode.AUTO,
    include_books: bool = True,
    include_video: bool = False,
    include_gossip: bool = False,
    round_number: int = 1,
) -> list[ExpandedQuery]:
    """
    根据主题和模式生成扩展查询列表（纯规则版）。

    Args:
        topic: 研究主题
        mode: 研究模式
        include_books: 是否包含图书查询
        include_video: 是否包含视频查询
        include_gossip: 是否包含八卦查询
        round_number: 当前轮次

    Returns:
        去重后的 ExpandedQuery 列表
    """
    logger.info(
        "query_expanded topic=%s mode=%s include_books=%s include_gossip=%s include_video=%s",
        topic,
        mode,
        include_books,
        include_gossip,
        include_video,
    )

    templates = list(_MODE_MAP.get(mode, _CONCEPT_TEMPLATES))

    if include_books:
        templates.extend(_BOOK_TEMPLATES)

    if include_gossip:
        templates.extend(_GOSSIP_TEMPLATES)

    if include_video:
        templates.extend(_VIDEO_TEMPLATES)

    # 生成并去重
    seen: set[str] = set()
    results: list[ExpandedQuery] = []
    priority = 1

    for template, purpose, source_hint in templates:
        query_text = template.format(topic=topic)
        query_lower = query_text.lower().strip()

        if query_lower in seen:
            continue
        seen.add(query_lower)

        results.append(
            ExpandedQuery(
                query=query_text,
                purpose=purpose,
                source_hint=source_hint,
                priority=priority,
                round=round_number,
            )
        )
        priority += 1

    logger.info("query_expanded_count topic=%s count=%d", topic, len(results))
    return results


# === QueryExpansionService（LLM 增强版） ===


class QueryExpansionService:
    """查询扩展服务 - 支持 LLM 增强，失败时 fallback 到规则版。"""

    def __init__(self, ai_gateway: AIGateway | None = None) -> None:
        self._ai_gateway = ai_gateway

    async def expand(
        self,
        topic: str,
        mode: TaskMode = TaskMode.AUTO,
        include_books: bool = True,
        include_video: bool = False,
        include_gossip: bool = False,
        round_number: int = 1,
    ) -> list[ExpandedQuery]:
        """扩展查询：LLM + 规则合并去重，LLM 失败时纯规则。"""
        # 规则版结果（始终生成）
        rule_queries = expand_queries(
            topic=topic,
            mode=mode,
            include_books=include_books,
            include_video=include_video,
            include_gossip=include_gossip,
            round_number=round_number,
        )

        # 如果无 gateway，直接返回规则版
        if self._ai_gateway is None:
            return rule_queries

        # 尝试 LLM 增强
        llm_queries = await self._try_llm_expand(topic, mode, round_number)
        if not llm_queries:
            return rule_queries

        # 合并去重
        return self._merge_queries(llm_queries, rule_queries)

    async def _try_llm_expand(
        self,
        topic: str,
        mode: TaskMode,
        round_number: int,
    ) -> list[ExpandedQuery]:
        """尝试 LLM 扩展，失败返回空列表。"""
        from app.ai.schemas import QueryExpansionOutput

        try:
            output: QueryExpansionOutput = await self._ai_gateway.run_json(  # type: ignore[union-attr]
                task_name="query_expansion",
                payload={
                    "topic": topic,
                    "context": mode.value,
                    "num_queries": 8,
                },
                output_schema=QueryExpansionOutput,
                language="zh",
            )
        except Exception as e:
            logger.warning("llm_query_expansion_failed topic=%s error=%s", topic, str(e))
            return []

        # 转换为 ExpandedQuery
        results: list[ExpandedQuery] = []
        for item in output.queries:
            results.append(ExpandedQuery(
                query=item.query,
                purpose=item.purpose,
                source_hint=item.source_hint.value,
                priority=item.priority,
                round=round_number,
            ))
        return results

    def _merge_queries(
        self,
        llm_queries: list[ExpandedQuery],
        rule_queries: list[ExpandedQuery],
    ) -> list[ExpandedQuery]:
        """合并 LLM 和规则 queries，去重保留高优先级。"""
        merged: dict[str, ExpandedQuery] = {}

        # LLM queries 优先
        for q in llm_queries:
            key = q.query.lower().strip()
            if key not in merged or q.priority > merged[key].priority:
                merged[key] = q

        # 规则 queries 补充
        for q in rule_queries:
            key = q.query.lower().strip()
            if key not in merged:
                merged[key] = q

        # 按 priority 排序
        results = sorted(merged.values(), key=lambda x: x.priority, reverse=True)
        return results
