"""LLM Gateway 集成测试 - 使用 MockLLMProvider，不访问真实网络。"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.errors import LLMFallbackRequired, LLMTaskFailed
from app.ai.gateway import AIGateway
from app.ai.prompts import PromptStore
from app.ai.router import LLMRouter
from app.ai.schemas import (
    Confidence,
    DocumentAnalysisOutput,
    ExpandedQueryItem,
    QueryExpansionOutput,
    SourceHint,
    SourceReviewOutput,
)
from app.ai.tasks import LLMTaskConfig, reset_config_cache
from app.providers.llm.base import BaseLLMProvider, LLMRequest, LLMResponse, ProviderHealth
from app.services.document_analysis_service import DocumentAnalysisService, ExtractedDocument
from app.services.scoring_service import LLMScoringService
from models.enums import (
    DownloadStatus,
    SearchSource,
    SourceLevel,
    SourceType,
    TaskMode,
)
from models.schemas import SourceItem
from services.dedupe_service import DedupedSourceCandidate
from services.query_expansion_service import QueryExpansionService


# === Mock Provider ===


class _IntegrationMockProvider(BaseLLMProvider):
    """集成测试用 Mock Provider，根据 prompt 内容返回不同 JSON。"""

    def __init__(self) -> None:
        self._responses: dict[str, str] = {}

    def set_response(self, keyword: str, json_text: str) -> None:
        self._responses[keyword] = json_text

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        # 根据 prompt 中的关键词匹配响应
        for keyword, response_text in self._responses.items():
            if keyword in request.user_prompt:
                return LLMResponse(
                    text=response_text,
                    provider="mock",
                    model=request.model,
                    latency_ms=1,
                    input_chars=len(request.user_prompt),
                    output_chars=len(response_text),
                )
        # 默认返回空 JSON
        return LLMResponse(
            text="{}",
            provider="mock",
            model=request.model,
            latency_ms=1,
            input_chars=len(request.user_prompt),
            output_chars=2,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="mock", reachable=True, latency_ms=0)


# === Fixtures ===


TEMPLATE_DIR = Path("config/prompt_templates")


@pytest.fixture(autouse=True)
def _reset():
    reset_config_cache()
    yield
    reset_config_cache()


@pytest.fixture
def mock_provider() -> _IntegrationMockProvider:
    return _IntegrationMockProvider()


@pytest.fixture
def gateway(mock_provider: _IntegrationMockProvider) -> AIGateway:
    """构建使用 mock provider 的 AIGateway。"""
    router = LLMRouter.__new__(LLMRouter)
    router._providers_config = {}
    router._config_path = Path("/dev/null")
    router.get_provider = lambda name: mock_provider  # type: ignore[assignment]
    prompt_store = PromptStore(template_dir=TEMPLATE_DIR)
    return AIGateway(router=router, prompt_store=prompt_store)


def _patch_task_config(config: LLMTaskConfig):
    return patch("app.ai.gateway.load_llm_task_config", return_value=config)


def _default_config(**overrides) -> LLMTaskConfig:
    defaults = dict(
        provider="mock",
        model="mock",
        temperature=0.3,
        max_input_chars=6000,
        max_output_tokens=1000,
        timeout_seconds=30,
        json_required=True,
        retry_on_parse_error=True,
        max_retries=1,
        require_llm=False,
    )
    defaults.update(overrides)
    return LLMTaskConfig(**defaults)


# === 1. Query Expansion: AIGateway.run_json → QueryExpansionOutput ===


class TestQueryExpansionIntegration:
    @pytest.mark.asyncio
    async def test_gateway_returns_query_expansion_output(
        self, gateway: AIGateway, mock_provider: _IntegrationMockProvider
    ) -> None:
        mock_provider.set_response("搜索查询", '{"queries": [{"query": "量子计算最新进展", "purpose": "recent", "source_hint": "web", "priority": 3}]}')

        with _patch_task_config(_default_config()):
            result = await gateway.run_json(
                task_name="query_expansion",
                payload={"topic": "量子计算", "context": "", "num_queries": 5},
                output_schema=QueryExpansionOutput,
            )

        assert isinstance(result, QueryExpansionOutput)
        assert len(result.queries) == 1
        assert result.queries[0].query == "量子计算最新进展"


# === 2. QueryExpansionService 合并 LLM + 规则 ===


class TestQueryExpansionServiceIntegration:
    @pytest.mark.asyncio
    async def test_merges_llm_and_rule_queries(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        mock_provider.set_response("搜索查询", '{"queries": [{"query": "quantum computing 2024 breakthroughs", "purpose": "recent", "source_hint": "web", "priority": 5}]}')

        service = QueryExpansionService(ai_gateway=gateway)

        with _patch_task_config(_default_config()):
            results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)

        queries = [r.query for r in results]
        # LLM query 存在
        assert "quantum computing 2024 breakthroughs" in queries
        # 规则 query 也存在
        assert "quantum computing origin" in queries

    @pytest.mark.asyncio
    async def test_deduplicates_merged_queries(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        # LLM 返回和规则重复的 query
        mock_provider.set_response("搜索查询", '{"queries": [{"query": "quantum computing origin", "purpose": "llm", "source_hint": "web", "priority": 8}]}')

        service = QueryExpansionService(ai_gateway=gateway)

        with _patch_task_config(_default_config()):
            results = await service.expand("quantum computing", mode=TaskMode.CONCEPT)

        queries_lower = [r.query.lower() for r in results]
        assert len(queries_lower) == len(set(queries_lower))


# === 3. SourceReview: LLM 输出 reason_to_read ===


class TestSourceReviewIntegration:
    @pytest.mark.asyncio
    async def test_llm_reason_to_read_applied(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        mock_provider.set_response("评估", '{"relevance_note": "高度相关", "reason_to_read": "核心参考论文", "confidence": "high"}')

        service = LLMScoringService(ai_gateway=gateway)
        candidate = DedupedSourceCandidate(
            normalized_url="https://arxiv.org/abs/123",
            url="https://arxiv.org/abs/123",
            title="Research Paper",
            snippet="A comprehensive study on quantum computing.",
            source_providers=[SearchSource.TAVILY],
            source_type=SourceType.ACADEMIC,
            published_at="2024-01-01",
        )

        with _patch_task_config(_default_config()):
            result = await service.score_with_review(candidate, topic="quantum computing")

        assert "核心参考论文" in result.scoring.reason_to_read


# === 4. DocumentAnalysisService: summary + story_points ===


class TestDocumentAnalysisIntegration:
    @pytest.mark.asyncio
    async def test_returns_summary_and_story_points(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        mock_provider.set_response("文档内容", '{"summary": "本文介绍了量子计算的发展", "story_points": ["1982年Feynman提出概念", "2019年量子优越性"], "key_points": ["量子比特"], "people": ["Feynman"]}')

        service = DocumentAnalysisService(ai_gateway=gateway)
        doc = ExtractedDocument(
            url="https://example.com/article",
            title="量子计算综述",
            content="文档内容：量子计算是一种利用量子力学原理进行计算的技术。",
            word_count=100,
        )

        with _patch_task_config(_default_config(max_input_chars=10000)):
            result = await service.analyze(doc, topic="量子计算")

        assert result.summary == "本文介绍了量子计算的发展"
        assert "1982年Feynman提出概念" in result.story_points
        assert "2019年量子优越性" in result.story_points
        assert "Feynman" in result.people


# === 5. Fallback 分支 ===


class TestFallbackBranches:
    @pytest.mark.asyncio
    async def test_query_expansion_fallback_on_bad_json(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        # 返回无效 JSON
        mock_provider.set_response("搜索查询", "not valid json at all")

        service = QueryExpansionService(ai_gateway=gateway)

        with _patch_task_config(_default_config()):
            results = await service.expand("test topic", mode=TaskMode.CONCEPT)

        # 应该 fallback 到规则版
        queries = [r.query for r in results]
        assert "test topic origin" in queries
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_source_review_fallback_on_error(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        # 返回无法解析为 SourceReviewOutput 的内容
        mock_provider.set_response("评估", "completely broken output")

        service = LLMScoringService(ai_gateway=gateway)
        candidate = DedupedSourceCandidate(
            normalized_url="https://example.com",
            url="https://example.com",
            title="Test",
            snippet="test snippet content here",
            source_providers=[SearchSource.BRAVE],
            source_type=SourceType.NEWS,
        )

        with _patch_task_config(_default_config()):
            result = await service.score_with_review(candidate, topic="test")

        # 应该返回规则评分（不崩溃）
        assert result.scoring is not None
        assert result.scoring.source_level is not None

    @pytest.mark.asyncio
    async def test_document_analysis_fallback_on_error(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        mock_provider.set_response("文档内容", "{invalid json")

        service = DocumentAnalysisService(ai_gateway=gateway)
        doc = ExtractedDocument(
            url="https://example.com",
            title="Test",
            content="文档内容 test content",
            word_count=10,
        )

        with _patch_task_config(_default_config()):
            result = await service.analyze(doc, topic="test")

        # 应该返回空对象
        assert result.summary == ""
        assert result.key_points == []

    @pytest.mark.asyncio
    async def test_require_llm_true_raises_on_failure(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        mock_provider.set_response("搜索查询", "broken")

        config = _default_config(require_llm=True, retry_on_parse_error=False, max_retries=0)
        with _patch_task_config(config):
            with pytest.raises(LLMTaskFailed):
                await gateway.run_json(
                    task_name="query_expansion",
                    payload={"topic": "test", "context": "", "num_queries": 3},
                    output_schema=QueryExpansionOutput,
                )

    @pytest.mark.asyncio
    async def test_require_llm_false_raises_fallback_required(self, gateway: AIGateway, mock_provider: _IntegrationMockProvider) -> None:
        mock_provider.set_response("搜索查询", "broken")

        config = _default_config(require_llm=False, retry_on_parse_error=False, max_retries=0, fallback="rule_based")
        with _patch_task_config(config):
            with pytest.raises(LLMFallbackRequired) as exc_info:
                await gateway.run_json(
                    task_name="query_expansion",
                    payload={"topic": "test", "context": "", "num_queries": 3},
                    output_schema=QueryExpansionOutput,
                )
            assert exc_info.value.fallback == "rule_based"

    @pytest.mark.asyncio
    async def test_no_gateway_query_expansion_uses_rules(self) -> None:
        service = QueryExpansionService(ai_gateway=None)
        results = await service.expand("AI", mode=TaskMode.CONCEPT)
        assert len(results) > 0
        assert "AI origin" in [r.query for r in results]

    @pytest.mark.asyncio
    async def test_no_gateway_document_analysis_returns_empty(self) -> None:
        service = DocumentAnalysisService(ai_gateway=None)
        doc = ExtractedDocument(url="x", title="t", content="c", word_count=1)
        result = await service.analyze(doc, topic="t")
        assert result.summary == ""

    @pytest.mark.asyncio
    async def test_no_gateway_scoring_uses_rules(self) -> None:
        service = LLMScoringService(ai_gateway=None)
        candidate = DedupedSourceCandidate(
            normalized_url="https://arxiv.org/abs/1",
            url="https://arxiv.org/abs/1",
            title="Paper",
            snippet="content",
            source_providers=[SearchSource.TAVILY],
            source_type=SourceType.ACADEMIC,
        )
        result = await service.score_with_review(candidate, topic="test")
        assert result.scoring.source_level is not None
