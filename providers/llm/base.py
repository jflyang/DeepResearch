"""LLM 服务抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any

from core.errors import ProviderError


class LLMProvider(ABC):
    """所有 LLM 服务必须实现此接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 标识名。"""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str | ProviderError:
        """生成文本。成功返回字符串，失败返回 ProviderError。"""

    async def health_check(self) -> bool:
        return True
