"""从 LLM 输出中提取结构化 JSON 数据。"""

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMJsonParseError(Exception):
    """JSON 提取/解析失败。"""

    def __init__(self, message: str, raw_output: str = "") -> None:
        self.raw_output = raw_output
        super().__init__(message)


class LLMJsonSchemaError(Exception):
    """JSON 结构不符合目标 schema。"""

    def __init__(self, message: str, data: dict[str, Any] | None = None) -> None:
        self.data = data
        super().__init__(message)


def extract_json(text: str) -> Any:
    """兼容旧接口：提取 JSON 对象或数组。"""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", stripped, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass
    for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        match = re.search(pattern, stripped)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    raise LLMJsonParseError(message="No valid JSON found in LLM output", raw_output=text)


def parse_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取第一个 JSON 对象。

    支持：纯 JSON、```json code block、混合文本中嵌入的 JSON。
    """
    stripped = text.strip()

    # 尝试直接解析
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 尝试从 fenced code block 提取
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", stripped, re.DOTALL)
    if code_block:
        try:
            result = json.loads(code_block.group(1).strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 尝试匹配第一个 { ... }
    match = re.search(r"\{[\s\S]*\}", stripped)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise LLMJsonParseError(
        message="No valid JSON object found in LLM output",
        raw_output=text,
    )


def parse_as(text: str, schema: type[T]) -> T:
    """从 LLM 输出中提取 JSON 并校验为指定 Pydantic schema。"""
    data = parse_json(text)
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        raise LLMJsonSchemaError(
            message=f"Schema validation failed: {e.error_count()} error(s)",
            data=data,
        ) from e
