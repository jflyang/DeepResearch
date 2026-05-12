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


class ExtractionService:
    """正文提取编排服务。"""

    def __init__(self, extractor: BaseExtractor | None = None):
        self._extractor = extractor or TrafilaturaExtractor()

    async def extract_source(self, source_item: SourceItem) -> ExtractedDocument:
        """
        提取来源正文并生成 ExtractedDocument。

        流程：
        1. 标记 download_status = downloading
        2. 调用 extractor
        3. 成功 → 创建 ExtractedDocument, 标记 extracted
        4. 失败 → 标记 failed

        Returns:
            ExtractedDocument（success=False 时 content 为空）
        """
        logger.info(
            "extraction_started source_id=%s url=%s",
            source_item.id,
            source_item.url,
        )

        # 标记下载中
        source_item.download_status = DownloadStatus.DOWNLOADING

        # 调用提取器
        result: ExtractedContent = await self._extractor.extract(source_item.url)

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
