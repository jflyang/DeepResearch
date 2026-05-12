"""搜索 Provider 抽象层 - 定义统一接口和返回结构。"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from models.enums import SearchSource, SourceType

logger = logging.getLogger(__name__)


# === 统一返回结构 ===


class SearchResult(BaseModel):
    """搜索 Provider 统一返回结构。各 Provider 必须将原始响应转换为此格式。"""

    title: str
    url: str
    snippet: str = ""
    source_provider: SearchSource
    source_type: SourceType = SourceType.OTHER
    published_at: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    language: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


# === 统一异常 ===


class SearchProviderError(Exception):
    """搜索 Provider 统一异常。所有 Provider 内部错误必须转换为此异常抛出。"""

    def __init__(
        self,
        provider: str,
        message: str,
        status_code: int | None = None,
        raw_error: str = "",
    ):
        self.provider = provider
        self.message = message
        self.status_code = status_code
        self.raw_error = raw_error
        super().__init__(f"[{provider}] {message}")


# === Provider 健康状态 ===


class ProviderHealth(BaseModel):
    """Provider 健康检查结果。"""

    provider: str
    enabled: bool = True
    configured: bool = True
    reachable: bool | None = None
    error: str | None = None


# === 抽象基类 ===


class BaseSearchProvider(ABC):
    """搜索源抽象基类。所有搜索 Provider 必须继承此类。"""

    @property
    @abstractmethod
    def provider_name(self) -> SearchSource:
        """Provider 标识。"""

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """
        执行搜索。

        Args:
            query: 搜索关键词
            limit: 最大返回条数

        Returns:
            统一格式的搜索结果列表

        Raises:
            SearchProviderError: 搜索失败时抛出
        """

    async def health_check(self) -> bool:
        """检查 Provider 是否可用。默认返回 True，子类可覆盖。"""
        return True

    def _log_search_start(self, query: str, limit: int) -> None:
        logger.info(
            "provider_search_started provider=%s query=%s limit=%d",
            self.provider_name,
            query,
            limit,
        )

    def _log_search_done(self, query: str, count: int) -> None:
        logger.info(
            "provider_search_completed provider=%s query=%s results=%d",
            self.provider_name,
            query,
            count,
        )

    def _log_search_failed(self, query: str, error: str) -> None:
        logger.error(
            "provider_search_failed provider=%s query=%s error=%s",
            self.provider_name,
            query,
            error,
        )
