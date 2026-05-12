"""TopicUnderstandingService 单元测试。"""

from unittest.mock import AsyncMock

import pytest

from app.ai.errors import LLMFallbackRequired
from app.ai.schemas import TopicUnderstandingOutput
from app.services.topic_understanding_service import TopicUnderstandingService
from models.enums import TaskMode


@pytest.fixture
def mock_gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_gateway: AsyncMock) -> TopicUnderstandingService:
    return TopicUnderstandingService(ai_gateway=mock_gateway)


@pytest.fixture
def service_no_llm() -> TopicUnderstandingService:
    return TopicUnderstandingService(ai_gateway=None)


# === 用户指定 mode 不被覆盖 ===


class TestUserSelectedMode:
    @pytest.mark.asyncio
    async def test_person_mode_not_overridden_by_llm(
        self, service: TopicUnderstandingService, mock_gateway: AsyncMock
    ) -> None:
        # LLM 返回 mode=company，但用户选了 person
        mock_gateway.run_json = AsyncMock(return_value=TopicUnderstandingOutput(
            mode="company",
            main_entity="Elon Musk",
            normalized_topic="Elon Musk 研究",
            aliases=["马斯克"],
            people=["Elon Musk"],
            suggested_focus=["创业经历"],
        ))

        result = await service.analyze("Elon Musk", user_selected_mode=TaskMode.PERSON)
        assert result.mode == "person"
        # 但 entities 仍来自 LLM
        assert result.aliases == ["马斯克"]
        assert result.people == ["Elon Musk"]
        assert result.suggested_focus == ["创业经历"]

    @pytest.mark.asyncio
    async def test_event_mode_preserved(
        self, service: TopicUnderstandingService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=TopicUnderstandingOutput(
            mode="concept",
            main_entity="FTX",
        ))

        result = await service.analyze("FTX 崩盘", user_selected_mode=TaskMode.EVENT)
        assert result.mode == "event"

    @pytest.mark.asyncio
    async def test_user_mode_preserved_on_llm_failure(
        self, service: TopicUnderstandingService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=RuntimeError("timeout"))

        result = await service.analyze("Tesla", user_selected_mode=TaskMode.COMPANY)
        assert result.mode == "company"


# === auto + LLM 成功 ===


class TestAutoWithLLM:
    @pytest.mark.asyncio
    async def test_llm_determines_mode(
        self, service: TopicUnderstandingService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=TopicUnderstandingOutput(
            mode="event",
            main_entity="FTX 崩盘",
            normalized_topic="FTX 交易所崩盘事件",
            language="zh",
            people=["Sam Bankman-Fried"],
            organizations=["FTX", "Alameda Research"],
            concepts=["加密货币"],
        ))

        result = await service.analyze("FTX 崩盘", user_selected_mode=None)
        assert result.mode == "event"
        assert result.main_entity == "FTX 崩盘"
        assert "Sam Bankman-Fried" in result.people
        assert "FTX" in result.organizations

    @pytest.mark.asyncio
    async def test_auto_mode_uses_llm(
        self, service: TopicUnderstandingService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=TopicUnderstandingOutput(
            mode="person",
            main_entity="张三",
            normalized_topic="张三",
        ))

        result = await service.analyze("张三", user_selected_mode=TaskMode.AUTO)
        assert result.mode == "person"

    @pytest.mark.asyncio
    async def test_llm_output_fields_preserved(
        self, service: TopicUnderstandingService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(return_value=TopicUnderstandingOutput(
            mode="concept",
            main_entity="深度学习",
            normalized_topic="深度学习技术",
            language="zh",
            aliases=["Deep Learning", "DL"],
            concepts=["神经网络", "反向传播"],
            suggested_focus=["发展历史", "关键人物"],
        ))

        result = await service.analyze("深度学习", user_selected_mode=TaskMode.AUTO)
        assert result.aliases == ["Deep Learning", "DL"]
        assert "神经网络" in result.concepts
        assert "发展历史" in result.suggested_focus


# === LLM 失败 fallback 规则 ===


class TestRuleFallback:
    @pytest.mark.asyncio
    async def test_event_keywords(self, service_no_llm: TopicUnderstandingService) -> None:
        result = await service_no_llm.analyze("某公司收购案争议", user_selected_mode=None)
        assert result.mode == "event"

    @pytest.mark.asyncio
    async def test_company_keywords(self, service_no_llm: TopicUnderstandingService) -> None:
        result = await service_no_llm.analyze("某创业公司融资历程", user_selected_mode=None)
        assert result.mode == "company"

    @pytest.mark.asyncio
    async def test_concept_keywords(self, service_no_llm: TopicUnderstandingService) -> None:
        result = await service_no_llm.analyze("Transformer 模型起源", user_selected_mode=None)
        assert result.mode == "concept"

    @pytest.mark.asyncio
    async def test_default_person(self, service_no_llm: TopicUnderstandingService) -> None:
        result = await service_no_llm.analyze("张三", user_selected_mode=None)
        assert result.mode == "person"

    @pytest.mark.asyncio
    async def test_fallback_on_exception(
        self, service: TopicUnderstandingService, mock_gateway: AsyncMock
    ) -> None:
        mock_gateway.run_json = AsyncMock(side_effect=LLMFallbackRequired(
            task="topic_understanding", reason="parse failed"
        ))

        result = await service.analyze("某诉讼事件", user_selected_mode=None)
        assert result.mode == "event"
        assert result.main_entity == "某诉讼事件"

    @pytest.mark.asyncio
    async def test_fallback_returns_basic_output(
        self, service_no_llm: TopicUnderstandingService
    ) -> None:
        result = await service_no_llm.analyze("量子计算", user_selected_mode=TaskMode.AUTO)
        assert isinstance(result, TopicUnderstandingOutput)
        assert result.main_entity == "量子计算"
        assert result.normalized_topic == "量子计算"
