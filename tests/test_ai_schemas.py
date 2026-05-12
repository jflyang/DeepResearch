"""AI schemas 单元测试。"""

import pytest
from pydantic import ValidationError

from app.ai.budget import TokenBudget
from app.ai.errors import AIError, BudgetExceededError, ParseError
from app.ai.schemas import (
    Confidence,
    DocumentAnalysisOutput,
    EntityExtractionOutput,
    EntityType,
    ExpandedQueryItem,
    ExtractedEntity,
    LLMRequest,
    LLMResponse,
    QueryExpansionOutput,
    SourceHint,
    SourceReviewOutput,
    TaskConfig,
    TopicUnderstandingOutput,
)


# === Gateway 层模型测试 ===


class TestLLMRequest:
    def test_defaults(self) -> None:
        req = LLMRequest(task="test", prompt="hello")
        assert req.task == "test"
        assert req.prompt == "hello"
        assert req.temperature == 0.7
        assert req.max_tokens == 2048
        assert req.response_format == "text"
        assert req.model == ""
        assert req.metadata == {}

    def test_custom_values(self) -> None:
        req = LLMRequest(
            task="summarize",
            prompt="content",
            model="qwen2.5:7b",
            temperature=0.3,
            max_tokens=512,
            response_format="json",
            metadata={"source": "test"},
        )
        assert req.model == "qwen2.5:7b"
        assert req.temperature == 0.3
        assert req.metadata["source"] == "test"


class TestLLMResponse:
    def test_basic(self) -> None:
        resp = LLMResponse(task="test", content="result", model="mock")
        assert resp.content == "result"
        assert resp.tokens_used == 0
        assert resp.cached is False


class TestTaskConfig:
    def test_defaults(self) -> None:
        cfg = TaskConfig(name="my_task")
        assert cfg.name == "my_task"
        assert cfg.temperature == 0.7
        assert cfg.response_format == "text"


# === LLM 输出 Schema 测试 ===


class TestTopicUnderstandingOutput:
    def test_defaults(self) -> None:
        out = TopicUnderstandingOutput()
        assert out.mode == ""
        assert out.main_entity == ""
        assert out.language == "zh"
        assert out.aliases == []
        assert out.people == []
        assert out.suggested_focus == []

    def test_minimal_valid(self) -> None:
        out = TopicUnderstandingOutput(
            mode="person",
            main_entity="张三",
            normalized_topic="张三研究",
        )
        assert out.mode == "person"
        assert out.main_entity == "张三"

    def test_max_length_exceeded(self) -> None:
        with pytest.raises(ValidationError):
            TopicUnderstandingOutput(main_entity="x" * 201)


class TestExpandedQueryItem:
    def test_minimal(self) -> None:
        item = ExpandedQueryItem(query="test query")
        assert item.query == "test query"
        assert item.source_hint == SourceHint.general
        assert item.priority == 1

    def test_all_source_hints(self) -> None:
        for hint in SourceHint:
            item = ExpandedQueryItem(query="q", source_hint=hint)
            assert item.source_hint == hint

    def test_invalid_source_hint(self) -> None:
        with pytest.raises(ValidationError):
            ExpandedQueryItem(query="q", source_hint="invalid")  # type: ignore[arg-type]

    def test_priority_bounds(self) -> None:
        item = ExpandedQueryItem(query="q", priority=10)
        assert item.priority == 10
        with pytest.raises(ValidationError):
            ExpandedQueryItem(query="q", priority=0)
        with pytest.raises(ValidationError):
            ExpandedQueryItem(query="q", priority=11)

    def test_query_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ExpandedQueryItem(query="x" * 501)


class TestQueryExpansionOutput:
    def test_defaults(self) -> None:
        out = QueryExpansionOutput()
        assert out.queries == []

    def test_with_items(self) -> None:
        out = QueryExpansionOutput(queries=[
            ExpandedQueryItem(query="q1", purpose="探索", source_hint=SourceHint.web, priority=2),
            ExpandedQueryItem(query="q2"),
        ])
        assert len(out.queries) == 2
        assert out.queries[0].purpose == "探索"


class TestExtractedEntity:
    def test_minimal(self) -> None:
        e = ExtractedEntity(name="OpenAI", type=EntityType.company)
        assert e.name == "OpenAI"
        assert e.type == EntityType.company
        assert e.should_expand is False

    def test_all_entity_types(self) -> None:
        for t in EntityType:
            e = ExtractedEntity(name="x", type=t)
            assert e.type == t

    def test_invalid_entity_type(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEntity(name="x", type="unknown")  # type: ignore[arg-type]

    def test_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEntity(name="x" * 201, type=EntityType.person)


class TestEntityExtractionOutput:
    def test_defaults(self) -> None:
        out = EntityExtractionOutput()
        assert out.entities == []

    def test_with_entities(self) -> None:
        out = EntityExtractionOutput(entities=[
            ExtractedEntity(name="GPT-4", type=EntityType.product, should_expand=True),
        ])
        assert out.entities[0].should_expand is True


class TestSourceReviewOutput:
    def test_defaults(self) -> None:
        out = SourceReviewOutput()
        assert out.relevance_note == ""
        assert out.quality_warning is None
        assert out.should_download is False
        assert out.confidence == Confidence.medium

    def test_all_confidence_levels(self) -> None:
        for c in Confidence:
            out = SourceReviewOutput(confidence=c)
            assert out.confidence == c

    def test_invalid_confidence(self) -> None:
        with pytest.raises(ValidationError):
            SourceReviewOutput(confidence="very_high")  # type: ignore[arg-type]

    def test_minimal_valid(self) -> None:
        out = SourceReviewOutput(
            relevance_note="高度相关",
            likely_source_type="academic",
            reason_to_read="核心论文",
            should_download=True,
            confidence=Confidence.high,
        )
        assert out.should_download is True
        assert out.confidence == Confidence.high


class TestDocumentAnalysisOutput:
    def test_defaults(self) -> None:
        out = DocumentAnalysisOutput()
        assert out.summary == ""
        assert out.reason_to_read == ""
        assert out.key_points == []
        assert out.people == []
        assert out.places == []
        assert out.organizations == []
        assert out.concepts == []
        assert out.story_points == []
        assert out.gossip_or_unverified_claims == []
        assert out.verification_notes == []

    def test_minimal_valid(self) -> None:
        out = DocumentAnalysisOutput(
            summary="这是一篇关于AI的论文",
            key_points=["要点1"],
        )
        assert out.summary == "这是一篇关于AI的论文"
        assert len(out.key_points) == 1

    def test_summary_max_length(self) -> None:
        with pytest.raises(ValidationError):
            DocumentAnalysisOutput(summary="x" * 2001)

    def test_full_output(self) -> None:
        out = DocumentAnalysisOutput(
            summary="摘要",
            reason_to_read="重要参考",
            key_points=["点1", "点2"],
            people=["张三"],
            places=["北京"],
            organizations=["清华大学"],
            concepts=["深度学习"],
            story_points=["事件1"],
            gossip_or_unverified_claims=["未证实说法"],
            verification_notes=["需要核实"],
        )
        assert len(out.people) == 1
        assert out.organizations[0] == "清华大学"


# === Budget / Error 测试 ===


class TestTokenBudget:
    def test_consume(self) -> None:
        budget = TokenBudget(limit=100)
        budget.consume(50)
        assert budget.used == 50
        assert budget.remaining == 50
        assert not budget.exhausted

    def test_exceed(self) -> None:
        budget = TokenBudget(limit=100)
        budget.consume(80)
        with pytest.raises(BudgetExceededError):
            budget.consume(30)

    def test_reset(self) -> None:
        budget = TokenBudget(limit=100)
        budget.consume(50)
        budget.reset()
        assert budget.used == 0
        assert budget.remaining == 100


class TestErrors:
    def test_ai_error(self) -> None:
        err = AIError(message="fail", provider="ollama", task="gen")
        assert err.provider == "ollama"
        assert str(err) == "fail"

    def test_parse_error(self) -> None:
        err = ParseError(message="bad json", raw_output="abc")
        assert err.raw_output == "abc"
        assert err.task == "parse"

    def test_budget_exceeded_error(self) -> None:
        err = BudgetExceededError(message="over", used=150, limit=100)
        assert err.used == 150
        assert err.limit == 100
