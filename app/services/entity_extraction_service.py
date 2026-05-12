"""实体提取服务 - 从文本中提取结构化实体。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.ai.budget import apply_input_budget
from app.ai.schemas import EntityExtractionOutput, EntityType
from app.ai.tasks import load_llm_task_config

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


class EntityCandidate(BaseModel):
    """统一实体输出。"""

    name: str
    type: str
    description: str = ""
    relation_to_topic: str = ""
    source_url: str = ""
    should_expand: bool = False
    confidence: str = "medium"  # high / medium / low


class EntityExtractionService:
    """从文本中提取实体，优先 LLM，失败时规则 fallback。"""

    def __init__(self, ai_gateway: AIGateway | None = None) -> None:
        self._ai_gateway = ai_gateway

    async def extract(
        self,
        topic: str,
        text: str,
        source_url: str = "",
    ) -> list[EntityCandidate]:
        """提取实体列表。空文本返回空列表。"""
        if not text or not text.strip():
            return []

        # 尝试 LLM
        result = await self._try_llm(topic, text, source_url)
        if result is not None:
            return result

        # fallback：返回空列表
        return []

    async def _try_llm(
        self,
        topic: str,
        text: str,
        source_url: str,
    ) -> list[EntityCandidate] | None:
        """尝试 LLM 提取，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        # 加载配置获取 max_input_chars
        try:
            config = load_llm_task_config("entity_extraction")
            max_chars = config.max_input_chars
        except Exception:
            max_chars = 8000

        truncated_text = apply_input_budget(text, max_chars)

        try:
            output: EntityExtractionOutput = await self._ai_gateway.run_json(
                task_name="entity_extraction",
                payload={"text": truncated_text},
                output_schema=EntityExtractionOutput,
                language="zh",
            )
        except Exception as e:
            logger.warning(
                "entity_extraction_failed topic=%s source=%s error=%s",
                topic, source_url, str(e),
            )
            return None

        # 转换为 EntityCandidate
        candidates: list[EntityCandidate] = []
        for entity in output.entities:
            candidates.append(EntityCandidate(
                name=entity.name,
                type=entity.type.value,
                description=entity.description,
                relation_to_topic=entity.relation_to_topic,
                source_url=source_url,
                should_expand=entity.should_expand,
                confidence="high" if entity.should_expand else "medium",
            ))
        return candidates
