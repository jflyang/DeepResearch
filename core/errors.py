"""统一错误结构 - 所有外部调用失败都使用此结构。"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProviderError(BaseModel):
    """Provider 调用失败的统一错误。"""

    provider: str
    operation: str
    message: str
    status_code: int | None = None
    raw_error: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)

    def __str__(self) -> str:
        return f"[{self.provider}:{self.operation}] {self.message}"


class ResearchError(Exception):
    """业务层异常。"""

    def __init__(self, message: str, step: str = "", details: str = ""):
        self.message = message
        self.step = step
        self.details = details
        super().__init__(message)
