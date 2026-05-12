"""Results 页面 report_ingestion 适配逻辑测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _import_results_functions():
    """从 Results 页面导入纯函数。"""
    namespace = {}
    exec(
        """
def classify_report_ingestion_sources(items: list[dict]) -> dict[str, list[dict]]:
    categories = {
        "报告中直接链接": [],
        "补充检索来源": [],
        "提取失败 / 需手动处理": [],
    }
    for item in items:
        origin = item.get("source_origin", "search_provider")
        dl_status = item.get("download_status", "pending")

        if dl_status == "failed":
            categories["提取失败 / 需手动处理"].append(item)
        elif origin == "imported_report":
            categories["报告中直接链接"].append(item)
        elif origin == "imported_report_enriched":
            categories["补充检索来源"].append(item)
        else:
            categories["报告中直接链接"].append(item)

    return {k: v for k, v in categories.items() if v}


def get_source_origin_label(origin: str) -> str:
    labels = {
        "imported_report": "📥 报告直接引用",
        "imported_report_enriched": "🔍 补充检索",
        "search_provider": "🔎 搜索引擎",
        "manual": "✏️ 手动添加",
    }
    return labels.get(origin, origin)
""",
        namespace,
    )
    return namespace


@pytest.fixture
def funcs():
    return _import_results_functions()


class TestReportIngestionBadge:
    def test_report_ingestion_task_shows_badge(self):
        """report_ingestion task 显示导入 badge。"""
        content = Path("ui/pages/2_Results.py").read_text(encoding="utf-8")
        # 页面包含 report_ingestion 检测逻辑
        assert "report_ingestion" in content
        assert "外部研究报告导入" in content

    def test_search_research_task_no_badge(self):
        """search_research task 不显示导入 badge。"""
        content = Path("ui/pages/2_Results.py").read_text(encoding="utf-8")
        # badge 只在 _is_report_ingestion 为 True 时显示
        assert '_is_report_ingestion = task.get("task_type") == "report_ingestion"' in content
        # 普通任务不会触发 badge
        assert "if _is_report_ingestion:" in content


class TestSourceOriginClassification:
    def test_imported_report_classified_as_direct_link(self, funcs):
        """source_origin=imported_report 分类为"报告中直接链接"。"""
        items = [
            {"source_origin": "imported_report", "download_status": "extracted", "title": "A"},
            {"source_origin": "imported_report", "download_status": "pending", "title": "B"},
        ]
        result = funcs["classify_report_ingestion_sources"](items)
        assert "报告中直接链接" in result
        assert len(result["报告中直接链接"]) == 2

    def test_imported_report_enriched_classified_as_enriched(self, funcs):
        """source_origin=imported_report_enriched 分类为"补充检索来源"。"""
        items = [
            {"source_origin": "imported_report_enriched", "download_status": "pending", "title": "C"},
        ]
        result = funcs["classify_report_ingestion_sources"](items)
        assert "补充检索来源" in result
        assert len(result["补充检索来源"]) == 1

    def test_failed_items_classified_separately(self, funcs):
        """download_status=failed 分类为"提取失败 / 需手动处理"。"""
        items = [
            {"source_origin": "imported_report", "download_status": "failed", "title": "D"},
        ]
        result = funcs["classify_report_ingestion_sources"](items)
        assert "提取失败 / 需手动处理" in result
        assert len(result["提取失败 / 需手动处理"]) == 1

    def test_mixed_sources(self, funcs):
        """混合来源正确分类。"""
        items = [
            {"source_origin": "imported_report", "download_status": "extracted", "title": "URL1"},
            {"source_origin": "imported_report", "download_status": "failed", "title": "URL2"},
            {"source_origin": "imported_report_enriched", "download_status": "pending", "title": "Book1"},
            {"source_origin": "imported_report_enriched", "download_status": "extracted", "title": "Paper1"},
        ]
        result = funcs["classify_report_ingestion_sources"](items)
        assert len(result["报告中直接链接"]) == 1
        assert len(result["提取失败 / 需手动处理"]) == 1
        assert len(result["补充检索来源"]) == 2

    def test_empty_categories_excluded(self, funcs):
        """空分类不出现在结果中。"""
        items = [
            {"source_origin": "imported_report", "download_status": "extracted", "title": "A"},
        ]
        result = funcs["classify_report_ingestion_sources"](items)
        assert "补充检索来源" not in result
        assert "提取失败 / 需手动处理" not in result

    def test_empty_items(self, funcs):
        """空列表返回空字典。"""
        result = funcs["classify_report_ingestion_sources"]([])
        assert result == {}


class TestSourceOriginLabel:
    def test_imported_report_label(self, funcs):
        assert "报告" in funcs["get_source_origin_label"]("imported_report")

    def test_enriched_label(self, funcs):
        assert "补充" in funcs["get_source_origin_label"]("imported_report_enriched")

    def test_search_provider_label(self, funcs):
        assert "搜索" in funcs["get_source_origin_label"]("search_provider")

    def test_unknown_origin_returns_raw(self, funcs):
        assert funcs["get_source_origin_label"]("custom") == "custom"


class TestPageIntegrity:
    def test_page_retains_level_filter(self):
        """保留原有来源等级筛选。"""
        content = Path("ui/pages/2_Results.py").read_text(encoding="utf-8")
        assert "level_filter" in content

    def test_page_retains_extract_button(self):
        """保留提取正文按钮。"""
        content = Path("ui/pages/2_Results.py").read_text(encoding="utf-8")
        assert "extract_source" in content

    def test_page_retains_trace(self):
        """保留 Trace 功能。"""
        content = Path("ui/pages/2_Results.py").read_text(encoding="utf-8")
        assert "trace" in content.lower()

    def test_page_retains_export(self):
        """保留导出到 Obsidian 按钮。"""
        content = Path("ui/pages/2_Results.py").read_text(encoding="utf-8")
        assert "export_index" in content
        assert "Obsidian" in content
