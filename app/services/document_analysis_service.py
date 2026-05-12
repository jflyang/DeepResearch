"""文档分析服务 - 正文提取后的摘要、实体、故事点生成。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.ai.budget import apply_input_budget
from app.ai.schemas import DocumentAnalysisOutput
from app.ai.tasks import load_llm_task_config

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


class ExtractedDocument(BaseModel):
    """提取后的文档内容。"""

    url: str
    title: str = ""
    content: str = ""
    word_count: int = 0


class DocumentAnalysisService:
    """对提取后的文档进行 LLM 分析。"""

    def __init__(self, ai_gateway: AIGateway | None = None) -> None:
        self._ai_gateway = ai_gateway

    async def analyze(
        self,
        document: ExtractedDocument,
        topic: str = "",
    ) -> DocumentAnalysisOutput:
        """分析文档，返回结构化分析结果。LLM 失败时返回空对象。"""
        if self._ai_gateway is None:
            return DocumentAnalysisOutput()

        # 加载任务配置获取 max_input_chars
        try:
            config = load_llm_task_config("document_summary")
            max_chars = config.max_input_chars
        except Exception:
            max_chars = 12000

        # 截断正文
        truncated_content = apply_input_budget(document.content, max_chars)

        # 调用 LLM
        try:
            result: DocumentAnalysisOutput = await self._ai_gateway.run_json(
                task_name="document_summary",
                payload={
                    "topic": topic,
                    "content": truncated_content,
                },
                output_schema=DocumentAnalysisOutput,
                language="zh",
            )
            return result
        except Exception as e:
            logger.warning(
                "document_analysis_failed url=%s error=%s",
                document.url, str(e),
            )
            return DocumentAnalysisOutput()
