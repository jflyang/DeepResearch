"""LLMJsonParser 单元测试。"""

import pytest
from pydantic import BaseModel, Field

from app.ai.parser import LLMJsonParseError, LLMJsonSchemaError, parse_as, parse_json


# === parse_json 测试 ===


class TestParseJsonPure:
    def test_simple_object(self) -> None:
        result = parse_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_nested_object(self) -> None:
        result = parse_json('{"outer": {"inner": [1, 2]}, "flag": true}')
        assert result == {"outer": {"inner": [1, 2]}, "flag": True}

    def test_whitespace_around(self) -> None:
        result = parse_json('  \n  {"a": 1}  \n  ')
        assert result == {"a": 1}


class TestParseJsonFenced:
    def test_json_code_block(self) -> None:
        text = """Here is the result:
```json
{"name": "test", "score": 0.9}
```
"""
        result = parse_json(text)
        assert result == {"name": "test", "score": 0.9}

    def test_code_block_no_lang(self) -> None:
        text = """Result:
```
{"items": [1, 2]}
```
"""
        result = parse_json(text)
        assert result == {"items": [1, 2]}

    def test_multiline_json_in_block(self) -> None:
        text = """分析结果：
```json
{
  "mode": "person",
  "main_entity": "张三",
  "aliases": ["老张"]
}
```
以上是分析。"""
        result = parse_json(text)
        assert result["mode"] == "person"
        assert result["aliases"] == ["老张"]


class TestParseJsonEmbedded:
    def test_json_with_prefix_text(self) -> None:
        text = 'The analysis shows {"relevance": 0.8, "category": "tech"} as the result.'
        result = parse_json(text)
        assert result == {"relevance": 0.8, "category": "tech"}

    def test_json_with_explanation_before_and_after(self) -> None:
        text = """根据分析，结果如下：
{"summary": "这是摘要", "score": 0.7}
希望对你有帮助。"""
        result = parse_json(text)
        assert result["summary"] == "这是摘要"


class TestParseJsonErrors:
    def test_no_json_raises(self) -> None:
        with pytest.raises(LLMJsonParseError) as exc_info:
            parse_json("no json here at all")
        assert exc_info.value.raw_output == "no json here at all"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(LLMJsonParseError):
            parse_json("{invalid: json, missing quotes}")

    def test_array_only_raises(self) -> None:
        # parse_json 只返回 dict，纯数组不符合
        with pytest.raises(LLMJsonParseError):
            parse_json("[1, 2, 3]")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(LLMJsonParseError):
            parse_json("")


# === parse_as 测试 ===


class _SampleSchema(BaseModel):
    name: str
    score: float = 0.0
    tags: list[str] = Field(default_factory=list)


class _StrictSchema(BaseModel):
    required_field: str
    another_required: int


class TestParseAs:
    def test_valid_json_matches_schema(self) -> None:
        text = '{"name": "test", "score": 0.95, "tags": ["a", "b"]}'
        result = parse_as(text, _SampleSchema)
        assert result.name == "test"
        assert result.score == 0.95
        assert result.tags == ["a", "b"]

    def test_defaults_applied(self) -> None:
        text = '{"name": "minimal"}'
        result = parse_as(text, _SampleSchema)
        assert result.score == 0.0
        assert result.tags == []

    def test_fenced_json_with_schema(self) -> None:
        text = """```json
{"name": "fenced", "score": 1.0}
```"""
        result = parse_as(text, _SampleSchema)
        assert result.name == "fenced"


class TestParseAsSchemaError:
    def test_missing_required_field(self) -> None:
        text = '{"another_required": 42}'
        with pytest.raises(LLMJsonSchemaError) as exc_info:
            parse_as(text, _StrictSchema)
        assert exc_info.value.data == {"another_required": 42}

    def test_wrong_type(self) -> None:
        text = '{"required_field": "ok", "another_required": "not_int"}'
        with pytest.raises(LLMJsonSchemaError):
            parse_as(text, _StrictSchema)

    def test_parse_error_propagates(self) -> None:
        with pytest.raises(LLMJsonParseError):
            parse_as("not json", _SampleSchema)
