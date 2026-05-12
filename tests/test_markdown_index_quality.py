"""Markdown index.md 输出质量测试 - 验证 final_index_synthesis 结果正确写入 index.md。"""

import pytest

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
from models.schemas import ResearchTask, SourceItem
from services.book_relevance_service import BookRelevanceResult
from services.markdown_service import export_research_index


@pytest.fixture
def task():
    return ResearchTask(
        id="test-md-quality-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sources():
    return [
        SourceItem(
            id="s1",
            task_id="test-md-quality-001",
            title="Tim Cook: The Genius Who Took Apple to the Next Level",
            url="https://books.example.com/cook",
            domain="books.example.com",
            snippet="A biography of Apple CEO Tim Cook",
            source_type=SourceType.BOOK,
            source_level=SourceLevel.A,
            relevance_score=0.85,
            reason_to_read="Comprehensive biography",
        ),
        SourceItem(
            id="s2",
            task_id="test-md-quality-001",
            title="Apple Leadership",
            url="https://apple.com/leadership",
            domain="apple.com",
            snippet="Official bio",
            source_type=SourceType.DOCUMENTATION,
            source_level=SourceLevel.S,
            relevance_score=0.95,
            reason_to_read="Official source",
        ),
    ]


@pytest.fixture
def synthesis():
    return FinalIndexSynthesisOutput(
        overview="Tim Cook 出生于 1960 年的 Alabama 州 Robertsdale，本次研究收集了传记、官方资料和访谈等多种来源。",
        topic_fit_warning=["部分图书因关键词歧义被错误匹配"],
        book_sources=[
            SynthesisBookSource(
                title="Tim Cook: The Genius Who Took Apple to the Next Level",
                title_zh="蒂姆·库克：将苹果带入下一个时代的天才",
                author="Leander Kahney",
                book_type="biography",
                relevance="high",
                why_read="可能包含库克的家庭背景、早年成长",
                likely_contains=["童年和家庭", "Auburn University", "IBM 早期职业"],
            ),
        ],
        key_people=[
            SynthesisKeyPerson(name="Tim Cook", role="研究主体", importance="high"),
            SynthesisKeyPerson(name="Steve Jobs", role="前任 CEO，与 Cook 关系密切", importance="high"),
        ],
        key_places=[
            SynthesisKeyPlace(name="Robertsdale, Alabama", significance="Tim Cook 出生地"),
        ],
        key_concepts=["Apple", "领导力", "供应链管理"],
        timeline_events=[
            SynthesisTimelineEvent(date="1960", event="Tim Cook 出生", source="传记"),
            SynthesisTimelineEvent(date="1982", event="Auburn University 毕业", source="官方资料"),
        ],
        story_points=[
            SynthesisStoryPoint(point="Cook 在 Alabama 小镇长大的经历", source="传记", verified=False),
        ],
        verification_warnings=[
            SynthesisVerificationWarning(
                claim="Cook 童年家境贫寒",
                source="网络文章",
                risk="未经一手来源验证",
            ),
        ],
        filtered_noise_summary=[
            "Python NLP Cookbook（NLP 技术书，与 Tim Cook 无关）",
            "Jamie Oliver 烹饪书（关键词 Cook 歧义匹配）",
        ],
        suggested_next_steps=["提取传记正文", "寻找 Auburn University 校友访谈"],
    )


class TestOverviewWrittenToIndex:
    """final_index_synthesis 输出 overview 写入 index.md。"""

    def test_overview_in_index(self, task, sources, synthesis, tmp_path):
        """overview 内容出现在 index.md 中。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "研究概览" in content
        assert "Tim Cook 出生于 1960 年" in content

    def test_overview_not_just_stats(self, task, sources, synthesis, tmp_path):
        """overview 不只是统计数字。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        # 应该有实质内容，不只是"共收集 X 条来源"
        assert "Alabama" in content or "Robertsdale" in content


class TestFilteredNoiseSummaryWritten:
    """filtered_noise_summary 写入 index.md。"""

    def test_filtered_noise_in_index(self, task, sources, synthesis, tmp_path):
        """被过滤噪音概览出现在 index.md 中。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "被过滤噪音概览" in content
        assert "Python NLP Cookbook" in content
        assert "Jamie Oliver" in content

    def test_filtered_books_passed_directly(self, task, sources, tmp_path):
        """直接传入的 filtered_books 也能写入。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            filtered_books=["Gourmet Cooking for Dummies（烹饪书）"],
        )
        content = path.read_text(encoding="utf-8")
        assert "Gourmet Cooking" in content


class TestBookSourcesStructured:
    """book_sources 结构化写入。"""

    def test_book_has_structured_info(self, task, sources, synthesis, tmp_path):
        """图书资料包含结构化信息。"""
        book_reviews = {
            "s1": BookRelevanceResult(
                is_relevant=True,
                relevance_level="high",
                book_title_zh="蒂姆·库克：将苹果带入下一个时代的天才",
                book_type="biography",
                why_relevant="直接以 Tim Cook 为主题的传记",
                likely_contains=["童年和家庭", "Auburn University"],
            ),
        }

        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews=book_reviews,
        )
        content = path.read_text(encoding="utf-8")

        # 结构化字段
        assert "中文名" in content
        assert "作者" in content
        assert "类型" in content
        assert "相关性" in content
        assert "为什么值得看" in content
        assert "可能包含" in content
        assert "状态" in content

    def test_book_chinese_name_from_review(self, task, sources, synthesis, tmp_path):
        """图书中文名来自 book_reviews。"""
        book_reviews = {
            "s1": BookRelevanceResult(
                is_relevant=True,
                relevance_level="high",
                book_title_zh="蒂姆·库克：将苹果带入下一个时代的天才",
                book_type="biography",
                why_relevant="传记",
                likely_contains=["童年"],
            ),
        }

        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews=book_reviews,
        )
        content = path.read_text(encoding="utf-8")
        assert "蒂姆·库克：将苹果带入下一个时代的天才" in content


class TestIndexNotJustSourceList:
    """index.md 不只是来源列表。"""

    def test_has_research_judgment(self, task, sources, synthesis, tmp_path):
        """index.md 包含研究判断。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")

        # 应该有多个实质性部分
        sections_present = 0
        for section in ["研究概览", "关键人物", "时间线", "待核验信息", "下一步深挖方向"]:
            if section in content:
                sections_present += 1

        assert sections_present >= 4, f"Only {sections_present} sections found"

    def test_has_timeline(self, task, sources, synthesis, tmp_path):
        """index.md 包含时间线。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "时间线" in content
        assert "1960" in content

    def test_has_story_points(self, task, sources, synthesis, tmp_path):
        """index.md 包含故事点。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "故事点" in content
        assert "Alabama" in content or "小镇" in content

    def test_has_next_steps(self, task, sources, synthesis, tmp_path):
        """index.md 包含下一步方向。"""
        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
        )
        content = path.read_text(encoding="utf-8")
        assert "下一步深挖方向" in content
        assert "提取传记正文" in content

    def test_content_length_substantial(self, task, sources, synthesis, tmp_path):
        """index.md 内容长度足够（不只是简单列表）。"""
        book_reviews = {
            "s1": BookRelevanceResult(
                is_relevant=True,
                relevance_level="high",
                book_title_zh="蒂姆·库克传",
                book_type="biography",
                why_relevant="传记",
                likely_contains=["童年", "Auburn"],
            ),
        }

        path = export_research_index(
            task, sources, {},
            vault_path=tmp_path,
            synthesis=synthesis,
            book_reviews=book_reviews,
        )
        content = path.read_text(encoding="utf-8")
        # 一个有研究价值的 index 应该至少有 500 字符
        assert len(content) > 500
