"""主题理解服务 - 分析研究主题，判断模式并提取实体。"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.ai.schemas import TopicUnderstandingOutput
from models.enums import TaskMode

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# 规则关键词映射
_EVENT_KEYWORDS = re.compile(r"争议|诉讼|收购|事件|丑闻|倒闭|破产|审判|调查|崩盘|collapse|lawsuit|scandal|acquisition", re.IGNORECASE)
_COMPANY_KEYWORDS = re.compile(r"公司|创业|融资|产品|企业|集团|startup|company|funding|IPO|Inc|Corp|Ltd", re.IGNORECASE)
_CONCEPT_KEYWORDS = re.compile(r"模型|概念|起源|定义|理论|算法|框架|原理|model|concept|theory|algorithm|definition", re.IGNORECASE)


class TopicUnderstandingService:
    """分析研究主题，输出 TopicUnderstandingOutput。"""

    def __init__(self, ai_gateway: AIGateway | None = None) -> None:
        self._ai_gateway = ai_gateway

    async def analyze(
        self,
        topic: str,
        user_selected_mode: TaskMode | None = None,
    ) -> TopicUnderstandingOutput:
        """分析主题。

        如果用户手动选择了 mode，LLM 不覆盖 mode，只补充 entities/focus。
        如果 mode=auto 或 None，优先 LLM 判断，失败时规则判断。
        """
        need_mode_detection = user_selected_mode is None or user_selected_mode == TaskMode.AUTO

        # 尝试 LLM
        llm_output = await self._try_llm(topic)

        if llm_output is not None:
            # LLM 成功
            if need_mode_detection:
                # 使用 LLM 判断的 mode
                mode = self._normalize_mode(llm_output.mode)
            else:
                # 用户指定 mode，不覆盖
                mode = user_selected_mode.value  # type: ignore[union-attr]

            return TopicUnderstandingOutput(
                mode=mode,
                main_entity=llm_output.main_entity or topic,
                normalized_topic=llm_output.normalized_topic or topic,
                language=llm_output.language,
                aliases=llm_output.aliases,
                people=llm_output.people,
                organizations=llm_output.organizations,
                places=llm_output.places,
                concepts=llm_output.concepts,
                suggested_focus=llm_output.suggested_focus,
            )

        # LLM 失败，规则 fallback
        if need_mode_detection:
            mode = self._rule_based_mode(topic)
        else:
            mode = user_selected_mode.value  # type: ignore[union-attr]

        return TopicUnderstandingOutput(
            mode=mode,
            main_entity=topic,
            normalized_topic=topic,
            language="zh",
        )

    async def _try_llm(self, topic: str) -> TopicUnderstandingOutput | None:
        """尝试 LLM 分析，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        try:
            return await self._ai_gateway.run_json(
                task_name="topic_understanding",
                payload={"topic": topic},
                output_schema=TopicUnderstandingOutput,
                language="zh",
            )
        except Exception as e:
            logger.warning("llm_topic_understanding_failed topic=%s error=%s", topic, str(e))
            return None

    def _rule_based_mode(self, topic: str) -> str:
        """规则判断 mode。"""
        if _EVENT_KEYWORDS.search(topic):
            return TaskMode.EVENT.value
        if _COMPANY_KEYWORDS.search(topic):
            return TaskMode.COMPANY.value
        if _CONCEPT_KEYWORDS.search(topic):
            return TaskMode.CONCEPT.value
        return TaskMode.PERSON.value

    def _normalize_mode(self, mode_str: str) -> str:
        """将 LLM 输出的 mode 标准化为 TaskMode 值。"""
        mode_lower = mode_str.lower().strip()
        for m in TaskMode:
            if m.value == mode_lower:
                return m.value
        return TaskMode.AUTO.value
