"""Results 页面纯函数逻辑测试。"""

import sys
sys.path.insert(0, ".")

from ui.pages._results_helpers import (
    group_sources_by_category,
    build_source_filter_state,
    apply_source_filters,
    format_task_summary_cards,
    get_synthesis_button_state,
    get_export_button_state,
)


# ============================================================
# group_sources_by_category
# ============================================================


class TestGroupSourcesByCategory:
    def test_empty_list(self):
        result = group_sources_by_category([])
        assert result == {}

    def test_s_a_goes_to_must_read(self):
        sources = [
            {"source_level": "S", "source_type": "article", "gossip_score": 0},
            {"source_level": "A", "source_type": "article", "gossip_score": 0},
        ]
        result = group_sources_by_category(sources)
        assert "必读资料" in result
        assert len(result["必读资料"]) == 2

    def test_books_grouped(self):
        sources = [
            {"source_level": "B", "source_type": "book", "gossip_score": 0},
        ]
        result = group_sources_by_category(sources)
        assert "图书资料" in result
        assert len(result["图书资料"]) == 1

    def test_gossip_grouped(self):
        sources = [
            {"source_level": "C", "source_type": "article", "gossip_score": 0.5},
        ]
        result = group_sources_by_category(sources)
        assert "八卦与旁证" in result

    def test_b_level_goes_to_deep_report(self):
        sources = [
            {"source_level": "B", "source_type": "article", "gossip_score": 0},
        ]
        result = group_sources_by_category(sources)
        assert "深度报道" in result


# ============================================================
# build_source_filter_state
# ============================================================


class TestBuildSourceFilterState:
    def test_defaults(self):
        state = build_source_filter_state()
        assert state["level"] == "全部"
        assert state["source_type"] == "全部"
        assert state["download_status"] == "全部"
        assert state["keyword"] == ""
        assert state["hide_low_quality"] is True

    def test_custom_values(self):
        state = build_source_filter_state(level="A", keyword="  Test  ")
        assert state["level"] == "A"
        assert state["keyword"] == "test"

    def test_hide_low_quality_false(self):
        state = build_source_filter_state(hide_low_quality=False)
        assert state["hide_low_quality"] is False


# ============================================================
# apply_source_filters
# ============================================================


class TestApplySourceFilters:
    def _make_sources(self):
        return [
            {"source_level": "S", "source_type": "article", "download_status": "extracted", "title": "Alpha", "domain": "a.com", "snippet": ""},
            {"source_level": "A", "source_type": "book", "download_status": "pending", "title": "Beta", "domain": "b.com", "snippet": ""},
            {"source_level": "B", "source_type": "article", "download_status": "pending", "title": "Gamma", "domain": "c.com", "snippet": ""},
            {"source_level": "D", "source_type": "other", "download_status": "failed", "title": "Delta", "domain": "d.com", "snippet": ""},
        ]

    def test_no_filter(self):
        sources = self._make_sources()
        filters = build_source_filter_state(hide_low_quality=False)
        result = apply_source_filters(sources, filters)
        assert len(result) == 4

    def test_filter_by_level(self):
        sources = self._make_sources()
        filters = build_source_filter_state(level="S", hide_low_quality=False)
        result = apply_source_filters(sources, filters)
        assert len(result) == 1
        assert result[0]["title"] == "Alpha"

    def test_filter_by_type(self):
        sources = self._make_sources()
        filters = build_source_filter_state(source_type="book", hide_low_quality=False)
        result = apply_source_filters(sources, filters)
        assert len(result) == 1
        assert result[0]["title"] == "Beta"

    def test_filter_by_keyword(self):
        sources = self._make_sources()
        filters = build_source_filter_state(keyword="gamma", hide_low_quality=False)
        result = apply_source_filters(sources, filters)
        assert len(result) == 1

    def test_hide_low_quality(self):
        sources = self._make_sources()
        filters = build_source_filter_state(hide_low_quality=True)
        result = apply_source_filters(sources, filters)
        assert all(s["source_level"] != "D" for s in result)
        assert len(result) == 3

    def test_filter_by_download_status(self):
        sources = self._make_sources()
        filters = build_source_filter_state(download_status="extracted", hide_low_quality=False)
        result = apply_source_filters(sources, filters)
        assert len(result) == 1
        assert result[0]["title"] == "Alpha"


# ============================================================
# format_task_summary_cards
# ============================================================


class TestFormatTaskSummaryCards:
    def test_basic(self):
        task = {"status": "completed"}
        sources = [
            {"source_level": "S", "download_status": "extracted"},
            {"source_level": "A", "download_status": "extracted"},
            {"source_level": "B", "download_status": "pending"},
            {"source_level": "C", "download_status": "pending"},
        ]
        cards = format_task_summary_cards(task, sources)
        assert any(c["label"] == "Sources" and c["value"] == 4 for c in cards)
        assert any(c["label"] == "Extracted" and c["value"] == 2 for c in cards)
        assert any(c["label"] == "High Quality" and c["value"] == 2 for c in cards)

    def test_with_failures(self):
        task = {"status": "completed"}
        sources = [
            {"source_level": "B", "download_status": "failed"},
        ]
        cards = format_task_summary_cards(task, sources)
        assert any(c["label"] == "Failed" and c["value"] == 1 for c in cards)

    def test_empty_sources(self):
        cards = format_task_summary_cards({}, [])
        assert any(c["label"] == "Sources" and c["value"] == 0 for c in cards)


# ============================================================
# get_synthesis_button_state
# ============================================================


class TestGetSynthesisButtonState:
    def test_not_completed(self):
        state = get_synthesis_button_state("running", 5, True)
        assert state["enabled"] is False
        assert "尚未完成" in state["reason"]

    def test_no_extracted(self):
        state = get_synthesis_button_state("completed", 0, True)
        assert state["enabled"] is False
        assert "提取" in state["reason"]

    def test_no_vault(self):
        state = get_synthesis_button_state("completed", 5, False)
        assert state["enabled"] is False
        assert "Vault" in state["reason"]

    def test_all_ready(self):
        state = get_synthesis_button_state("completed", 5, True)
        assert state["enabled"] is True
        assert state["reason"] is None


# ============================================================
# get_export_button_state
# ============================================================


class TestGetExportButtonState:
    def test_not_completed(self):
        state = get_export_button_state("running", True, "/vault")
        assert state["enabled"] is False

    def test_no_vault(self):
        state = get_export_button_state("completed", False)
        assert state["enabled"] is False
        assert "Vault" in state["reason"]

    def test_ready(self):
        state = get_export_button_state("completed", True, "/vault/path")
        assert state["enabled"] is True
        assert state["target_path"] == "/vault/path"


# ============================================================
# Runner
# ============================================================


def _run_all():
    test_classes = [
        TestGroupSourcesByCategory,
        TestBuildSourceFilterState,
        TestApplySourceFilters,
        TestFormatTaskSummaryCards,
        TestGetSynthesisButtonState,
        TestGetExportButtonState,
    ]
    total = 0
    passed = 0
    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in methods:
            total += 1
            try:
                getattr(instance, method_name)()
                passed += 1
            except AssertionError as e:
                print(f"  FAIL {cls.__name__}.{method_name}: {e}")
            except Exception as e:
                print(f"  ERROR {cls.__name__}.{method_name}: {e}")

    print(f"\n{'✅' if passed == total else '❌'} {passed}/{total} tests passed")
    return passed == total


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
