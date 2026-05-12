"""RelevanceFilter - 判断搜索结果候选 URL 是否值得抓取。

规则优先，可选 LLM 增强。
不直接调用 LLM，通过回调接口支持 LLM 判断。
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import yaml

from app.crawlers.base import CrawlCandidate
from models.enums import CrawlSkipReason, SearchResultDepth

logger = logging.getLogger(__name__)

# === Configuration ===

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CRAWLING_POLICY_PATH = _PROJECT_ROOT / "config" / "crawling_policy.yaml"


@lru_cache
def _load_relevance_config() -> dict:
    """加载相关性过滤配置。"""
    if not _CRAWLING_POLICY_PATH.exists():
        return _default_relevance_config()
    try:
        with open(_CRAWLING_POLICY_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("relevance_filter", _default_relevance_config())
    except Exception:
        return _default_relevance_config()


def _default_relevance_config() -> dict:
    return {
        "enabled": True,
        "min_score": 0.55,
        "llm_enabled": False,
        "top_n_for_llm_review": 30,
    }


def reset_relevance_config_cache() -> None:
    """清除配置缓存（测试用）。"""
    _load_relevance_config.cache_clear()


# === Blocked Patterns ===

# 明确无关的 URL 模式
_BLOCKED_URL_PATTERNS = [
    r"login", r"signin", r"signup", r"register",
    r"cart", r"checkout", r"add-to-cart",
    r"/ads/", r"/sponsored/",
    r"shopping", r"/shop/", r"/product/",
    r"recipe", r"cookbook",
]

# 明确无关的域名
_BLOCKED_DOMAINS = [
    "amazon.com", "ebay.com", "aliexpress.com",
    "pinterest.com", "instagram.com", "tiktok.com",
    "facebook.com", "twitter.com",
]

# 低优先域名（不阻止，但降低分数）
_LOW_PRIORITY_DOMAINS = [
    "wikipedia.org", "en.wikipedia.org", "zh.wikipedia.org",
]

# 高权威域名（提高分数）
_HIGH_AUTHORITY_DOMAINS = [
    ".edu", ".gov", ".ac.",
    "nature.com", "science.org", "ieee.org",
    "nytimes.com", "washingtonpost.com", "bbc.com", "bbc.co.uk",
    "reuters.com", "apnews.com",
    "arxiv.org", "scholar.google.com",
]

# 不支持的内容类型后缀
_UNSUPPORTED_EXTENSIONS = [
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".zip", ".rar", ".tar",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv",
    ".jpg", ".jpeg", ".png", ".gif", ".svg",
]


class RelevanceFilter:
    """判断搜索结果候选 URL 是否值得抓取。

    规则：
    1. title/snippet/domain 与 topic 高相关 → should_crawl=true
    2. 明显无关（菜谱、购物、广告）→ should_crawl=false
    3. Wikipedia 默认低优先
    4. 官方、大学、权威媒体优先
    5. 排除 login/ads/shopping/duplicate
    6. top30/top100 限制
    """

    def __init__(
        self,
        config: dict | None = None,
        llm_reviewer: Callable | None = None,
    ):
        """
        Args:
            config: 相关性过滤配置
            llm_reviewer: 可选的 LLM 审查回调，签名: async (candidates, topic) -> list[CrawlCandidate]
        """
        self._config = config or _load_relevance_config()
        self._llm_reviewer = llm_reviewer

    async def filter_candidates(
        self,
        candidates: list[dict[str, Any]],
        topic: str,
        canonical_topic: str | None = None,
        depth: SearchResultDepth = SearchResultDepth.TOP30,
    ) -> list[CrawlCandidate]:
        """对搜索结果候选进行相关性过滤。

        Args:
            candidates: 原始搜索结果列表，每项包含 url, title, snippet, rank 等
            topic: 研究主题
            canonical_topic: 规范化主题名（如英文名）
            depth: 搜索深度（top30/top50/top100）

        Returns:
            CrawlCandidate 列表，包含 relevance_score 和 should_crawl 判断
        """
        if not self._config.get("enabled", True):
            # 过滤器禁用，全部通过
            return [
                CrawlCandidate(
                    url=c.get("url", ""),
                    title=c.get("title"),
                    snippet=c.get("snippet"),
                    source_provider=c.get("source_provider"),
                    matched_query=c.get("matched_query"),
                    rank=c.get("rank"),
                    relevance_score=1.0,
                    should_crawl=True,
                )
                for c in candidates
            ]

        # 确定最大候选数
        max_candidates = _depth_to_max(depth)

        # 规则过滤
        seen_urls: set[str] = set()
        filtered: list[CrawlCandidate] = []

        for candidate_data in candidates[:max_candidates]:
            url = candidate_data.get("url", "")
            if not url:
                continue

            # 去重
            normalized_url = self._normalize_url(url)
            if normalized_url in seen_urls:
                filtered.append(CrawlCandidate(
                    url=url,
                    title=candidate_data.get("title"),
                    snippet=candidate_data.get("snippet"),
                    source_provider=candidate_data.get("source_provider"),
                    matched_query=candidate_data.get("matched_query"),
                    rank=candidate_data.get("rank"),
                    relevance_score=0.0,
                    should_crawl=False,
                    skip_reason=CrawlSkipReason.DUPLICATE_URL,
                ))
                continue
            seen_urls.add(normalized_url)

            # 规则评分
            score, skip_reason = self._score_candidate(
                url=url,
                title=candidate_data.get("title", ""),
                snippet=candidate_data.get("snippet", ""),
                topic=topic,
                canonical_topic=canonical_topic,
                rank=candidate_data.get("rank"),
            )

            min_score = self._config.get("min_score", 0.55)
            should_crawl = score >= min_score and skip_reason is None

            filtered.append(CrawlCandidate(
                url=url,
                title=candidate_data.get("title"),
                snippet=candidate_data.get("snippet"),
                source_provider=candidate_data.get("source_provider"),
                matched_query=candidate_data.get("matched_query"),
                rank=candidate_data.get("rank"),
                source_hint=candidate_data.get("source_hint"),
                relevance_score=score,
                should_crawl=should_crawl,
                skip_reason=skip_reason if not should_crawl else None,
            ))

        # 可选 LLM 审查
        if (
            self._config.get("llm_enabled", False)
            and self._llm_reviewer is not None
        ):
            top_n = self._config.get("top_n_for_llm_review", 30)
            to_review = [c for c in filtered if c.should_crawl][:top_n]
            if to_review:
                try:
                    reviewed = await self._llm_reviewer(to_review, topic)
                    # 合并 LLM 结果
                    reviewed_map = {c.url: c for c in reviewed}
                    for i, c in enumerate(filtered):
                        if c.url in reviewed_map:
                            filtered[i] = reviewed_map[c.url]
                except Exception as e:
                    logger.warning("llm_relevance_review_failed error=%s", str(e)[:100])
                    # LLM 失败 fallback 到规则判断，不影响结果

        # 按 relevance_score 降序排列
        filtered.sort(key=lambda c: (c.should_crawl, c.relevance_score or 0), reverse=True)

        logger.info(
            "relevance_filter_completed total=%d should_crawl=%d skipped=%d",
            len(filtered),
            sum(1 for c in filtered if c.should_crawl),
            sum(1 for c in filtered if not c.should_crawl),
        )

        return filtered

    def _score_candidate(
        self,
        url: str,
        title: str,
        snippet: str,
        topic: str,
        canonical_topic: str | None,
        rank: int | None,
    ) -> tuple[float, CrawlSkipReason | None]:
        """对单个候选进行规则评分。

        Returns:
            (score, skip_reason) - score 0.0~1.0, skip_reason 为 None 表示通过
        """
        score = 0.5  # 基础分
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()

        # === 阻止规则 ===

        # 检查 blocked domains
        for blocked in _BLOCKED_DOMAINS:
            if blocked in domain:
                return 0.0, CrawlSkipReason.BLOCKED_DOMAIN

        # 检查 blocked URL patterns
        url_lower = url.lower()
        for pattern in _BLOCKED_URL_PATTERNS:
            if re.search(pattern, url_lower):
                return 0.1, CrawlSkipReason.LOW_RELEVANCE

        # 检查不支持的文件类型
        for ext in _UNSUPPORTED_EXTENSIONS:
            if path.endswith(ext):
                return 0.0, CrawlSkipReason.UNSUPPORTED_CONTENT_TYPE

        # === 加分规则 ===

        # 主题相关性（title + snippet 中包含主题关键词）
        topic_terms = self._extract_terms(topic)
        canonical_terms = self._extract_terms(canonical_topic) if canonical_topic else []
        all_terms = topic_terms + canonical_terms

        text_to_check = f"{title} {snippet}".lower()

        term_matches = sum(1 for term in all_terms if term.lower() in text_to_check)
        if all_terms:
            term_ratio = term_matches / len(all_terms)
            score += term_ratio * 0.3  # 最多 +0.3

        # 高权威域名加分
        for auth_domain in _HIGH_AUTHORITY_DOMAINS:
            if auth_domain in domain:
                score += 0.15
                break

        # 低优先域名减分
        for low_domain in _LOW_PRIORITY_DOMAINS:
            if low_domain in domain:
                score -= 0.15
                break

        # 排名加分（越靠前越好）
        if rank is not None and rank > 0:
            if rank <= 5:
                score += 0.1
            elif rank <= 10:
                score += 0.05

        # 长标题/snippet 通常更有信息量
        if len(title) > 30:
            score += 0.05
        if len(snippet) > 100:
            score += 0.05

        # 访谈、长文、研究报告关键词加分
        valuable_keywords = ["interview", "访谈", "研究", "report", "analysis", "深度", "exclusive", "独家"]
        for kw in valuable_keywords:
            if kw in text_to_check:
                score += 0.1
                break

        # 确保分数在 0~1 范围
        score = max(0.0, min(1.0, score))

        return score, None

    def _extract_terms(self, text: str | None) -> list[str]:
        """从文本中提取关键词。"""
        if not text:
            return []
        # 简单分词：按空格和标点分割，过滤短词
        terms = re.split(r'[\s,;，；、]+', text)
        return [t for t in terms if len(t) >= 2]

    def _normalize_url(self, url: str) -> str:
        """URL 归一化用于去重。"""
        parsed = urlparse(url)
        # 去掉 fragment 和 trailing slash
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        return normalized.lower()


def _depth_to_max(depth: SearchResultDepth) -> int:
    """将搜索深度转换为最大候选数。"""
    mapping = {
        SearchResultDepth.TOP30: 30,
        SearchResultDepth.TOP50: 50,
        SearchResultDepth.TOP100: 100,
    }
    return mapping.get(depth, 30)
