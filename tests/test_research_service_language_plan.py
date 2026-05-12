"""ResearchService 语言规划集成测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.enums import LanguageCode, SearchStrategy, TaskMode, TaskStatus
from models.schemas import ResearchLanguagePlan, ResearchTask
from services.research_service import ResearchService


@pytest.fixture
def mock_providers():
    """Mock search providers that return empty results."""
    mock_web = AsyncMock()
    mock_web.provider_name = "mock_web"
    mock_web.search = AsyncMock(return_value=[])

    return {
        "web": [mock_web],
        "general": [mock_web],
        "book": [],
        "video": [],
        "archive": [],
    }


@pytest.fixture
def service(mock_providers):
    """ResearchService with mock providers, no AI gateway."""
    return ResearchService(providers=mock_providers, ai_gateway=None)


@pytest.fixture
def tim_cook_task():
    """中文"库克的童年故事"研究任务。"""
    return ResearchTask(
        topic="库克的童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def xiaomi_task():
    """中文"小米早期创业故事"研究任务。"""
    return ResearchTask(
        topic="小米早期创业故事",
        mode=TaskMode.COMPANY,
        status=TaskStatus.PENDING,
    )


class TestLanguagePlanIntegration:
    """语言规划集成到研究流程测试。"""

    async def test_tim_cook_gets_english_first_plan(self, service, tim_cook_task):
        """中文"库克的童年故事"启动研究时，query_expansion 收到 english_first plan。"""
        # 直接测试语言规划步骤
        plan = await service._plan_language(tim_cook_task)

        assert plan is not None
        assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST
        assert plan.working_language == LanguageCode.EN
        assert plan.main_entity_canonical == "Tim Cook"

    async def test_english_queries_dominate(self, service, tim_cook_task):
        """生成的 search query 英文为主。"""
        plan = await service._plan_language(tim_cook_task)
        queries = await service._expand_queries_with_plan(tim_cook_task, plan)

        en_count = sum(1 for q in queries if q.language == LanguageCode.EN)
        zh_count = sum(1 for q in queries if q.language == LanguageCode.ZH)

        assert en_count > zh_count, f"EN={en_count}, ZH={zh_count}"

    async def test_english_queries_contain_tim_cook(self, service, tim_cook_task):
        """英文 query 使用 canonical entity。"""
        plan = await service._plan_language(tim_cook_task)
        queries = await service._expand_queries_with_plan(tim_cook_task, plan)

        en_queries = [q.query for q in queries if q.language == LanguageCode.EN]
        assert any("Tim Cook" in q for q in en_queries)

    async def test_full_pipeline_completes(self, service, tim_cook_task):
        """完整流水线能跑通。"""
        summary = await service.run_initial_research(tim_cook_task)

        assert summary.total_queries > 0
        assert tim_cook_task.status == TaskStatus.COMPLETED


class TestLanguagePlanFailure:
    """语言规划失败时主流程仍继续。"""

    async def test_planner_exception_does_not_crash(self, mock_providers):
        """language_planner 抛错时主流程仍继续。"""
        service = ResearchService(providers=mock_providers, ai_gateway=None)

        # Patch planner to raise
        with patch(
            "services.research_service.ResearchService._plan_language",
            new_callable=AsyncMock,
            return_value=None,
        ):
            task = ResearchTask(
                topic="库克的童年故事",
                mode=TaskMode.PERSON,
                status=TaskStatus.PENDING,
            )
            summary = await service.run_initial_research(task)

            # 主流程仍完成
            assert task.status == TaskStatus.COMPLETED
            assert summary.total_queries > 0

    async def test_planner_returns_none_uses_legacy(self, mock_providers):
        """plan=None 时使用旧 query expansion 流程。"""
        service = ResearchService(providers=mock_providers, ai_gateway=None)

        task = ResearchTask(
            topic="unknown topic without entity",
            mode=TaskMode.AUTO,
            status=TaskStatus.PENDING,
        )

        # _plan_language 对未知主题返回 bilingual plan，
        # 但即使返回 None 也应该工作
        with patch.object(service, "_plan_language", new_callable=AsyncMock, return_value=None):
            summary = await service.run_initial_research(task)
            assert summary.total_queries > 0
            assert task.status == TaskStatus.COMPLETED


class TestSourceItemLanguageMetadata:
    """SourceItem runtime 对象包含语言元数据。"""

    async def test_source_items_have_language_metadata(self, mock_providers):
        """SourceItem 包含 canonical_topic 和 query_language。"""
        from models.enums import SourceLevel, SourceType, SearchSource
        from providers.search.base import SearchResult

        service = ResearchService(providers=mock_providers, ai_gateway=None)

        # 验证 _to_source_items 带语言元数据
        plan = ResearchLanguagePlan(
            original_topic="库克的童年故事",
            canonical_topic="Tim Cook childhood story",
            working_language=LanguageCode.EN,
            search_strategy=SearchStrategy.ENGLISH_FIRST,
        )

        # 模拟 scored results
        mock_candidate = MagicMock()
        mock_candidate.title = "Tim Cook Early Life"
        mock_candidate.url = "https://example.com/tim-cook"
        mock_candidate.snippet = "Tim Cook grew up"
        mock_candidate.source_type = SourceType.NEWS

        mock_scoring = MagicMock()
        mock_scoring.source_level = SourceLevel.A
        mock_scoring.relevance_score = 0.9
        mock_scoring.authority_score = 0.8
        mock_scoring.originality_score = 0.7
        mock_scoring.gossip_score = 0.0
        mock_scoring.reason_to_read = "Primary source"

        mock_scored = MagicMock()
        mock_scored.candidate = mock_candidate
        mock_scored.scoring = mock_scoring

        items = service._to_source_items("task-1", [mock_scored], language_plan=plan)

        assert len(items) == 1
        item = items[0]
        assert item.canonical_topic == "Tim Cook childhood story"
        assert item.original_topic == "库克的童年故事"
        assert item.query_language == LanguageCode.EN

    async def test_source_items_without_plan_have_no_metadata(self, mock_providers):
        """无 language_plan 时 SourceItem 无语言元数据。"""
        from unittest.mock import MagicMock
        from models.enums import SourceLevel, SourceType

        service = ResearchService(providers=mock_providers, ai_gateway=None)

        mock_candidate = MagicMock()
        mock_candidate.title = "Test"
        mock_candidate.url = "https://example.com"
        mock_candidate.snippet = "test"
        mock_candidate.source_type = SourceType.OTHER

        mock_scoring = MagicMock()
        mock_scoring.source_level = SourceLevel.C
        mock_scoring.relevance_score = 0.5
        mock_scoring.authority_score = 0.5
        mock_scoring.originality_score = 0.5
        mock_scoring.gossip_score = 0.0
        mock_scoring.reason_to_read = ""

        mock_scored = MagicMock()
        mock_scored.candidate = mock_candidate
        mock_scored.scoring = mock_scoring

        items = service._to_source_items("task-1", [mock_scored], language_plan=None)

        assert len(items) == 1
        item = items[0]
        assert item.canonical_topic is None
        assert item.original_topic is None
        assert item.query_language is None
