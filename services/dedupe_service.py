"""去重服务 - 对多源搜索结果按 URL 去重并合并信息。"""

import logging

from pydantic import BaseModel, Field

from models.enums import SearchSource, SourceType
from providers.search.base import SearchResult
from utils.url import normalize_url

logger = logging.getLogger(__name__)


class DedupedSourceCandidate(BaseModel):
    """去重合并后的候选来源。"""

    normalized_url: str
    url: str  # 保留原始 URL（取第一个出现的）
    title: str
    snippet: str = ""
    source_providers: list[SearchSource] = Field(default_factory=list)
    source_type: SourceType = SourceType.OTHER
    published_at: str | None = None  # ISO string or None
    raw_items: list[dict] = Field(default_factory=list, exclude=True)


def _select_better_title(existing: str, new: str) -> str:
    """选择更长且信息量更高的 title。"""
    if not existing:
        return new
    if not new:
        return existing
    # 优先选更长的
    if len(new) > len(existing):
        return new
    return existing


def _merge_snippets(existing: str, new: str, max_length: int = 500) -> str:
    """合并 snippet，避免重复内容。"""
    if not new:
        return existing
    if not existing:
        return new
    # 如果新 snippet 已包含在旧的中，跳过
    if new in existing:
        return existing
    if existing in new:
        return new
    # 拼接，限制长度
    merged = f"{existing} | {new}"
    if len(merged) > max_length:
        merged = merged[:max_length]
    return merged


def dedupe_results(results: list[SearchResult]) -> list[DedupedSourceCandidate]:
    """
    对搜索结果按规范化 URL 去重，合并来自不同 provider 的信息。

    合并规则：
    - title: 选更长的
    - snippet: 拼接不重复部分
    - source_providers: 记录所有来源 provider
    - source_type: 保留第一个非 OTHER 的类型
    - published_at: 保留第一个非空值
    - raw_items: 保留所有原始数据

    Returns:
        去重合并后的 DedupedSourceCandidate 列表（保持首次出现顺序）
    """
    seen: dict[str, DedupedSourceCandidate] = {}
    order: list[str] = []

    for result in results:
        key = normalize_url(result.url)

        if key in seen:
            # 合并到已有记录
            candidate = seen[key]
            candidate.title = _select_better_title(candidate.title, result.title)
            candidate.snippet = _merge_snippets(candidate.snippet, result.snippet)

            if result.source_provider not in candidate.source_providers:
                candidate.source_providers.append(result.source_provider)

            # 保留第一个非 OTHER 的 source_type
            if candidate.source_type == SourceType.OTHER and result.source_type != SourceType.OTHER:
                candidate.source_type = result.source_type

            # 保留第一个非空 published_at
            if candidate.published_at is None and result.published_at is not None:
                candidate.published_at = result.published_at.isoformat()

            candidate.raw_items.append(result.raw)
        else:
            # 新记录
            candidate = DedupedSourceCandidate(
                normalized_url=key,
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                source_providers=[result.source_provider],
                source_type=result.source_type,
                published_at=result.published_at.isoformat() if result.published_at else None,
                raw_items=[result.raw] if result.raw else [],
            )
            seen[key] = candidate
            order.append(key)

    deduped = [seen[key] for key in order]

    removed = len(results) - len(deduped)
    if removed > 0:
        logger.info(
            "results_deduped total=%d unique=%d removed=%d",
            len(results),
            len(deduped),
            removed,
        )
    else:
        logger.info("results_deduped total=%d unique=%d removed=0", len(results), len(deduped))

    return deduped
