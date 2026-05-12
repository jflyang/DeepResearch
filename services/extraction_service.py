"""正文提取编排服务。

职责：接收 source_item_id → 提取正文 → 保存 ExtractedDocument → 更新状态。
"""

import logging
from datetime import UTC, datetime

from models.enums import DownloadStatus
from models.schemas import ExtractedDocument, SourceItem
from providers.extraction.base import BaseExtractor, ExtractedContent
from providers.extraction.trafilatura_extractor import TrafilaturaExtractor

logger = logging.getLogger(__name__)

# 不可提取的 URL 模式（这些是 API 信息页或预览页，不是可读正文）
_NON_EXTRACTABLE_DOMAINS = [
    "books.google.com",
    "books.google.co",
    "play.google.com/store/books",
    "openlibrary.org/works",
    "openlibrary.org/books",
]


def _is_non_extractable_url(url: str) -> str | None:
    """检查 URL 是否为已知不可提取的类型。返回原因或 None。"""
    url_lower = url.lower()
    for pattern in _NON_EXTRACTABLE_DOMAINS:
        if pattern in url_lower:
            return f"图书信息页（{pattern}）不包含可提取正文，需手动获取图书内容"
    return None


class ExtractionService:
    """正文提取编排服务。

    策略：trafilatura 优先 → 失败时 fallback 到 Playwright 浏览器提取。
    """

    def __init__(self, extractor: BaseExtractor | None = None, enable_browser_fallback: bool = True):
        self._extractor = extractor or TrafilaturaExtractor()
        # 如果显式传入了自定义 extractor（测试场景），禁用 browser fallback
        self._enable_browser_fallback = enable_browser_fallback if extractor is None else False

    async def extract_source(self, source_item: SourceItem) -> ExtractedDocument:
        """
        提取来源正文并生成 ExtractedDocument。

        流程：
        1. 检查 URL 是否可提取
        2. 标记 download_status = downloading
        3. 调用 trafilatura 提取
        4. 如果失败且 browser fallback 可用 → 调用 Playwright 提取
        5. 成功 → 创建 ExtractedDocument, 标记 extracted
        6. 失败 → 标记 failed

        Returns:
            ExtractedDocument（success=False 时 content 为空）
        """
        logger.info(
            "extraction_started source_id=%s url=%s",
            source_item.id,
            source_item.url,
        )

        # 检查是否为已知不可提取的 URL
        non_extractable_reason = _is_non_extractable_url(source_item.url)
        if non_extractable_reason:
            source_item.download_status = DownloadStatus.SKIPPED
            logger.info(
                "extraction_skipped source_id=%s url=%s reason=%s",
                source_item.id, source_item.url, non_extractable_reason,
            )
            return ExtractedDocument(
                source_item_id=source_item.id,
                title=source_item.title,
                author="",
                content="",
            )

        # 标记下载中
        source_item.download_status = DownloadStatus.DOWNLOADING

        # 1. 尝试 trafilatura
        result: ExtractedContent = await self._extractor.extract(source_item.url)

        # 2. 如果 trafilatura 失败，尝试 Playwright 浏览器
        if not result.success and self._enable_browser_fallback:
            browser_result = await self._try_browser_extraction(source_item.url)
            if browser_result and browser_result.success:
                result = browser_result
                logger.info(
                    "browser_fallback_succeeded source_id=%s url=%s chars=%d",
                    source_item.id, source_item.url, len(result.text),
                )

        if result.success:
            source_item.download_status = DownloadStatus.EXTRACTED
            doc = ExtractedDocument(
                source_item_id=source_item.id,
                title=result.title or source_item.title,
                author=result.author,
                content=result.text,
                summary="",
                key_quotes=[],
                people=[],
                places=[],
                organizations=[],
                concepts=[],
                events=[],
            )
            logger.info(
                "extraction_completed source_id=%s chars=%d title=%s",
                source_item.id,
                len(result.text),
                doc.title[:50],
            )
            return doc
        else:
            source_item.download_status = DownloadStatus.FAILED
            logger.warning(
                "extraction_failed source_id=%s url=%s error=%s",
                source_item.id,
                source_item.url,
                result.error,
            )
            return ExtractedDocument(
                source_item_id=source_item.id,
                title=source_item.title,
                author="",
                content="",
            )

    async def _try_browser_extraction(self, url: str) -> ExtractedContent | None:
        """尝试使用 Playwright 浏览器提取。未安装时返回 None。"""
        try:
            from providers.extraction.playwright_extractor import (
                PlaywrightExtractor,
                is_playwright_available,
            )

            if not is_playwright_available():
                logger.debug("browser_fallback_unavailable reason=playwright_not_installed")
                return None

            extractor = PlaywrightExtractor(timeout_ms=30000)
            return await extractor.extract(url)

        except Exception as e:
            logger.warning("browser_fallback_failed url=%s error=%s", url, str(e)[:100])
            return None
