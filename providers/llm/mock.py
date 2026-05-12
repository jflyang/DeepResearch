"""Mock LLM Provider - 用于测试。"""

import logging
from typing import Any

from core.errors import ProviderError
from providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class MockLLMProvider(LLMProvider):
    """返回固定响应的 Mock LLM，用于单元测试和无 LLM 环境。"""

    @property
    def name(self) -> str:
        return "mock"

    async def generate(self, prompt: str, **kwargs: Any) -> str | ProviderError:
        logger.debug("MockLLM called with prompt length: %d", len(prompt))
        # 返回简单的查询扩展结果
        return "expanded query 1\nexpanded query 2\nexpanded query 3"
