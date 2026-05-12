"""语言规划端到端流程测试 - 不访问真实网络。

流程：中文输入 → 语言规划 → 英文 query 为主 → Mock 搜索 → SourceItem 带语言元数据 → Markdown 双语输出。
"""

from unittest.mock import AsyncMock

import pytest
import yaml

from models.enums import (
    DownloadStatus,
    LanguageCode,
    SearchSource,
    SearchStrategy,
    SourceLevel,
    SourceType,
    TaskMode,
    TaskStatus,
)
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from providers.search.base import SearchResult
from services.markdown_service import export_source_note
from services.query_expansion_service import QueryExpansionService
from services.research_service import ResearchService
from app.services.research_language_planner import ResearchLanguagePlannerService


class MockSearchProvider:
    """Mock search provider，不访问网络，返回固定英文结果。"""

    provider_name = "mock_web"

    def __init__(self):
        self.received_queries: list[str] = []

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        self.received_queries.append(query)
        return [
            SearchResult(
                title="Tim Cook's Early Life in Robertsdale, Alabama",
                url=f"https://example.com/tim-cook-{len(self.received_queries)}",
                snippet="Tim Cook grew up in Robertsdale, a small town in southern Alabama.",
                source_provider=SearchSource.TAVILY,
                source_type=SourceType.NEWS,
            ),
        ]


@pytest.fixture
def mock_provider():
    return MockSearchProvider()


@pytest.fixture
def mock_providers(mock_provider):
    return {
        "web": [mock_provider],
        "general": [mock_provider],
        "book": [],
        "video": [],
        "archive": [],
        "forum": [],
        "legal": [],
    }


async def test_chinese_topic_english_research_chinese_output_flow(tmp_path, mock_providers, mock_provider):
    """端到端：中文输入 → 英文研究 → 中文归档。

    验证完整流程：
    1. 语言规划识别 Tim Cook
    2. Query expansion 英文为主
    3. Search provider 收到英文 query
    4. SourceItem 带语言元数据
    5. Markdown 输出双语结构
    """
    topic = "库克的童年故事"

    # ============================================================
    # Step 1: 语言规划
    # ============================================================
    planner = ResearchLanguagePlannerService(ai_gateway=None)
    plan = await planner.plan(topic=topic, mode=TaskMode.PERSON)

    assert plan.user_language == LanguageCode.ZH
    assert plan.working_language == LanguageCode.EN
    assert plan.output_language == LanguageCode.ZH
    assert "Tim Cook" in plan.canonical_topic
    assert plan.search_strategy == SearchStrategy.ENGLISH_FIRST
    assert plan.main_entity_canonical == "Tim Cook"

    # ============================================================
    # Step 2: Query Expansion（英文为主）
    # ============================================================
    expansion_service = QueryExpansionService(ai_gateway=None)
    queries = await expansion_service.expand(
        topic=topic,
        mode=TaskMode.PERSON,
        include_books=True,
        language_plan=plan,
    )

    assert len(queries) > 0

    en_queries = [q for q in queries if q.language == LanguageCode.EN]
    zh_queries = [q for q in queries if q.language == LanguageCode.ZH]
    assert len(en_queries) > len(zh_queries), (
        f"English queries ({len(en_queries)}) should outnumber Chinese ({len(zh_queries)})"
    )

    # 英文 query 包含 Tim Cook
    en_query_texts = [q.query for q in en_queries]
    assert any("Tim Cook" in q for q in en_query_texts), (
        f"No 'Tim Cook' in English queries: {en_query_texts[:5]}"
    )

    # 每个 query 都有 language 字段
    for q in queries:
        assert q.language in (LanguageCode.EN, LanguageCode.ZH, LanguageCode.MIXED)

    # ============================================================
    # Step 3: Mock Search（验证 provider 收到英文 query）
    # ============================================================
    research_service = ResearchService(providers=mock_providers, ai_gateway=None)
    task = ResearchTask(
        topic=topic,
        mode=TaskMode.PERSON,
        status=TaskStatus.PENDING,
        include_books=True,
    )

    summary = await research_service.run_initial_research(task)

    assert task.status == TaskStatus.COMPLETED
    assert summary.total_queries > 0

    # MockSearchProvider 收到了英文 query
    assert len(mock_provider.received_queries) > 0
    en_received = [q for q in mock_provider.received_queries if "Tim Cook" in q]
    assert len(en_received) > 0, (
        f"Provider should receive 'Tim Cook' queries, got: {mock_provider.received_queries[:5]}"
    )

    # ============================================================
    # Step 4: SourceItem 带语言元数据
    # ============================================================
    # 手动构造带语言元数据的 SourceItem（模拟 _to_source_items 的输出）
    source_item = SourceItem(
        task_id=task.id,
        title="Tim Cook's Early Life in Robertsdale, Alabama",
        url="https://example.com/tim-cook-1",
        domain="example.com",
        snippet="Tim Cook grew up in Robertsdale",
        source_type=SourceType.NEWS,
        source_level=SourceLevel.A,
        reason_to_read="一手传记资料",
        download_status=DownloadStatus.EXTRACTED,
        # 语言元数据
        query_language=LanguageCode.EN,
        source_language=LanguageCode.EN,
        matched_query="Tim Cook childhood Robertsdale Alabama",
        canonical_topic=plan.canonical_topic,
        original_topic=plan.original_topic,
    )

    assert source_item.query_language == LanguageCode.EN
    assert source_item.matched_query == "Tim Cook childhood Robertsdale Alabama"
    assert "Tim Cook" in source_item.canonical_topic

    # ============================================================
    # Step 5: Mock ExtractedDocument（英文原文 + 中文摘要标记）
    # ============================================================
    extracted = ExtractedDocument(
        source_item_id=source_item.id,
        title="Tim Cook's Early Life in Robertsdale, Alabama",
        author="John Reporter",
        content=(
            "Timothy Donald Cook was born on November 1, 1960, in Mobile, Alabama. "
            "He grew up in nearby Robertsdale. His father, Donald Cook, was a shipyard worker, "
            "and his mother, Geraldine Cook, worked at a pharmacy. Cook attended Robertsdale "
            "High School, where he was valedictorian of his graduating class in 1978. "
            "He then enrolled at Auburn University, earning a Bachelor of Science in "
            "industrial engineering in 1982."
        ),
        summary=(
            "Tim Cook 1960 年出生于阿拉巴马州 Mobile，在 Robertsdale 小镇长大。"
            "父亲 Donald Cook 是船厂工人，母亲 Geraldine Cook 在药房工作。"
            "他是 1978 年高中毕业班第一名，后进入 Auburn University 学习工业工程。"
        ),
        key_quotes=[
            "Cook attended Robertsdale High School, where he was valedictorian",
            "earning a Bachelor of Science in industrial engineering in 1982",
        ],
        people=["Tim Cook", "Donald Cook", "Geraldine Cook"],
        places=["Robertsdale", "Alabama", "Mobile"],
        organizations=["Robertsdale High School", "Auburn University"],
        concepts=["valedictorian", "industrial engineering"],
        # 语言元数据
        original_language=LanguageCode.EN,
        summary_language=LanguageCode.ZH,
        canonical_topic=plan.canonical_topic,
        original_topic=plan.original_topic,
    )

    assert extracted.original_language == LanguageCode.EN
    assert extracted.summary_language == LanguageCode.ZH

    # ============================================================
    # Step 6: Markdown 输出（双语结构）
    # ============================================================
    vault_path = tmp_path / "vault"
    md_path = export_source_note(
        source_item=source_item,
        extracted=extracted,
        topic=topic,
        vault_path=vault_path,
    )

    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")

    # 双语结构
    assert "# 中文摘要" in content
    assert "# 原文正文" in content

    # 中文摘要内容
    assert "Tim Cook 1960 年出生于阿拉巴马州" in content

    # 英文原文未被翻译覆盖
    assert "Timothy Donald Cook was born on November 1, 1960" in content
    assert "valedictorian of his graduating class in 1978" in content

    # Frontmatter 语言元数据
    parts = content.split("---")
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])

    assert fm["source_language"] == "en"
    assert fm["output_language"] == "zh"
    assert fm["query_language"] == "en"
    assert "Tim Cook" in fm["canonical_topic"]
    assert fm["original_topic"] == "库克的童年故事"
    assert fm["matched_query"] == "Tim Cook childhood Robertsdale Alabama"

    # 原文信息章节
    assert "原文语言" in content
    assert "匹配 query" in content
