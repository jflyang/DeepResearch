"""Trafilatura 正文提取器。"""

import asyncio
import logging
from functools import partial

import trafilatura

from providers.extraction.base import BaseExtractor, ExtractedContent

logger = logging.getLogger(__name__)


class TrafilaturaExtractor(BaseExtractor):
    """使用 trafilatura 提取网页正文。"""

    @property
    def name(self) -> str:
        return "trafilatura"

    async def extract(self, url: str) -> ExtractedContent:
        """提取网页正文。在线程池中运行阻塞的 trafilatura 调用。"""
        logger.info("extraction_started extractor=%s url=%s", self.name, url)

        if not url or not url.startswith(("http://", "https://")):
            logger.warning("extraction_failed extractor=%s url=%s reason=invalid_url", self.name, url)
            return ExtractedContent(
                source_url=url,
                success=False,
                error="Invalid URL: must start with http:// or https://",
            )

        try:
            result = await asyncio.to_thread(self._extract_sync, url)
            return result
        except Exception as e:
            logger.error("extraction_failed extractor=%s url=%s error=%s", self.name, url, str(e))
            return ExtractedContent(
                source_url=url,
                success=False,
                error=f"Unexpected error: {type(e).__name__}: {e}",
            )

    def _extract_sync(self, url: str) -> ExtractedContent:
        """同步提取逻辑（在线程池中执行）。"""
        # 获取页面
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            logger.warning("extraction_failed extractor=%s url=%s reason=fetch_failed", self.name, url)
            return ExtractedContent(
                source_url=url,
                success=False,
                error="Failed to fetch URL: no response or connection error",
            )

        # 提取正文
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )

        if not text or not text.strip():
            logger.warning("extraction_failed extractor=%s url=%s reason=empty_content", self.name, url)
            return ExtractedContent(
                source_url=url,
                success=False,
                error="Extraction returned empty content",
            )

        # 提取元数据
        metadata = trafilatura.extract(
            downloaded,
            output_format="json",
            include_comments=False,
        )

        meta_dict = self._parse_metadata(metadata)

        title = meta_dict.get("title", "")
        author = meta_dict.get("author", "")
        date = meta_dict.get("date", "")

        logger.info(
            "extraction_completed extractor=%s url=%s chars=%d title=%s",
            self.name,
            url,
            len(text),
            title[:50],
        )

        return ExtractedContent(
            title=title,
            author=author,
            published_at=date,
            source_url=url,
            text=text,
            metadata=meta_dict,
            success=True,
        )

    @staticmethod
    def _parse_metadata(json_str: str | None) -> dict:
        """解析 trafilatura JSON 输出为 dict。"""
        if not json_str:
            return {}
        import json
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return {}
