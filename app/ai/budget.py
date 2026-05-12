"""Token 预算与输入截断。"""

from dataclasses import dataclass, field

from app.ai.errors import BudgetExceededError

_TRUNCATION_MARKER = "\n\n[...TRUNCATED...]\n\n"


@dataclass
class TokenBudget:
    """追踪单次研究任务的 token 消耗。"""

    limit: int = 100_000
    used: int = field(default=0, init=False)

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def consume(self, tokens: int) -> None:
        """消耗 token，超限时抛出异常。"""
        if self.used + tokens > self.limit:
            raise BudgetExceededError(
                message=f"Token budget exceeded: {self.used + tokens}/{self.limit}",
                used=self.used + tokens,
                limit=self.limit,
            )
        self.used += tokens

    def reset(self) -> None:
        self.used = 0


def apply_input_budget(text: str, max_input_chars: int) -> str:
    """截断输入文本以满足字符预算。

    策略：保留前 70%，保留后 30%，中间插入截断标记。
    """
    if len(text) <= max_input_chars:
        return text

    usable = max_input_chars - len(_TRUNCATION_MARKER)
    if usable <= 0:
        return text[:max_input_chars]

    head_size = int(usable * 0.7)
    tail_size = usable - head_size

    head = text[:head_size]
    tail = text[-tail_size:] if tail_size > 0 else ""
    return head + _TRUNCATION_MARKER + tail
