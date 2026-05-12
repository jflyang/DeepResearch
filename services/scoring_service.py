"""评分服务 - 对候选来源进行可解释的评分和分类。

评分规则从 config/source_rules.yaml 加载，不硬编码。
"""

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

from core.config import get_settings
from models.enums import SourceLevel, SourceType
from services.dedupe_service import DedupedSourceCandidate

logger = logging.getLogger(__name__)


# === 规则加载 ===


@lru_cache
def _load_rules() -> dict:
    """加载评分规则配置。"""
    rules_path = Path("config/source_rules.yaml")
    if not rules_path.exists():
        logger.warning("scoring_rules_not_found path=%s using_defaults=true", rules_path)
        return {}
    with open(rules_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _reset_rules_cache() -> None:
    """清除规则缓存（仅测试用）。"""
    _load_rules.cache_clear()


# === 评分结果 ===


class ScoringResult:
    """评分结果 - 可解释的评分输出。"""

    def __init__(
        self,
        relevance_score: float,
        authority_score: float,
        originality_score: float,
        gossip_score: float,
        source_level: SourceLevel,
        category: str,
        reason_to_read: str,
    ):
        self.relevance_score = relevance_score
        self.authority_score = authority_score
        self.originality_score = originality_score
        self.gossip_score = gossip_score
        self.source_level = source_level
        self.category = category
        self.reason_to_read = reason_to_read


class ScoredCandidate:
    """评分后的候选来源。"""

    def __init__(self, candidate: DedupedSourceCandidate, scoring: ScoringResult):
        self.candidate = candidate
        self.scoring = scoring

    @property
    def final_score(self) -> float:
        settings = get_settings()
        s = self.scoring
        raw = (
            settings.scoring_relevance_weight * s.relevance_score
            + settings.scoring_authority_weight * s.authority_score
            + settings.scoring_originality_weight * s.originality_score
            - settings.scoring_gossip_penalty * s.gossip_score
        )
        return max(0.0, min(1.0, round(raw, 4)))


# === 内部评分函数 ===


def _match_domain(domain: str, rules: dict) -> tuple[float, str]:
    """匹配域名到权威度分组，返回 (score, group_name)。"""
    authority_domains = rules.get("authority_domains", {})

    for group_name, group_config in authority_domains.items():
        # 精确域名匹配
        domains_list = group_config.get("domains", [])
        for d in domains_list:
            if d in domain:
                return group_config["score"], group_name

        # 后缀匹配
        suffixes = group_config.get("suffix", [])
        for suffix in suffixes:
            if domain.endswith(suffix):
                return group_config["score"], group_name

    return 0.3, "unknown"


def _authority_score(domain: str, rules: dict) -> tuple[float, str]:
    """计算权威度评分。"""
    score, group = _match_domain(domain, rules)
    return score, group


def _relevance_score(candidate: DedupedSourceCandidate, topic: str) -> float:
    """基于内容信号的相关性评分。"""
    score = 0.2

    # title 包含 topic 关键词
    if topic and topic.lower() in candidate.title.lower():
        score += 0.3

    # snippet 长度
    if candidate.snippet:
        length = len(candidate.snippet)
        if length > 300:
            score += 0.3
        elif length > 100:
            score += 0.2
        elif length > 30:
            score += 0.1

    # 有发布日期
    if candidate.published_at:
        score += 0.1

    # 多个 provider 都返回了（说明相关性高）
    if len(candidate.source_providers) > 1:
        score += 0.1

    return min(score, 1.0)


def _originality_score(source_type: SourceType, domain_group: str) -> float:
    """基于来源类型和域名分组的原创性评分。"""
    if domain_group in ("official", "academic"):
        return 0.95
    if domain_group == "government":
        return 0.9
    if source_type == SourceType.BOOK:
        return 0.8
    if domain_group == "major_media":
        return 0.7
    if domain_group == "university":
        return 0.85
    if domain_group == "tech":
        return 0.6
    if source_type == SourceType.DOCUMENTATION:
        return 0.6
    if domain_group in ("community", "blog_platform"):
        return 0.3
    if source_type == SourceType.BLOG:
        return 0.35
    if source_type == SourceType.FORUM:
        return 0.25
    return 0.4


def _gossip_score(title: str, domain: str, rules: dict) -> float:
    """计算八卦/低质量信号评分。"""
    gossip_signals = rules.get("gossip_signals", {})
    score = 0.0

    # 标题模式匹配
    title_lower = title.lower()
    for pattern in gossip_signals.get("title_patterns", []):
        if re.search(pattern, title_lower):
            score += 0.3
            break

    # 八卦域名
    for d in gossip_signals.get("domains", []):
        if d in domain:
            score += 0.4
            break

    return min(score, 1.0)


def _is_low_quality(title: str, domain: str, rules: dict) -> bool:
    """检测是否为低质量内容。"""
    low_quality = rules.get("low_quality", {})

    # 标题模式
    title_lower = title.lower()
    for pattern in low_quality.get("title_patterns", []):
        if re.search(pattern, title_lower):
            return True

    # 低质量域名
    for d in low_quality.get("domains", []):
        if d in domain:
            return True

    return False


def _classify_category(
    candidate: DedupedSourceCandidate,
    domain_group: str,
    gossip: float,
    is_low_qual: bool,
) -> str:
    """分类来源类别。"""
    if is_low_qual:
        return "low_quality"

    if domain_group in ("official", "government"):
        return "official"

    if domain_group == "academic":
        return "primary_source"

    # 标题关键词分类
    title_lower = candidate.title.lower()

    if any(kw in title_lower for kw in ("transcript", "full text", "verbatim", "deposition")):
        return "transcript"

    if any(kw in title_lower for kw in ("interview", "q&a", "conversation with", "talks to")):
        return "interview"

    if any(kw in title_lower for kw in ("profile", "investigation", "deep dive", "longread")):
        return "deep_profile"

    if candidate.source_type == SourceType.BOOK or domain_group == "book":
        return "book"

    if gossip >= 0.3:
        return "gossip"

    if domain_group == "major_media":
        return "deep_profile"

    if domain_group in ("community", "blog_platform"):
        return "local_source"

    return "general"


def _compute_level(final_score: float, rules: dict) -> SourceLevel:
    """根据阈值计算等级。"""
    thresholds = rules.get("level_thresholds", {})
    if final_score >= thresholds.get("S", 0.82):
        return SourceLevel.S
    if final_score >= thresholds.get("A", 0.65):
        return SourceLevel.A
    if final_score >= thresholds.get("B", 0.50):
        return SourceLevel.B
    if final_score >= thresholds.get("C", 0.35):
        return SourceLevel.C
    return SourceLevel.D


def _build_reason(category: str, domain_group: str, level: SourceLevel) -> str:
    """生成简短的阅读理由。"""
    reasons = {
        "official": "Official/government source",
        "primary_source": "Primary academic source",
        "transcript": "First-hand transcript",
        "interview": "Direct interview content",
        "deep_profile": "In-depth profile or investigation",
        "book": "Book-length treatment",
        "gossip": "Gossip/tabloid content",
        "low_quality": "Low quality or SEO content",
        "local_source": "Community or blog source",
    }
    reason = reasons.get(category, f"General source ({domain_group})")
    return f"[{level}] {reason}"


# === 公开 API ===


def score_candidate(
    candidate: DedupedSourceCandidate,
    topic: str = "",
    mode: str = "auto",
) -> ScoringResult:
    """对单个候选来源评分。"""
    rules = _load_rules()
    domain = candidate.url.split("//")[-1].split("/")[0].lower()

    authority, domain_group = _authority_score(domain, rules)
    relevance = _relevance_score(candidate, topic)
    originality = _originality_score(candidate.source_type, domain_group)
    gossip = _gossip_score(candidate.title, domain, rules)
    is_low_qual = _is_low_quality(candidate.title, domain, rules)

    # 低质量惩罚
    if is_low_qual:
        authority = min(authority, 0.2)
        originality = min(originality, 0.2)

    category = _classify_category(candidate, domain_group, gossip, is_low_qual)

    # 计算 final score 用于确定 level
    settings = get_settings()
    raw_final = (
        settings.scoring_relevance_weight * relevance
        + settings.scoring_authority_weight * authority
        + settings.scoring_originality_weight * originality
        - settings.scoring_gossip_penalty * gossip
    )
    raw_final = max(0.0, min(1.0, raw_final))
    level = _compute_level(raw_final, rules)

    reason = _build_reason(category, domain_group, level)

    logger.debug(
        "source_scored url=%s level=%s category=%s authority=%.2f relevance=%.2f",
        candidate.url,
        level,
        category,
        authority,
        relevance,
    )

    return ScoringResult(
        relevance_score=round(relevance, 4),
        authority_score=round(authority, 4),
        originality_score=round(originality, 4),
        gossip_score=round(gossip, 4),
        source_level=level,
        category=category,
        reason_to_read=reason,
    )


def score_candidates(
    candidates: list[DedupedSourceCandidate],
    topic: str = "",
    mode: str = "auto",
) -> list[ScoredCandidate]:
    """对候选列表评分，按 final_score 降序排列。"""
    scored: list[ScoredCandidate] = []

    for candidate in candidates:
        scoring = score_candidate(candidate, topic=topic, mode=mode)
        scored.append(ScoredCandidate(candidate=candidate, scoring=scoring))

    scored.sort(key=lambda x: x.final_score, reverse=True)
    logger.info("scoring_completed total=%d", len(scored))
    return scored
