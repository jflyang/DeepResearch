"""自动抓取策略测试 - 验证来源选择逻辑。"""

import pytest

from models.enums import DownloadStatus, SourceLevel, SourceType
from models.schemas import SourceItem
from services.auto_fetch_service import (
    _default_policy,
    _reset_policy_cache,
    select_sources_for_fetch,
)


@pytest.fixture(autouse=True)
def reset_policy():
    """每个测试前清除策略缓存。"""
    _reset_policy_cache()
    yield
    _reset_policy_cache()


@pytest.fixture
def default_policy():
    return _default_policy()


def _make_source(
    level: str = "A",
    source_type: str = "news",
    domain: str = "example.com",
    relevance: float = 0.8,
    download_status: str = "pending",
    **kwargs,
) -> SourceItem:
    """创建测试用 SourceItem。"""
    return SourceItem(
        id=kwargs.get("id", f"src-{level}-{domain}"),
        task_id="test-task",
        title=kwargs.get("title", f"Test Source ({level})"),
        url=f"https://{domain}/article",
        domain=domain,
        snippet="Test snippet",
        source_type=SourceType(source_type),
        source_level=SourceLevel(level),
        relevance_score=relevance,
        authority_score=0.7,
        download_status=DownloadStatus(download_status),
        reason_to_read="Test reason",
    )


class TestSourceSelection:
    """来源选择策略测试。"""

    def test_s_level_selected(self, default_policy):
        """S 级来源被选中。"""
        sources = [_make_source(level="S", id="s1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 1
        assert selected[0].source_level == SourceLevel.S

    def test_a_level_selected(self, default_policy):
        """A 级来源被选中。"""
        sources = [_make_source(level="A", id="a1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 1
        assert selected[0].source_level == SourceLevel.A

    def test_b_level_not_selected(self, default_policy):
        """B 级来源不自动抓取。"""
        sources = [_make_source(level="B", id="b1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0
        assert len(skipped) == 1

    def test_c_level_not_selected(self, default_policy):
        """C 级来源不自动抓取。"""
        sources = [_make_source(level="C", id="c1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0

    def test_d_level_not_selected(self, default_policy):
        """D 级来源不自动抓取。"""
        sources = [_make_source(level="D", id="d1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0

    def test_wikipedia_skipped(self, default_policy):
        """Wikipedia 默认不抓取。"""
        sources = [_make_source(level="S", domain="en.wikipedia.org", id="wiki1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0
        assert len(skipped) == 1

    def test_reference_type_skipped(self, default_policy):
        """reference 类型来源不抓取。"""
        sources = [_make_source(level="S", source_type="reference", id="ref1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0
        assert len(skipped) == 1

    def test_max_sources_per_task(self, default_policy):
        """max_sources_per_task 生效。"""
        # 创建 25 个 S 级来源
        sources = [_make_source(level="S", id=f"s{i}", domain=f"site{i}.com") for i in range(25)]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 20  # max_sources_per_task = 20

    def test_already_extracted_skipped(self, default_policy):
        """已抓取的来源不重复抓取。"""
        sources = [_make_source(level="S", download_status="extracted", id="ext1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0

    def test_low_relevance_skipped(self, default_policy):
        """低相关性来源不抓取。"""
        sources = [_make_source(level="S", relevance=0.1, id="low1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0

    def test_failed_not_retried_by_default(self, default_policy):
        """失败的来源默认不重试。"""
        sources = [_make_source(level="S", download_status="failed", id="fail1")]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 0

    def test_disabled_policy_selects_nothing(self):
        """auto_fetch.enabled=false 时不选择任何来源。"""
        policy = _default_policy()
        policy["auto_fetch"]["enabled"] = False
        sources = [_make_source(level="S", id="s1")]
        selected, skipped = select_sources_for_fetch(sources, policy)
        assert len(selected) == 0

    def test_mixed_levels_only_sa_selected(self, default_policy):
        """混合等级时只选 S/A。"""
        sources = [
            _make_source(level="S", id="s1", domain="s1.com"),
            _make_source(level="A", id="a1", domain="a1.com"),
            _make_source(level="B", id="b1", domain="b1.com"),
            _make_source(level="C", id="c1", domain="c1.com"),
            _make_source(level="D", id="d1", domain="d1.com"),
        ]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        assert len(selected) == 2
        levels = {s.source_level.value for s in selected}
        assert levels == {"S", "A"}

    def test_irrelevant_book_not_fetched(self, default_policy):
        """无关图书不抓取（通过 source_type 过滤）。"""
        # 如果图书被标记为 low_quality 类型则不抓
        sources = [_make_source(level="A", source_type="other", id="book1", relevance=0.1)]
        selected, skipped = select_sources_for_fetch(sources, default_policy)
        # 低相关性被过滤
        assert len(selected) == 0
