"""端到端集成测试 - 不依赖真实 API，使用 Mock Provider 和本地 fixture。"""

import pytest

from models.enums import (
    DownloadStatus,
    SearchSource,
    SourceLevel,
    SourceType,
    TaskMode,
    TaskStatus,
)
from models.schemas import SourceItem
from providers.extraction.base import BaseExtractor, ExtractedContent
from providers.search.base import BaseSearchProvider, SearchResult
from services.dedupe_service import dedupe_results
from services.extraction_service import ExtractionService
from services.markdown_service import export_research_index, export_source_note
from services.query_expansion_service import expand_queries
from services.research_service import CreateResearchTaskRequest, ResearchService
from services.result_classification_service import classify_results
from services.scoring_service import score_candidates


# === Mock Providers ===


class MockSearchProvider(BaseSearchProvider):
    """返回 3 条固定结果的 Mock Provider。"""

    def __init__(self):
        self._results = [
            SearchResult(
                title="SEC Filing: Tesla 10-K Annual Report",
                url="https://www.sec.gov/cgi-bin/browse-edgar?company=tesla",
                snippet="Annual report filed with the Securities and Exchange Commission "
                "containing comprehensive financial data and risk factors for Tesla Inc.",
                source_provider=SearchSource.TAVILY,
                source_type=SourceType.GOVERNMENT,
            ),
            SearchResult(
                title="Elon Musk Biography by Walter Isaacson",
                url="https://books.google.com/books?id=musk-bio-2023",
                snippet="by Walter Isaacson — A comprehensive biography covering Elon Musk's "
                "life from childhood in South Africa to leading Tesla and SpaceX.",
                source_provider=SearchSource.GOOGLE_BOOKS,
                source_type=SourceType.BOOK,
            ),
            SearchResult(
                title="Elon Musk personal life rumors and dating history",
                url="https://www.reddit.com/r/celebrity/comments/musk-gossip",
                snippet="Discussion thread about Elon Musk's relationship controversies "
                "and personal life rumors from various tabloid sources.",
                source_provider=SearchSource.BRAVE,
                source_type=SourceType.FORUM,
            ),
        ]

    @property
    def provider_name(self) -> SearchSource:
        return SearchSource.TAVILY

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return self._results


class MockExtractor(BaseExtractor):
    """返回固定提取结果的 Mock Extractor。"""

    @property
    def name(self) -> str:
        return "mock"

    async def extract(self, url: str) -> ExtractedContent:
        return ExtractedContent(
            title="Extracted: SEC Tesla Filing",
            author="SEC EDGAR",
            published_at="2024-03-15",
            source_url=url,
            text=(
                "Tesla, Inc. Annual Report 2024.\n\n"
                "Risk Factors: The company faces significant challenges in manufacturing "
                "and supply chain management. Elon Musk's leadership style has been both "
                "praised and criticized.\n\n"
                "The company was founded in 2003 by Martin Eberhard and Marc Tarpenning. "
                "Elon Musk joined as chairman in 2004 and became CEO in 2008.\n\n"
                "In 2008, Tesla faced a severe crisis and nearly went bankrupt during the "
                "financial downturn. The company survived through emergency funding.\n\n"
                "Key competitors include Rivian, Lucid Motors, and traditional automakers "
                "like Ford and GM entering the EV market."
            ),
            metadata={"source": "sec.gov"},
            success=True,
        )


# === Integration Test ===


@pytest.mark.asyncio
async def test_research_flow_with_mock_providers(tmp_path):
    """
    端到端集成测试：
    1. 创建任务
    2. 查询扩展
    3. 搜索（Mock）
    4. 去重
    5. 评分
    6. 分类
    7. 正文提取（Mock）
    8. Markdown 导出
    9. 验证文件存在
    """
    # --- 1. 创建任务 ---
    providers = {
        "web": [MockSearchProvider()],
        "general": [MockSearchProvider()],
        "book": [MockSearchProvider()],
        "video": [],
        "archive": [],
    }
    service = ResearchService(providers=providers, max_concurrency=3)

    request = CreateResearchTaskRequest(
        topic="Elon Musk",
        mode=TaskMode.PERSON,
        include_books=True,
        include_gossip=True,
        include_video=False,
    )
    task = service.create_task(request)
    assert task.status == TaskStatus.PENDING
    assert task.topic == "Elon Musk"

    # --- 2. 查询扩展 ---
    expanded = expand_queries(
        topic=task.topic,
        mode=task.mode,
        include_books=task.include_books,
        include_gossip=task.include_gossip,
    )
    assert len(expanded) > 5
    task.expanded_queries = [q.query for q in expanded]

    # --- 3. 搜索 ---
    mock_provider = MockSearchProvider()
    raw_results = await mock_provider.search("Elon Musk")
    assert len(raw_results) == 3

    # --- 4. 去重 ---
    deduped = dedupe_results(raw_results)
    assert len(deduped) == 3  # 3 unique URLs

    # --- 5. 评分 ---
    scored = score_candidates(deduped, topic="Elon Musk")
    assert len(scored) == 3

    # 验证排序：sec.gov 应排在前面
    levels = [s.scoring.source_level for s in scored]
    assert SourceLevel.S in levels or SourceLevel.A in levels

    # 验证 sec.gov 得分高于 reddit
    sec_score = next(s for s in scored if "sec.gov" in s.candidate.url)
    reddit_score = next(s for s in scored if "reddit.com" in s.candidate.url)
    assert sec_score.final_score > reddit_score.final_score

    # --- 6. 转换为 SourceItem 并分类 ---
    source_items: list[SourceItem] = []
    for s in scored:
        item = SourceItem(
            task_id=task.id,
            title=s.candidate.title,
            url=s.candidate.url,
            domain=s.candidate.url.split("//")[1].split("/")[0],
            snippet=s.candidate.snippet,
            source_type=s.candidate.source_type,
            source_level=s.scoring.source_level,
            relevance_score=s.scoring.relevance_score,
            authority_score=s.scoring.authority_score,
            originality_score=s.scoring.originality_score,
            gossip_score=s.scoring.gossip_score,
            reason_to_read=s.scoring.reason_to_read,
            download_status=DownloadStatus.PENDING,
        )
        source_items.append(item)

    classified = classify_results(source_items, mode=TaskMode.PERSON)
    assert len(classified) > 0
    # 应有多个分类
    assert any("必读" in cat or "官方" in cat for cat in classified.keys())

    # --- 7. 正文提取 ---
    extractor = MockExtractor()
    extraction_service = ExtractionService(extractor=extractor)

    # 提取第一条（sec.gov）
    sec_item = next(i for i in source_items if "sec.gov" in i.url)
    extracted_doc = await extraction_service.extract_source(sec_item)

    assert sec_item.download_status == DownloadStatus.EXTRACTED
    assert len(extracted_doc.content) > 0
    assert "Tesla" in extracted_doc.content

    # 手动填充 NER 字段（MVP 中由 LLM 或规则填充）
    extracted_doc.people = ["Elon Musk", "Martin Eberhard"]
    extracted_doc.organizations = ["Tesla", "SpaceX", "Rivian"]
    extracted_doc.concepts = ["electric vehicles", "EV market"]
    extracted_doc.places = ["South Africa"]
    extracted_doc.key_quotes = ["nearly went bankrupt during the financial downturn"]

    # --- 8. Markdown 导出 ---
    vault_path = tmp_path / "vault"

    # 导出单篇笔记
    note_path = export_source_note(
        source_item=sec_item,
        extracted=extracted_doc,
        topic="Elon Musk",
        vault_path=vault_path,
    )
    assert note_path.exists()
    assert note_path.suffix == ".md"
    assert sec_item.download_status == DownloadStatus.EXPORTED

    # 验证笔记内容
    note_content = note_path.read_text(encoding="utf-8")
    assert "---" in note_content  # frontmatter
    assert "Tesla" in note_content
    assert "# 正文" in note_content
    assert "sec.gov" in note_content

    # 导出研究索引
    task.status = TaskStatus.COMPLETED
    docs_map = {sec_item.id: extracted_doc}

    index_path = export_research_index(
        task=task,
        sources=source_items,
        extracted_docs=docs_map,
        vault_path=vault_path,
    )

    # --- 9. 验证文件存在 ---
    assert index_path.exists()
    assert index_path.name == "index.md"

    index_content = index_path.read_text(encoding="utf-8")
    assert "Elon Musk" in index_content
    assert "研究索引" in index_content
    assert "Elon Musk" in index_content or "Martin Eberhard" in index_content

    # 验证目录结构
    research_dir = index_path.parent
    sources_dir = research_dir / "sources"
    assert sources_dir.exists()
    assert any(sources_dir.iterdir())  # 至少有一个 source markdown

    # 验证 source markdown 在 sources/ 目录下
    source_files = list(sources_dir.glob("*.md"))
    assert len(source_files) >= 1
