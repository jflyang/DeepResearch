"""正文提取器抽象基类。"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExtractedContent(BaseModel):
    """提取结果统一结构。"""

    title: str = ""
    author: str = ""
    published_at: str = ""
    source_url: str = ""
    text: str = ""
    html: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None


class BaseExtractor(ABC):
    """正文提取器抽象基类。所有提取器必须实现此接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """提取器标识名。"""

    @abstractmethod
    async def extract(self, url: str) -> ExtractedContent:
        """
        提取网页正文。

        永远不应抛出未捕获异常。失败时返回 success=False + error 描述。
        """
