"""结果分类服务 - 按研究模式将 SourceItem 分类供 UI 展示。

一个 SourceItem 可以进入多个分类。
"""

import logging
import re

from models.enums import SourceLevel, TaskMode
from models.schemas import SourceItem

logger = logging.getLogger(__name__)

# === 基础分类 ===

BASE_CATEGORIES = [
    "必读资料",
    "一手资料",
    "官方资料",
    "深度报道",
    "图书资料",
    "采访与演讲",
    "地方资料",
    "八卦与旁证",
    "争议资料",
    "低质量隐藏",
]

# === 模式额外分类 ===

_PERSON_CATEGORIES = [
    "童年与家庭",
    "教育经历",
    "早期职业",
    "性格与习惯",
    "人际关系",
    "争议与传闻",
]

_COMPANY_CATEGORIES = [
    "创始阶段",
    "融资与投资人",
    "早期产品",
    "关键失败",
    "竞争对手",
    "战略转型",
]

_EVENT_CATEGORIES = [
    "时间线",
    "关键文件",
    "参与方",
    "各方说法",
    "冲突点",
    "后续影响",
]

_CONCEPT_CATEGORIES = [
    "定义",
    "起源",
    "代表论文",
    "关键人物",
    "技术前史",
    "后续演化",
    "争议",
    "应用案例",
]

_MODE_CATEGORIES: dict[TaskMode, list[str]] = {
    TaskMode.PERSON: _PERSON_CATEGORIES,
    TaskMode.COMPANY: _COMPANY_CATEGORIES,
    TaskMode.EVENT: _EVENT_CATEGORIES,
    TaskMode.CONCEPT: _CONCEPT_CATEGORIES,
    TaskMode.AUTO: _CONCEPT_CATEGORIES,
}

# === 关键词匹配规则 ===

_PERSON_KEYWORDS: dict[str, list[str]] = {
    "童年与家庭": ["childhood", "family", "parents", "mother", "father", "grew up", "born", "siblings", "early life"],
    "教育经历": ["school", "university", "college", "education", "degree", "graduated", "student"],
    "早期职业": ["early career", "first job", "started", "founded", "co-founded", "began"],
    "性格与习惯": ["personality", "habits", "routine", "character", "style", "philosophy"],
    "人际关系": ["relationship", "marriage", "wife", "husband", "partner", "friend", "mentor"],
    "争议与传闻": ["controversy", "scandal", "rumor", "allegation", "lawsuit", "accused"],
}

_COMPANY_KEYWORDS: dict[str, list[str]] = {
    "创始阶段": ["founding", "founded", "co-founded", "origin", "started", "early days", "garage"],
    "融资与投资人": ["funding", "investor", "venture", "series", "valuation", "ipo", "raised"],
    "早期产品": ["first product", "launch", "prototype", "mvp", "early product", "beta"],
    "关键失败": ["failure", "failed", "bankrupt", "crisis", "layoff", "shutdown", "pivot"],
    "竞争对手": ["competitor", "competition", "rival", "versus", "vs", "market share"],
    "战略转型": ["pivot", "transformation", "strategy", "restructur", "rebrand", "new direction"],
}

_EVENT_KEYWORDS: dict[str, list[str]] = {
    "时间线": ["timeline", "chronolog", "sequence", "history", "dates"],
    "关键文件": ["document", "filing", "report", "evidence", "record", "transcript"],
    "参与方": ["parties", "involved", "participant", "stakeholder", "defendant", "plaintiff"],
    "各方说法": ["statement", "testimony", "claimed", "denied", "alleged", "according to"],
    "冲突点": ["dispute", "conflict", "controversy", "disagreement", "contested"],
    "后续影响": ["aftermath", "impact", "consequence", "result", "legacy", "changed"],
}

_CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "定义": ["definition", "what is", "meaning", "concept", "refers to"],
    "起源": ["origin", "history", "invented", "coined", "first proposed", "emerged"],
    "代表论文": ["paper", "publication", "research", "study", "journal", "arxiv"],
    "关键人物": ["pioneer", "inventor", "researcher", "key people", "contributor", "founder"],
    "技术前史": ["predecessor", "before", "earlier", "precursor", "evolution", "prior art"],
    "后续演化": ["evolution", "development", "progress", "advancement", "future", "next generation"],
    "争议": ["controversy", "debate", "criticism", "limitation", "challenge", "ethical"],
    "应用案例": ["application", "use case", "implementation", "deployed", "real world", "example"],
}

_MODE_KEYWORDS: dict[TaskMode, dict[str, list[str]]] = {
    TaskMode.PERSON: _PERSON_KEYWORDS,
    TaskMode.COMPANY: _COMPANY_KEYWORDS,
    TaskMode.EVENT: _EVENT_KEYWORDS,
    TaskMode.CONCEPT: _CONCEPT_KEYWORDS,
    TaskMode.AUTO: _CONCEPT_KEYWORDS,
}


# === 分类逻辑 ===


def _matches_keywords(item: SourceItem, keywords: list[str]) -> bool:
    """检查 item 的 title+snippet 是否匹配任一关键词。"""
    text = f"{item.title} {item.snippet}".lower()
    return any(kw in text for kw in keywords)


def _classify_base(item: SourceItem) -> list[str]:
    """基础分类。"""
    categories: list[str] = []

    # D 级 → 低质量隐藏
    if item.source_level == SourceLevel.D:
        categories.append("低质量隐藏")
        return categories

    # S 级 → 必读资料
    if item.source_level == SourceLevel.S:
        categories.append("必读资料")

    # 官方资料
    if item.reason_to_read and "official" in item.reason_to_read.lower():
        categories.append("官方资料")

    # 一手资料
    if item.reason_to_read and "primary" in item.reason_to_read.lower():
        categories.append("一手资料")
    text_lower = f"{item.title} {item.snippet}".lower()
    if any(kw in text_lower for kw in ("transcript", "deposition", "filing", "testimony")):
        if "一手资料" not in categories:
            categories.append("一手资料")

    # 图书资料
    if item.source_type.value == "book" or (item.reason_to_read and "book" in item.reason_to_read.lower()):
        categories.append("图书资料")

    # 采访与演讲
    if any(kw in text_lower for kw in ("interview", "q&a", "speech", "lecture", "talk", "keynote")):
        categories.append("采访与演讲")

    # 深度报道
    if item.reason_to_read and "depth" in item.reason_to_read.lower():
        categories.append("深度报道")
    elif item.source_level in (SourceLevel.A, SourceLevel.S) and len(item.snippet) > 150:
        categories.append("深度报道")

    # 争议资料
    if any(kw in text_lower for kw in ("controversy", "lawsuit", "scandal", "investigation", "accused")):
        categories.append("争议资料")

    # 八卦与旁证
    if item.gossip_score >= 0.3:
        categories.append("八卦与旁证")
    elif item.source_level == SourceLevel.C and item.gossip_score > 0:
        categories.append("八卦与旁证")

    # 地方资料
    if item.reason_to_read and ("community" in item.reason_to_read.lower() or "local" in item.reason_to_read.lower()):
        categories.append("地方资料")

    # 低质量隐藏（非 D 级但 reason 标记为 low_quality）
    if item.reason_to_read and "low quality" in item.reason_to_read.lower():
        categories.append("低质量隐藏")

    return categories


def _classify_mode(item: SourceItem, mode: TaskMode) -> list[str]:
    """按模式额外分类。"""
    keywords_map = _MODE_KEYWORDS.get(mode, {})
    categories: list[str] = []

    for category, keywords in keywords_map.items():
        if _matches_keywords(item, keywords):
            categories.append(category)

    return categories


def _sort_items(items: list[SourceItem]) -> list[SourceItem]:
    """按 source_level 和综合分排序。"""
    level_order = {SourceLevel.S: 0, SourceLevel.A: 1, SourceLevel.B: 2, SourceLevel.C: 3, SourceLevel.D: 4}

    def sort_key(item: SourceItem) -> tuple[int, float]:
        level_rank = level_order.get(item.source_level, 4)
        # 综合分取负数实现降序
        composite = item.relevance_score + item.authority_score + item.originality_score
        return (level_rank, -composite)

    return sorted(items, key=sort_key)


# === 公开 API ===


def classify_results(
    items: list[SourceItem],
    mode: TaskMode = TaskMode.AUTO,
) -> dict[str, list[SourceItem]]:
    """
    将 SourceItem 列表按研究模式分类。

    一个 item 可以出现在多个分类中。
    每个分类内按 source_level + 综合分排序。

    Returns:
        分类名 → 排序后的 SourceItem 列表
    """
    # 初始化所有分类
    mode_categories = _MODE_CATEGORIES.get(mode, [])
    all_category_names = BASE_CATEGORIES + mode_categories
    result: dict[str, list[SourceItem]] = {name: [] for name in all_category_names}

    for item in items:
        # 基础分类
        base_cats = _classify_base(item)
        for cat in base_cats:
            if cat in result:
                result[cat].append(item)

        # D 级只进低质量，不做模式分类
        if item.source_level == SourceLevel.D:
            continue

        # 模式额外分类
        mode_cats = _classify_mode(item, mode)
        for cat in mode_cats:
            if cat in result:
                result[cat].append(item)

    # 每个分类内排序
    for cat in result:
        result[cat] = _sort_items(result[cat])

    # 移除空分类
    result = {k: v for k, v in result.items() if v}

    logger.info(
        "classification_completed mode=%s items=%d categories=%d",
        mode,
        len(items),
        len(result),
    )

    return result
