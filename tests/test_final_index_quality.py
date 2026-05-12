"""final_index_synthesis 输出质量测试。"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.ai.schemas import (
    FinalIndexSynthesisOutput,
    SynthesisBookSource,
    SynthesisKeyPerson,
    SynthesisKeyPlace,
    SynthesisStoryPoint,
    SynthesisTimelineEvent,
    SynthesisVerificationWarning,
)
from models.enums import SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from services.book_relevance_service import BookRelevanceResult
from services.markdown_service import export_research_index, generate_index_synthesis


@pytest.fixture
def task():
    return ResearchTask(
        id="test-quality-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sources():
    return [
        SourceItem(
            id="s1",
            task_id="test-quality-001",
            title="Tim Cook: The Genius Who Took Apple to the Next Level",
            url="https://books.example.com/cook",
            domain="books.example.com",
            snippet="A biography of Apple CEO Tim Cook",
            source_type=SourceType.BOOK,
            source_level=SourceLevel.A,
            relevance_score=0.85,
            authority_score=0.8,
            reason_to_read="Comprehensive biography of Tim Cook",
        ),
        SourceItem(
            id="s2",
            task_id="test-quality-001",
            title="Apple Leadership Tim Cook",
            url="https://apple.com/leadership",
            domain="apple.com",
            snippet="Official bio of Tim Cook",
            source_type=SourceType.DOCUMENTATION,
            source_level=SourceLevel.S,
            relevance_score=0.95,
            authority_score=0.99,
            reason_to_read="Official source",
        ),
        SourceItem(
            id="s3",
            task_id="test-quality-001",
            title="Interview with Tim Cook at Stanford",
            url="https://stanford.edu/interview",
            domain="stanford.edu",
            snippet="Q&A session about his early life",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.A,
            relevance_score=0.85,
            authority_score=0.8,
            reason_to_read="First-hand account",
        ),
    ]


@pytest.fixture
def book_reviews():
    return {
        "s1": BookRelevanceResult(
            is_relevant=True,
            relevance_level="high",
            book_title_zh="蒂姆·库克：将苹果带入下一个时代的天才",
            book_type="biography",
            why_relevant="直接以 Tim Cook 为主题的传记，可能包含童年经历",
            likely_contains=["童年和家庭", "Auburn University", "IBM / Compaq 早期职业"],
        ),
    }


@pytest.fixture
def synthesis():
    return FinalIndexSynthesisOutput(
        overview="本次研究围绕 Tim Cook 的童年故事展开，收集了多个高质量来源。",
        topic_fit_warning=[],
        book_sources=[
            SynthesisBookSource(
                title="Tim Cook: The Genius Who Took Apple to the Next Level",
                title_zh="蒂姆·库克：将苹果带入下一个时代的天才",
                author="Leander Kahney",
                book_type="biography",
                relevance="high",
                why_read="可能包含库克的家庭背景、早年成长",
                likely_contains=["童年和家庭", "Auburn University"],
            ),
        ],
        key_people=[
            SynthesisKeyPerson(name="Tim Cook", role="研究主体", importance="high"),
            SynthesisKeyPerson(name="Steve Jobs", role="前任 CEO", importance="high"),
        ],
        key_places=[
            SynthesisKeyPlace(name="Robertsdale, Alabama", significance="Tim Cook 出生地"),
        ],
        key_concepts=["Apple", "领导力", "供应链管理"],
        timeline_events=[
            SynthesisTimelineEvent(date="1960", event="Tim Cook 出生于 Alabama", source="传记"),
        ],
        story_points=[
            SynthesisStoryPoint(point="Cook 在小镇长大的经历", source="传记", verified=False),
        ],
        verification_warnings=[
            SynthesisVerificationWarning(
                claim="Cook 童年家境贫寒",
                source="网络文章",
                risk="未经一手来源验证",
            ),
        ],
        filtered_noise_summary=["Python NLP Cookbook（与主题无关）", "Jamie Oliver 烹饪书（关键词歧义）"],
        suggested_next_steps=["提取传记正文", "寻找 Auburn University 校友访谈"],
    )


class TestIndexBookQuality:
    """index.md 图书资料质量测试。"""

    def test_book_has_chinese_name(self, task, sources, book_reviews, synthesis, tmp_path):
        """图书资料包含中文名。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews=book_reviews,
        )
        content = path.read_text(encoding="utf-8")
        assert "蒂姆·库克" in content

    def test_book_has_author(self, task, sources, book_reviews, synthesis, tmp_path):
        """图书资料包含作者。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews=book_reviews,
        )
        content = path.read_text(encoding="utf-8")
        assert "Leander Kahney" in content

    def test_book_has_why_read(self, task, sources, book_reviews, synthesis, tmp_path):
        """图书资料包含为什么值得看。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews=book_reviews,
        )
        content = path.read_text(encoding="utf-8")
        assert "为什么值得看" in content
        # 应该有具体内容而非"待分析"
        assert "Tim Cook" in content or "传记" in content or "童年" in content

    def test_irrelevant_book_not_in_books_section(self, task, synthesis, tmp_path):
        """不相关图书不出现在图书资料。"""
        # 添加一个不相关的图书
        sources_with_noise = [
            SourceItem(
                id="s_irrelevant",
                task_id="test-quality-001",
                title="Python Natural Language Processing Cookbook",
                url="https://books.example.com/nlp",
                domain="books.example.com",
                snippet="NLP recipes in Python",
                source_type=SourceType.BOOK,
                source_level=SourceLevel.B,
            ),
            SourceItem(
                id="s_relevant",
                task_id="test-quality-001",
                title="Tim Cook: The Genius",
                url="https://books.example.com/cook",
                domain="books.example.com",
                snippet="Biography",
                source_type=SourceType.BOOK,
                source_level=SourceLevel.A,
            ),
        ]

        reviews = {
            "s_irrelevant": BookRelevanceResult(
                is_relevant=False,
                relevance_level="irrelevant",
                why_relevant="NLP cookbook 与 Tim Cook 无关",
            ),
            "s_relevant": BookRelevanceResult(
                is_relevant=True,
                relevance_level="high",
                book_title_zh="蒂姆·库克：天才",
                book_type="biography",
                why_relevant="Tim Cook 传记",
                likely_contains=["童年经历"],
            ),
        }

        path = export_research_index(
            task, sources_with_noise, {},
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews=reviews,
        )
        content = path.read_text(encoding="utf-8")

        # 不相关图书不应出现在图书资料部分
        assert "Python Natural Language Processing" not in content
        # 相关图书应该出现
        assert "Tim Cook" in content


class TestIndexEntityQuality:
    """index.md 实体信息质量测试。"""

    def test_key_people_not_empty(self, task, sources, synthesis, tmp_path):
        """相关人物不为空。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "关键人物" in content
        # 应该有具体人物
        assert "Tim Cook" in content
        assert "Steve Jobs" in content

    def test_key_concepts_not_empty(self, task, sources, synthesis, tmp_path):
        """重点名词不为空。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "重点名词" in content
        assert "Apple" in content

    def test_verification_warnings_written(self, task, sources, synthesis, tmp_path):
        """待核验信息能写入。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "待核验信息" in content
        assert "Cook 童年家境贫寒" in content


class TestIndexExtractionStatus:
    """来源提取状态标记测试。"""

    def test_unextracted_source_marked(self, task, sources, synthesis, tmp_path):
        """没正文的来源标记"尚未抓取正文"。"""
        # 不传 extracted_docs → 所有来源都没有正文
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "尚未抓取正文" in content

    def test_extracted_source_marked(self, task, sources, synthesis, tmp_path):
        """有正文的来源标记"已提取正文"。"""
        extracted = {
            "s1": ExtractedDocument(
                source_item_id="s1",
                title="Tim Cook: The Genius",
                author="Leander Kahney",
                content="Full text content here...",
                people=["Tim Cook", "Steve Jobs"],
                concepts=["Apple", "Leadership"],
            ),
        }
        path = export_research_index(
            task, sources, extracted,
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews={
                "s1": BookRelevanceResult(
                    is_relevant=True,
                    relevance_level="high",
                    book_title_zh="蒂姆·库克传",
                    book_type="biography",
                    why_relevant="传记",
                    likely_contains=["童年"],
                ),
            },
        )
        content = path.read_text(encoding="utf-8")
        assert "已提取正文" in content


class TestGenerateIndexSynthesis:
    """generate_index_synthesis 函数测试。"""

    @pytest.mark.asyncio
    async def test_generates_with_gateway(self, sources):
        """有 AI Gateway 时应调用 LLM 生成结构化输出。"""
        mock_gateway = MagicMock()
        mock_gateway.run_json = AsyncMock(return_value=FinalIndexSynthesisOutput(
            overview="这是 LLM 生成的研究概览。",
            key_people=[SynthesisKeyPerson(name="Tim Cook", role="主体", importance="high")],
        ))

        result = await generate_index_synthesis(
            topic="Tim Cook 童年故事",
            mode="person",
            sources=sources,
            ai_gateway=mock_gateway,
        )

        assert isinstance(result, FinalIndexSynthesisOutput)
        assert "研究概览" in result.overview or "LLM" in result.overview
        mock_gateway.run_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_without_gateway(self, sources):
        """没有 AI Gateway 时返回规则生成的结果。"""
        result = await generate_index_synthesis(
            topic="Tim Cook 童年故事",
            mode="person",
            sources=sources,
            ai_gateway=None,
        )

        assert isinstance(result, FinalIndexSynthesisOutput)
        assert "Tim Cook" in result.overview
        assert len(result.key_people) > 0

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self, sources):
        """LLM 失败时返回规则生成的结果。"""
        mock_gateway = MagicMock()
        mock_gateway.run_json = AsyncMock(side_effect=Exception("API error"))

        result = await generate_index_synthesis(
            topic="Tim Cook 童年故事",
            mode="person",
            sources=sources,
            ai_gateway=mock_gateway,
        )

        assert isinstance(result, FinalIndexSynthesisOutput)
        assert "Tim Cook" in result.overview
