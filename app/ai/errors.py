"""AI 模块专用异常。"""


class AIError(Exception):
    """AI 调用基础异常。"""

    def __init__(self, message: str, provider: str = "", task: str = ""):
        self.message = message
        self.provider = provider
        self.task = task
        super().__init__(message)


class ParseError(AIError):
    """JSON 解析失败。"""

    def __init__(self, message: str, raw_output: str = ""):
        self.raw_output = raw_output
        super().__init__(message=message, task="parse")


class BudgetExceededError(AIError):
    """Token 预算超限。"""

    def __init__(self, message: str, used: int = 0, limit: int = 0):
        self.used = used
        self.limit = limit
        super().__init__(message=message, task="budget")


class LLMFallbackRequired(AIError):
    """LLM 调用失败且 require_llm=false，业务层应使用 fallback 策略。"""

    def __init__(self, task: str, fallback: str | None = None, reason: str = ""):
        self.fallback = fallback
        self.reason = reason
        super().__init__(message=f"LLM fallback required for '{task}': {reason}", task=task)


class LLMTaskFailed(AIError):
    """LLM 调用失败且 require_llm=true，无法降级。"""

    def __init__(self, task: str, reason: str = "", provider: str = ""):
        self.reason = reason
        super().__init__(message=f"LLM task failed: '{task}': {reason}", provider=provider, task=task)
