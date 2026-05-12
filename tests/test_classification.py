"""结果分类服务测试。"""

import pytest

from models.enums import DownloadStatus, SourceLevel, SourceType, TaskMode
from models.schemas import SourceItem
from services.result_classification_service import classify_results


def _make_item(
    title: str = "Test",
    url: str = "https://example.com",
    snippet: str = "Some content",
    source_level: SourceLevel = SourceLevel.B,
    source_type: SourceType = SourceType.OTHER,
    gossip_score: float = 0.0,
    relevance_score: float = 0.5,
    authority_score: float = 0.5,
    originality_score: float = 0.5,
    reason_to_read: str = "",
) -> SourceItem:
    return SourceItem(
        task_id="task-1",
        title=title,
        url=url,
        domain="example.com",
        snippet=snippet,
        source_type=source_type,
        source_level=source_level,
        relevance_score=relevance_score,
        authority_score=authority_score,
        originality_score=originality_score,
        gossip_score=gossip_score,
        reason_to_read=reason_to_read,
        download_status=DownloadStatus.PENDING,
    )


# === 基础分类测试 ===


class TestBaseClassification:
    def test_d_level_goes_to_low_quality(self):
        item = _make_item(source_level=SourceLevel.D)
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "低质量隐藏" in result
        assert item in result["低质量隐藏"]

    def test_d_level_only_in_low_quality(self):
        item = _make_item(
            source_level=SourceLevel.D,
            title="Interview with CEO childhood story",
        )
        result = classify_results([item], mode=TaskMode.PERSON)
        assert "低质量隐藏" in result
        # D 级不应出现在其他分类
        for cat, items in result.items():
            if cat != "低质量隐藏":
                assert item not in items

    def test_s_level_is_must_read(self):
        item = _make_item(source_level=SourceLevel.S, reason_to_read="[S] Official source")
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "必读资料" in result
        assert item in result["必读资料"]

    def test_official_category(self):
        item = _make_item(reason_to_read="[S] Official/government source")
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "官方资料" in result
        assert item in result["官方资料"]

    def test_primary_source_category(self):
        item = _make_item(reason_to_read="[A] Primary academic source")
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "一手资料" in result
        assert item in result["一手资料"]

    def test_book_category(self):
        item = _make_item(source_type=SourceType.BOOK, reason_to_read="[B] Book-length treatment")
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "图书资料" in result
        assert item in result["图书资料"]

    def test_interview_category(self):
        item = _make_item(title="Exclusive Interview with Elon Musk")
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "采访与演讲" in result
        assert item in result["采访与演讲"]

    def test_gossip_high_score(self):
        item = _make_item(gossip_score=0.5, source_level=SourceLevel.C)
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "八卦与旁证" in result
        assert item in result["八卦与旁证"]

    def test_c_level_with_some_gossip(self):
        item = _make_item(gossip_score=0.1, source_level=SourceLevel.C)
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "八卦与旁证" in result

    def test_controversy_category(self):
        item = _make_item(title="Tesla Lawsuit Over Autopilot Crash")
        result = classify_results([item], mode=TaskMode.AUTO)
        assert "争议资料" in result
        assert item in result["争议资料"]

    def test_item_in_multiple_categories(self):
        item = _make_item(
            title="SEC Filing Transcript of Tesla Investigation",
            source_level=SourceLevel.S,
            reason_to_read="[S] Official/government source",
        )
        result = classify_results([item], mode=TaskMode.AUTO)
        categories_with_item = [cat for cat, items in result.items() if item in items]
        assert len(categories_with_item) >= 2


# === 人物模式测试 ===


class TestPersonMode:
    def test_childhood_category(self):
        item = _make_item(title="Elon Musk's Childhood in South Africa")
        result = classify_results([item], mode=TaskMode.PERSON)
        assert "童年与家庭" in result
        assert item in result["童年与家庭"]

    def test_education_category(self):
        item = _make_item(title="Where Did Elon Musk Go to University?")
        result = classify_results([item], mode=TaskMode.PERSON)
        assert "教育经历" in result
        assert item in result["教育经历"]

    def test_early_career_category(self):
        item = _make_item(snippet="He co-founded Zip2 as his first company")
        result = classify_results([item], mode=TaskMode.PERSON)
        assert "早期职业" in result
        assert item in result["早期职业"]

    def test_personality_category(self):
        item = _make_item(title="The Work Habits and Philosophy of Elon Musk")
        result = classify_results([item], mode=TaskMode.PERSON)
        assert "性格与习惯" in result

    def test_relationship_category(self):
        item = _make_item(title="Elon Musk's Marriage and Family Life")
        result = classify_results([item], mode=TaskMode.PERSON)
        assert "人际关系" in result

    def test_controversy_category(self):
        item = _make_item(title="Allegations Against CEO in Lawsuit")
        result = classify_results([item], mode=TaskMode.PERSON)
        assert "争议与传闻" in result

    def test_person_categories_not_in_company_mode(self):
        item = _make_item(title="Childhood of the Founder")
        result = classify_results([item], mode=TaskMode.COMPANY)
        assert "童年与家庭" not in result


# === 公司模式测试 ===


class TestCompanyMode:
    def test_founding_category(self):
        item = _make_item(title="The Founding Story of Tesla Motors")
        result = classify_results([item], mode=TaskMode.COMPANY)
        assert "创始阶段" in result
        assert item in result["创始阶段"]

    def test_funding_category(self):
        item = _make_item(snippet="Series B funding round raised $50M from top investors")
        result = classify_results([item], mode=TaskMode.COMPANY)
        assert "融资与投资人" in result

    def test_early_product_category(self):
        item = _make_item(title="Tesla's First Product: The Roadster Prototype")
        result = classify_results([item], mode=TaskMode.COMPANY)
        assert "早期产品" in result

    def test_failure_category(self):
        item = _make_item(title="How Tesla Nearly Went Bankrupt in 2008")
        result = classify_results([item], mode=TaskMode.COMPANY)
        assert "关键失败" in result

    def test_competitor_category(self):
        item = _make_item(snippet="Tesla vs Rivian: the competition for EV market share")
        result = classify_results([item], mode=TaskMode.COMPANY)
        assert "竞争对手" in result

    def test_strategy_category(self):
        item = _make_item(title="Tesla's Strategic Pivot to Energy Storage")
        result = classify_results([item], mode=TaskMode.COMPANY)
        assert "战略转型" in result


# === 事件模式测试 ===


class TestEventMode:
    def test_timeline_category(self):
        item = _make_item(title="FTX Collapse: A Complete Timeline")
        result = classify_results([item], mode=TaskMode.EVENT)
        assert "时间线" in result
        assert item in result["时间线"]

    def test_documents_category(self):
        item = _make_item(title="Key Documents Filed in FTX Case")
        result = classify_results([item], mode=TaskMode.EVENT)
        assert "关键文件" in result

    def test_parties_category(self):
        item = _make_item(snippet="The defendant and plaintiff parties involved in the case")
        result = classify_results([item], mode=TaskMode.EVENT)
        assert "参与方" in result

    def test_statements_category(self):
        item = _make_item(title="SBF Testimony: What He Claimed Under Oath")
        result = classify_results([item], mode=TaskMode.EVENT)
        assert "各方说法" in result

    def test_conflict_category(self):
        item = _make_item(snippet="The central dispute between regulators and the exchange")
        result = classify_results([item], mode=TaskMode.EVENT)
        assert "冲突点" in result

    def test_aftermath_category(self):
        item = _make_item(title="The Aftermath: How FTX Changed Crypto Regulation")
        result = classify_results([item], mode=TaskMode.EVENT)
        assert "后续影响" in result


# === 概念模式测试 ===


class TestConceptMode:
    def test_definition_category(self):
        item = _make_item(title="What is Quantum Computing? Definition and Meaning")
        result = classify_results([item], mode=TaskMode.CONCEPT)
        assert "定义" in result
        assert item in result["定义"]

    def test_origin_category(self):
        item = _make_item(snippet="The history of quantum computing originated in the 1980s")
        result = classify_results([item], mode=TaskMode.CONCEPT)
        assert "起源" in result

    def test_paper_category(self):
        item = _make_item(title="Landmark Research Paper on Quantum Supremacy")
        result = classify_results([item], mode=TaskMode.CONCEPT)
        assert "代表论文" in result

    def test_key_people_category(self):
        item = _make_item(snippet="Richard Feynman was a pioneer in quantum computing")
        result = classify_results([item], mode=TaskMode.CONCEPT)
        assert "关键人物" in result

    def test_application_category(self):
        item = _make_item(title="Real World Applications of Quantum Computing")
        result = classify_results([item], mode=TaskMode.CONCEPT)
        assert "应用案例" in result

    def test_controversy_category(self):
        item = _make_item(title="The Debate Over Quantum Computing Limitations")
        result = classify_results([item], mode=TaskMode.CONCEPT)
        assert "争议" in result


# === 排序测试 ===


class TestSorting:
    def test_sorted_by_level_within_category(self):
        items = [
            _make_item(title="Interview C level", source_level=SourceLevel.C, snippet="An interview with the CEO"),
            _make_item(title="Interview S level", source_level=SourceLevel.S, snippet="An exclusive interview"),
            _make_item(title="Interview A level", source_level=SourceLevel.A, snippet="A detailed interview"),
        ]
        result = classify_results(items, mode=TaskMode.AUTO)
        if "采访与演讲" in result:
            levels = [i.source_level for i in result["采访与演讲"]]
            level_order = {SourceLevel.S: 0, SourceLevel.A: 1, SourceLevel.B: 2, SourceLevel.C: 3}
            ranks = [level_order[l] for l in levels]
            assert ranks == sorted(ranks)

    def test_empty_input(self):
        result = classify_results([], mode=TaskMode.AUTO)
        assert result == {}

    def test_empty_categories_removed(self):
        items = [_make_item(title="Random page", source_level=SourceLevel.B)]
        result = classify_results(items, mode=TaskMode.PERSON)
        # 不应有空分类
        for cat, cat_items in result.items():
            assert len(cat_items) > 0
