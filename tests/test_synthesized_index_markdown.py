"""测试 render_synthesized_index 生成高质量 index.md。"""

from __future__ import annotations

import pytest

from app.services.markdown_service import render_synthesized_index
from models.enums import ClaimConfidence, DownloadStatus, SourceLevel, SourceType
from models.schemas import (
    DeduplicatedClaimGroup,
    SourceItem,
    SynthesizedResearchDocument,
)


# === Fixtures ===


def _make_synthesis(**kwargs) -> SynthesizedResearchDocument:
    """创建测试用 SynthesizedResearchDocument。"""
    defaults = {
        "task_id": "task-001",
        "topic": "Apple Inc. 发展史",
        "canonical_topic": "Apple Inc.",
        "overview": "Apple 是全球最大的科技公司之一，本研究梳理了其从车库创业到万亿市值的历程。",
        "executive_summary": "Apple 于 1976 年创立；iPhone 于 2007 年发布，彻底改变了智能手机行业；Tim Cook 于 2011 年接任 CEO。",
        "confirmed_facts": [
            DeduplicatedClaimGroup(
                group_id="grp-1",
                normalized_claim="Apple founded 1976",
                claim_type="fact",
                merged_claim="Apple 于 1976 年由 Steve Jobs、Steve Wozniak 和 Ronald Wayne 在加州车库创立",
                supporting_sources=[
                    {"source_id": "src-1", "title": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Apple_Inc."},
                    {"source_id": "src-2", "title": "Official History", "url": "https://apple.com/history"},
                ],
                confidence=ClaimConfidence.HIGH,
                importance=5,
            ),
            DeduplicatedClaimGroup(
                group_id="grp-2",
                normalized_claim="iPhone launched 2007",
                claim_type="fact",
                merged_claim="iPhone 于 2007 年 1 月由 Steve Jobs 在 Macworld 发布",
                supporting_sources=[
                    {"source_id": "src-3", "title": "Macworld Keynote", "url": "https://example.com/macworld"},
                ],
                confidence=ClaimConfidence.HIGH,
                importance=5,
            ),
        ],
        "timeline": [
            DeduplicatedClaimGroup(
                group_id="tl-1",
                normalized_claim="1976 founded",
                claim_type="timeline_event",
                merged_claim="Apple 成立",
                supporting_sources=[{"source_id": "src-1", "title": "Wiki", "url": "https://wiki.org"}],
                confidence=ClaimConfidence.HIGH,
                importance=5,
                dates=["1976"],
            ),
            DeduplicatedClaimGroup(
                group_id="tl-2",
                normalized_claim="2007 iPhone",
                claim_type="timeline_event",
                merged_claim="iPhone 发布",
                supporting_sources=[{"source_id": "src-3", "title": "Macworld", "url": ""}],
                confidence=ClaimConfidence.HIGH,
                importance=5,
                dates=["2007"],
            ),
        ],
        "key_people": [
            {"name": "Steve Jobs", "description": "联合创始人、前 CEO", "relation_to_topic": "Apple 灵魂人物"},
            {"name": "Tim Cook", "description": "现任 CEO", "relation_to_topic": "2011 年接任"},
        ],
        "key_places": [
            {"name": "Cupertino", "description": "Apple 总部所在地"},
        ],
        "key_concepts": [
            {"name": "iPhone", "description": "Apple 核心产品，2007 年发布"},
            {"name": "App Store", "description": "移动应用生态系统"},
        ],
        "story_points": [
            DeduplicatedClaimGroup(
                group_id="sp-1",
                normalized_claim="garage founding",
                claim_type="story_point",
                merged_claim="三个人在车库里创立了后来的万亿公司",
                supporting_sources=[{"source_id": "src-1", "title": "Wiki", "url": "https://wiki.org"}],
                confidence=ClaimConfidence.MEDIUM,
                importance=4,
            ),
        ],
        "controversies": [
            DeduplicatedClaimGroup(
                group_id="cv-1",
                normalized_claim="labor controversy",
                claim_type="controversy",
                merged_claim="供应链劳工问题",
                supporting_sources=[{"source_id": "src-4", "title": "NYT Report", "url": "https://nyt.com/apple"}],
                conflicting_sources=[{"source_id": "src-5", "title": "Apple Response", "claim": "已改善"}],
                confidence=ClaimConfidence.CONFLICTING,
                importance=3,
                needs_verification=True,
            ),
        ],
        "verification_needed": [
            DeduplicatedClaimGroup(
                group_id="vn-1",
                normalized_claim="unverified revenue",
                claim_type="fact",
                merged_claim="2024 年收入预计超 4000 亿美元",
                supporting_sources=[{"source_id": "src-6", "title": "Analyst Report", "url": ""}],
                confidence=ClaimConfidence.UNVERIFIED,
                importance=3,
                needs_verification=True,
            ),
        ],
        "source_map": [
            {"source_id": "src-1", "title": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Apple_Inc.", "contribution": "基础事实"},
            {"source_id": "src-3", "title": "Macworld Keynote", "url": "https://example.com/macworld", "contribution": "iPhone 发布细节"},
            {"source_id": "src-4", "title": "NYT Report", "url": "https://nyt.com/apple", "contribution": "劳工争议"},
        ],
        "suggested_next_steps": [
            "深入研究 iPhone 产品线演变",
            "核验供应链劳工问题的最新进展",
            "补充 Apple Silicon 相关资料",
        ],
        "generated_at": "2025-01-15 10:30",
    }
    defaults.update(kwargs)
    return SynthesizedResearchDocument(**defaults)


def _make_sources() -> list[SourceItem]:
    """创建测试用 SourceItem 列表。"""
    return [
        SourceItem(
            id="src-1", task_id="task-001", title="Wikipedia",
            url="https://en.wikipedia.org/wiki/Apple_Inc.",
            source_type=SourceType.REFERENCE, source_level=SourceLevel.A,
            download_status=DownloadStatus.EXTRACTED,
        ),
        SourceItem(
            id="src-3", task_id="task-001", title="Macworld Keynote",
            url="https://example.com/macworld",
            source_type=SourceType.NEWS, source_level=SourceLevel.S,
            download_status=DownloadStatus.EXTRACTED,
        ),
        SourceItem(
            id="src-book", task_id="task-001", title="Becoming Steve Jobs",
            url="",
            source_type=SourceType.BOOK, source_level=SourceLevel.A,
            download_status=DownloadStatus.PENDING,
            reason_to_read="深入了解 Jobs 的管理风格转变",
        ),
    ]


# === Tests ===


class TestOverviewSection:
    """index.md 包含"研究概览"。"""

    def test_contains_overview_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 一、研究概览" in md

    def test_contains_overview_content(self):
        md = render_synthesized_index(_make_synthesis())
        assert "Apple 是全球最大的科技公司之一" in md


class TestExecutiveSummary:
    """index.md 包含"核心摘要"。"""

    def test_contains_summary_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 二、核心摘要" in md

    def test_contains_summary_content(self):
        md = render_synthesized_index(_make_synthesis())
        assert "Apple 于 1976 年创立" in md


class TestConfirmedFacts:
    """index.md 包含"已确认的关键信息"。"""

    def test_contains_confirmed_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 三、已确认的关键信息" in md

    def test_confirmed_facts_listed(self):
        md = render_synthesized_index(_make_synthesis())
        assert "Apple 于 1976 年由 Steve Jobs" in md
        assert "iPhone 于 2007 年" in md


class TestConfirmedFactSources:
    """confirmed fact 下有来源链接。"""

    def test_source_links_present(self):
        md = render_synthesized_index(_make_synthesis())
        assert "[Wikipedia](https://en.wikipedia.org/wiki/Apple_Inc.)" in md
        assert "[Official History](https://apple.com/history)" in md

    def test_source_without_url_shows_title(self):
        """没有 URL 的来源显示 title 和 source_id。"""
        synthesis = _make_synthesis(
            confirmed_facts=[
                DeduplicatedClaimGroup(
                    normalized_claim="test",
                    claim_type="fact",
                    merged_claim="无 URL 的事实",
                    supporting_sources=[
                        {"source_id": "src-99", "title": "Internal Doc", "url": ""},
                    ],
                    confidence=ClaimConfidence.HIGH,
                    importance=4,
                ),
            ]
        )
        md = render_synthesized_index(synthesis)
        assert "Internal Doc" in md
        assert "src-99" in md


class TestTimeline:
    """index.md 包含时间线。"""

    def test_contains_timeline_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 四、时间线" in md

    def test_timeline_table_format(self):
        md = render_synthesized_index(_make_synthesis())
        assert "| 时间 | 事件 | 来源 |" in md
        assert "| 1976 |" in md
        assert "| 2007 |" in md


class TestPeoplePlacesConcepts:
    """index.md 包含人物/地点/重点名词。"""

    def test_contains_people_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 五、相关人物" in md

    def test_people_listed(self):
        md = render_synthesized_index(_make_synthesis())
        assert "Steve Jobs" in md
        assert "Tim Cook" in md

    def test_contains_places_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 六、相关地点" in md

    def test_places_listed(self):
        md = render_synthesized_index(_make_synthesis())
        assert "Cupertino" in md

    def test_contains_concepts_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 七、重点名词" in md

    def test_concepts_listed(self):
        md = render_synthesized_index(_make_synthesis())
        assert "iPhone" in md
        assert "App Store" in md


class TestVerificationNeeded:
    """index.md 包含待核验信息。"""

    def test_contains_verification_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 十、冲突与待核验信息" in md

    def test_verification_table(self):
        md = render_synthesized_index(_make_synthesis())
        assert "| 说法 | 问题 | 下一步核验 | 来源 |" in md
        assert "供应链劳工问题" in md
        assert "来源冲突" in md


class TestSourceMap:
    """source_map 被写入资料来源地图。"""

    def test_contains_source_map_heading(self):
        md = render_synthesized_index(_make_synthesis())
        assert "## 十一、资料来源地图" in md

    def test_source_map_entries(self):
        md = render_synthesized_index(_make_synthesis(), sources=_make_sources())
        assert "Wikipedia" in md
        assert "Macworld Keynote" in md
        assert "参与合成" in md

    def test_source_map_shows_contribution(self):
        md = render_synthesized_index(_make_synthesis())
        assert "基础事实" in md


class TestFallbackWithoutSynthesis:
    """没有 synthesis 时 fallback 到旧 index（空 synthesis 仍可渲染）。"""

    def test_empty_synthesis_renders_placeholder(self):
        """空 synthesis 仍然生成有效 markdown。"""
        empty = SynthesizedResearchDocument(
            task_id="task-empty",
            topic="空主题",
        )
        md = render_synthesized_index(empty)
        assert "# 空主题｜研究文档" in md
        assert "## 一、研究概览" in md
        assert "暂无" in md  # 各节都有 placeholder

    def test_empty_synthesis_has_frontmatter(self):
        empty = SynthesizedResearchDocument(task_id="t", topic="X")
        md = render_synthesized_index(empty)
        assert "---" in md
        assert "synthesis: true" in md


class TestIrrelevantSourcesExcluded:
    """不相关来源不出现在核心事实区。"""

    def test_only_supporting_sources_in_confirmed(self):
        """confirmed_facts 只显示 supporting_sources 中的来源。"""
        synthesis = _make_synthesis()
        md = render_synthesized_index(synthesis, sources=_make_sources())

        # 在"已确认的关键信息"区域，不应出现不相关来源
        confirmed_section_start = md.index("## 三、已确认的关键信息")
        confirmed_section_end = md.index("## 四、时间线")
        confirmed_section = md[confirmed_section_start:confirmed_section_end]

        # src-4 (NYT Report) 不在 confirmed_facts 的 supporting_sources 中
        assert "NYT Report" not in confirmed_section
        # src-1 (Wikipedia) 在 confirmed_facts 中
        assert "Wikipedia" in confirmed_section


class TestObsidianCompatibility:
    """Markdown 兼容 Obsidian。"""

    def test_frontmatter_valid(self):
        md = render_synthesized_index(_make_synthesis())
        # 以 --- 开头和结尾
        assert md.startswith("---\n")
        # 第二个 --- 存在
        second_dash = md.index("---", 4)
        assert second_dash > 0

    def test_no_html_tags(self):
        """不包含 HTML 标签（Obsidian 偏好纯 markdown）。"""
        md = render_synthesized_index(_make_synthesis())
        assert "<div" not in md
        assert "<span" not in md
        assert "<table" not in md
