"""Crawlee 网页抓取模块 - 低耦合的搜索结果 URL 抓取引擎。

职责：
- 访问搜索结果 URL 并提取网页正文
- 候选 URL 相关性判断
- 批量抓取管理

不负责：
- 搜索引擎查询（由 SearchRouter / Search Provider 负责）
- LLM 分析（由 DocumentAnalysisService 负责）
- 数据持久化（由调用方负责）
- Obsidian 导出（由 MarkdownService 负责）
"""

from app.crawlers.base import CrawlCandidate, CrawlRequest, CrawlResult, CrawlBatchResult
from app.crawlers.crawlee_service import CrawleeCrawlerService
from app.crawlers.content_extractor import ContentExtractor
from app.crawlers.relevance_filter import RelevanceFilter

__all__ = [
    "CrawlCandidate",
    "CrawlRequest",
    "CrawlResult",
    "CrawlBatchResult",
    "CrawleeCrawlerService",
    "ContentExtractor",
    "RelevanceFilter",
]
