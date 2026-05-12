"""查询扩展服务 - 规则版 + LLM 增强 + 语言规划支持。

支持 LLM 增强查询扩展，LLM 失败时自动 fallback 到规则版。
当提供 ResearchLanguagePlan 时，根据 search_strategy 生成中英比例合适的 query。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

from models.enums import LanguageCode, SearchStrategy, TaskMode
from models.schemas import ExpandedQuery as RichExpandedQuery
from models.schemas import ResearchLanguagePlan

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


# === 输出模型（保持向后兼容） ===


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

# === 中文规则模板 ===

_PERSON_TEMPLATES_ZH = [
    ("{topic} 传记", "传记搜索", "web"),
    ("{topic} 早年经历", "早年经历", "web"),
    ("{topic} 童年", "童年故事", "web"),
    ("{topic} 家庭背景", "家庭背景", "web"),
    ("{topic} 采访", "采访记录", "web"),
    ("{topic} 创业经历", "创业经历", "web"),
]

_COMPANY_TEMPLATES_ZH = [
    ("{topic} 创业故事", "创业故事", "web"),
    ("{topic} 创始人", "创始人信息", "web"),
    ("{topic} 早期发展", "早期发展", "web"),
    ("{topic} 融资历程", "融资历程", "web"),
    ("{topic} 竞争对手", "竞争分析", "web"),
]

_EVENT_TEMPLATES_ZH = [
    ("{topic} 时间线", "事件时间线", "web"),
    ("{topic} 争议", "争议详情", "web"),
    ("{topic} 诉讼", "法律诉讼", "web"),
    ("{topic} 调查", "调查报道", "web"),
    ("{topic} 内幕", "内幕消息", "web"),
]

_CONCEPT_TEMPLATES_ZH = [
    ("{topic} 起源", "概念起源", "web"),
    ("{topic} 发展历史", "发展历史", "web"),
    ("{topic} 论文", "学术论文", "web"),
    ("{topic} 关键人物", "关键人物", "web"),
]

_MODE_MAP_ZH: dict[TaskMode, list[tuple[str, str, str]]] = {
    TaskMode.PERSON: _PERSON_TEMPLATES_ZH,
    TaskMode.COMPANY: _COMPANY_TEMPLATES_ZH,
    TaskMode.EVENT: _EVENT_TEMPLATES_ZH,
    TaskMode.CONCEPT: _CONCEPT_TEMPLATES_ZH,
    TaskMode.AUTO: _CONCEPT_TEMPLATES_ZH,
}

# 低质量 query 模式
_LOW_QUALITY_PATTERNS = re.compile(
    r"\b(what is|overview|top \d+|facts about|wiki)\b",
    re.IGNORECASE,
)


# === 服务函数（规则版，保持向后兼容） ===


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


# === QueryExpansionService（LLM 增强版 + 语言规划） ===


class QueryExpansionService:
    """查询扩展服务 - 支持 LLM 增强和语言规划，失败时 fallback 到规则版。"""

    def __init__(self, ai_gateway: "AIGateway | None" = None) -> None:
        self._ai_gateway = ai_gateway

    async def expand(
        self,
        topic: str,
        mode: TaskMode = TaskMode.AUTO,
        include_books: bool = True,
        include_video: bool = False,
        include_gossip: bool = False,
        round_number: int = 1,
        language_plan: ResearchLanguagePlan | None = None,
    ) -> list[RichExpandedQuery]:
        """扩展查询：根据语言规划生成中英比例合适的 query。

        如果 language_plan=None，保持原有逻辑（向后兼容）。
        """
        if language_plan is None:
            # 无语言规划 → 原有逻辑（LLM + 规则合并）
            return await self._expand_legacy(
                topic=topic,
                mode=mode,
                include_books=include_books,
                include_video=include_video,
                include_gossip=include_gossip,
                round_number=round_number,
            )

        # 有语言规划 → 按策略生成
        rule_queries = self._generate_with_plan(
            language_plan=language_plan,
            mode=mode,
            include_books=include_books,
            include_video=include_video,
            include_gossip=include_gossip,
            round_number=round_number,
        )

        # 尝试 LLM 增强
        llm_queries = await self._try_llm_expand_with_plan(
            language_plan=language_plan,
            mode=mode,
            round_number=round_number,
        )

        if llm_queries:
            merged = self._merge_rich_queries(llm_queries, rule_queries)
        else:
            merged = rule_queries

        # 过滤低质量 query
        merged = [q for q in merged if not _LOW_QUALITY_PATTERNS.search(q.query)]

        return merged

    async def _expand_legacy(
        self,
        topic: str,
        mode: TaskMode,
        include_books: bool,
        include_video: bool,
        include_gossip: bool,
        round_number: int,
    ) -> list[RichExpandedQuery]:
        """原有逻辑：LLM + 规则合并，转换为 RichExpandedQuery。"""
        # 规则版结果
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
            return [self._legacy_to_rich(q) for q in rule_queries]

        # 尝试 LLM 增强
        llm_queries = await self._try_llm_expand(topic, mode, round_number)
        if not llm_queries:
            return [self._legacy_to_rich(q) for q in rule_queries]

        # 合并去重（legacy 类型）
        merged = self._merge_queries(llm_queries, rule_queries)
        return [self._legacy_to_rich(q) for q in merged]

    # ============================================================
    # 语言规划感知的规则生成
    # ============================================================

    def _generate_with_plan(
        self,
        language_plan: ResearchLanguagePlan,
        mode: TaskMode,
        include_books: bool,
        include_video: bool,
        include_gossip: bool,
        round_number: int,
    ) -> list[RichExpandedQuery]:
        """根据语言规划生成中英文 query。"""
        strategy = language_plan.search_strategy
        canonical = language_plan.main_entity_canonical or language_plan.canonical_topic or language_plan.original_topic
        original = language_plan.main_entity_original or language_plan.original_topic

        # 确定英文和中文 topic
        en_topic = canonical
        zh_topic = original

        # 生成英文 queries
        en_queries = self._generate_en_queries(
            en_topic=en_topic,
            mode=mode,
            include_books=include_books,
            include_video=include_video,
            include_gossip=include_gossip,
            round_number=round_number,
            canonical_entity=language_plan.main_entity_canonical,
            original_user_term=language_plan.main_entity_original,
        )

        # 生成中文 queries
        zh_queries = self._generate_zh_queries(
            zh_topic=zh_topic,
            mode=mode,
            round_number=round_number,
            canonical_entity=language_plan.main_entity_canonical,
            original_user_term=language_plan.main_entity_original,
        )

        # 按策略分配比例和优先级
        if strategy == SearchStrategy.ENGLISH_FIRST:
            return self._apply_english_first(en_queries, zh_queries)
        elif strategy == SearchStrategy.CHINESE_FIRST:
            return self._apply_chinese_first(en_queries, zh_queries)
        else:  # bilingual
            return self._apply_bilingual(en_queries, zh_queries)

    def _generate_en_queries(
        self,
        en_topic: str,
        mode: TaskMode,
        include_books: bool,
        include_video: bool,
        include_gossip: bool,
        round_number: int,
        canonical_entity: str | None,
        original_user_term: str | None,
    ) -> list[RichExpandedQuery]:
        """生成英文 queries。"""
        templates = list(_MODE_MAP.get(mode, _CONCEPT_TEMPLATES))
        if include_books:
            templates.extend(_BOOK_TEMPLATES)
        if include_gossip:
            templates.extend(_GOSSIP_TEMPLATES)
        if include_video:
            templates.extend(_VIDEO_TEMPLATES)

        seen: set[str] = set()
        results: list[RichExpandedQuery] = []

        for template, purpose, source_hint in templates:
            query_text = template.format(topic=en_topic)
            query_lower = query_text.lower().strip()

            if query_lower in seen:
                continue
            seen.add(query_lower)

            results.append(RichExpandedQuery(
                query=query_text,
                purpose=purpose,
                source_hint=source_hint,
                priority=5,
                round=round_number,
                language=LanguageCode.EN,
                canonical_entity=canonical_entity,
                original_user_term=original_user_term,
            ))

        return results

    def _generate_zh_queries(
        self,
        zh_topic: str,
        mode: TaskMode,
        round_number: int,
        canonical_entity: str | None,
        original_user_term: str | None,
    ) -> list[RichExpandedQuery]:
        """生成中文 queries。"""
        templates = list(_MODE_MAP_ZH.get(mode, _CONCEPT_TEMPLATES_ZH))

        seen: set[str] = set()
        results: list[RichExpandedQuery] = []

        for template, purpose, source_hint in templates:
            query_text = template.format(topic=zh_topic)
            query_lower = query_text.lower().strip()

            if query_lower in seen:
                continue
            seen.add(query_lower)

            results.append(RichExpandedQuery(
                query=query_text,
                purpose=purpose,
                source_hint=source_hint,
                priority=5,
                round=round_number,
                language=LanguageCode.ZH,
                canonical_entity=canonical_entity,
                original_user_term=original_user_term,
            ))

        return results

    def _apply_english_first(
        self,
        en_queries: list[RichExpandedQuery],
        zh_queries: list[RichExpandedQuery],
    ) -> list[RichExpandedQuery]:
        """english_first: 英文 ~80%, 中文 ~20%。英文优先级更高。"""
        # 英文全部保留，高优先级
        for i, q in enumerate(en_queries):
            q.priority = min(10, 8 - i // 3)  # 8, 8, 8, 7, 7, 7, ...

        # 中文取前 ~25% 数量，低优先级
        zh_count = max(2, len(en_queries) // 4)
        zh_subset = zh_queries[:zh_count]
        for q in zh_subset:
            q.priority = 3

        return en_queries + zh_subset

    def _apply_chinese_first(
        self,
        en_queries: list[RichExpandedQuery],
        zh_queries: list[RichExpandedQuery],
    ) -> list[RichExpandedQuery]:
        """chinese_first: 中文 ~80%, 英文 ~20%。中文优先级更高。"""
        # 中文全部保留，高优先级
        for i, q in enumerate(zh_queries):
            q.priority = min(10, 8 - i // 3)

        # 英文取前 ~25% 数量，低优先级
        en_count = max(2, len(zh_queries) // 4)
        en_subset = en_queries[:en_count]
        for q in en_subset:
            q.priority = 3

        return zh_queries + en_subset

    def _apply_bilingual(
        self,
        en_queries: list[RichExpandedQuery],
        zh_queries: list[RichExpandedQuery],
    ) -> list[RichExpandedQuery]:
        """bilingual: 中英文各约一半，优先级相同。"""
        # 取两边数量的较大值作为目标
        target = max(len(en_queries), len(zh_queries))
        en_subset = en_queries[:target]
        zh_subset = zh_queries[:target]

        for q in en_subset:
            q.priority = 6
        for q in zh_subset:
            q.priority = 6

        return en_subset + zh_subset

    # ============================================================
    # LLM 增强（语言规划感知）
    # ============================================================

    async def _try_llm_expand_with_plan(
        self,
        language_plan: ResearchLanguagePlan,
        mode: TaskMode,
        round_number: int,
    ) -> list[RichExpandedQuery]:
        """尝试 LLM 扩展（带语言规划上下文），失败返回空列表。"""
        if self._ai_gateway is None:
            return []

        from app.ai.schemas import QueryExpansionOutput

        # 构建 LLM payload，注入语言规划信息
        payload = {
            "topic": language_plan.canonical_topic or language_plan.original_topic,
            "context": mode.value,
            "num_queries": 8,
            "canonical_entity": language_plan.main_entity_canonical or "",
            "language_plan_note": (
                f"search_strategy={language_plan.search_strategy.value}, "
                f"working_language={language_plan.working_language.value}"
            ),
            "english_query_weight": (
                "0.8" if language_plan.search_strategy == SearchStrategy.ENGLISH_FIRST
                else "0.2" if language_plan.search_strategy == SearchStrategy.CHINESE_FIRST
                else "0.5"
            ),
        }

        try:
            output: QueryExpansionOutput = await self._ai_gateway.run_json(
                task_name="query_expansion",
                payload=payload,
                output_schema=QueryExpansionOutput,
                language="zh",
            )
        except Exception as e:
            logger.warning(
                "llm_query_expansion_failed topic=%s error=%s",
                language_plan.original_topic, str(e),
            )
            return []

        # 转换为 RichExpandedQuery
        results: list[RichExpandedQuery] = []
        for item in output.queries:
            results.append(RichExpandedQuery(
                query=item.query,
                purpose=item.purpose,
                source_hint=item.source_hint.value,
                priority=item.priority,
                round=round_number,
                language=self._detect_query_language(item.query),
                canonical_entity=language_plan.main_entity_canonical,
                original_user_term=language_plan.main_entity_original,
            ))
        return results

    async def _try_llm_expand(
        self,
        topic: str,
        mode: TaskMode,
        round_number: int,
    ) -> list[ExpandedQuery]:
        """尝试 LLM 扩展，失败返回空列表（向后兼容）。"""
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

    # ============================================================
    # 合并与辅助
    # ============================================================

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

    def _merge_rich_queries(
        self,
        llm_queries: list[RichExpandedQuery],
        rule_queries: list[RichExpandedQuery],
    ) -> list[RichExpandedQuery]:
        """合并 LLM 和规则 RichExpandedQuery，去重保留高优先级。"""
        merged: dict[str, RichExpandedQuery] = {}

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

        results = sorted(merged.values(), key=lambda x: x.priority, reverse=True)
        return results

    def _legacy_to_rich(self, q: ExpandedQuery) -> RichExpandedQuery:
        """将旧版 ExpandedQuery 转换为 RichExpandedQuery。"""
        return RichExpandedQuery(
            query=q.query,
            purpose=q.purpose,
            source_hint=q.source_hint,
            priority=min(q.priority, 10),
            round=q.round,
            language=self._detect_query_language(q.query),
            canonical_entity=None,
            original_user_term=None,
        )

    def _detect_query_language(self, query: str) -> LanguageCode:
        """简单检测 query 语言。"""
        import re as _re
        cjk_count = len(_re.findall(r"[\u4e00-\u9fff]", query))
        if cjk_count > 0:
            return LanguageCode.ZH
        return LanguageCode.EN
