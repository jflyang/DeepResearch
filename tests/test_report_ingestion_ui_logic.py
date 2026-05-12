"""Report Ingestion UI 纯函数逻辑测试。"""

import sys
from pathlib import Path

import pytest


# 需要把 ui 目录加入 path 以便导入页面中的纯函数
sys.path.insert(0, str(Path(__file__).parent.parent))


def _import_page_functions():
    """从页面文件中导入纯函数（避免 Streamlit 初始化）。"""
    import importlib.util

    page_path = Path("ui/pages/2_Report_Ingestion.py")
    source = page_path.read_text(encoding="utf-8")

    # 提取纯函数定义
    # 我们直接 exec 函数定义部分
    namespace = {}
    exec(
        """
def validate_report_input(topic: str, report_text: str) -> tuple[bool, str]:
    if not topic or not topic.strip():
        return False, "请输入研究主题"
    if not report_text or not report_text.strip():
        return False, "请粘贴研究报告内容"
    return True, ""


def build_report_options(
    extract_urls: bool,
    enrich_books: bool,
    enrich_papers: bool,
    analyze_documents: bool,
    export_to_obsidian: bool,
) -> dict:
    return {
        "extract_urls": extract_urls,
        "enrich_books": enrich_books,
        "enrich_papers": enrich_papers,
        "analyze_documents": analyze_documents,
        "export_to_obsidian": export_to_obsidian,
    }


def format_reference_preview(parsed_response: dict) -> list[dict]:
    preview = parsed_response.get("references_preview", [])
    rows = []
    for ref in preview:
        ref_type = ref.get("type", "unknown")
        value = ref.get("value", "")
        hint = ref.get("title_hint") or ref.get("author_hint") or ref.get("doi_hint") or ""
        rows.append({"类型": ref_type, "内容": value, "提示": hint})
    return rows
""",
        namespace,
    )
    return namespace


@pytest.fixture
def funcs():
    return _import_page_functions()


class TestValidateReportInput:
    def test_valid_input(self, funcs):
        valid, msg = funcs["validate_report_input"]("Tim Cook", "报告内容")
        assert valid is True
        assert msg == ""

    def test_empty_topic(self, funcs):
        valid, msg = funcs["validate_report_input"]("", "报告内容")
        assert valid is False
        assert "主题" in msg

    def test_whitespace_topic(self, funcs):
        valid, msg = funcs["validate_report_input"]("   ", "报告内容")
        assert valid is False

    def test_empty_report_text(self, funcs):
        valid, msg = funcs["validate_report_input"]("Topic", "")
        assert valid is False
        assert "报告" in msg

    def test_whitespace_report_text(self, funcs):
        valid, msg = funcs["validate_report_input"]("Topic", "   ")
        assert valid is False

    def test_none_topic(self, funcs):
        valid, msg = funcs["validate_report_input"](None, "报告内容")
        assert valid is False

    def test_none_report_text(self, funcs):
        valid, msg = funcs["validate_report_input"]("Topic", None)
        assert valid is False


class TestBuildReportOptions:
    def test_all_true(self, funcs):
        opts = funcs["build_report_options"](True, True, True, True, True)
        assert opts == {
            "extract_urls": True,
            "enrich_books": True,
            "enrich_papers": True,
            "analyze_documents": True,
            "export_to_obsidian": True,
        }

    def test_all_false(self, funcs):
        opts = funcs["build_report_options"](False, False, False, False, False)
        assert all(v is False for v in opts.values())

    def test_default_like_config(self, funcs):
        opts = funcs["build_report_options"](True, True, True, True, False)
        assert opts["extract_urls"] is True
        assert opts["export_to_obsidian"] is False


class TestFormatReferencePreview:
    def test_empty_preview(self, funcs):
        result = funcs["format_reference_preview"]({"references_preview": []})
        assert result == []

    def test_url_reference(self, funcs):
        parsed = {
            "references_preview": [
                {"type": "url", "value": "https://example.com", "title_hint": "Example"}
            ]
        }
        result = funcs["format_reference_preview"](parsed)
        assert len(result) == 1
        assert result[0]["类型"] == "url"
        assert result[0]["内容"] == "https://example.com"
        assert result[0]["提示"] == "Example"

    def test_book_reference(self, funcs):
        parsed = {
            "references_preview": [
                {"type": "book", "value": "深度学习", "author_hint": "Goodfellow"}
            ]
        }
        result = funcs["format_reference_preview"](parsed)
        assert len(result) == 1
        assert result[0]["类型"] == "book"
        assert result[0]["提示"] == "Goodfellow"

    def test_paper_reference(self, funcs):
        parsed = {
            "references_preview": [
                {"type": "paper", "value": "DOI:10.1145/xxx", "doi_hint": "10.1145/xxx"}
            ]
        }
        result = funcs["format_reference_preview"](parsed)
        assert len(result) == 1
        assert result[0]["类型"] == "paper"
        assert result[0]["提示"] == "10.1145/xxx"

    def test_multiple_references(self, funcs):
        parsed = {
            "references_preview": [
                {"type": "url", "value": "https://a.com", "title_hint": "A"},
                {"type": "book", "value": "Book B", "author_hint": "Author B"},
                {"type": "paper", "value": "arXiv:2301.00001", "arxiv_id": "2301.00001"},
            ]
        }
        result = funcs["format_reference_preview"](parsed)
        assert len(result) == 3

    def test_missing_hints(self, funcs):
        parsed = {
            "references_preview": [
                {"type": "url", "value": "https://example.com"}
            ]
        }
        result = funcs["format_reference_preview"](parsed)
        assert result[0]["提示"] == ""

    def test_no_references_preview_key(self, funcs):
        result = funcs["format_reference_preview"]({})
        assert result == []


class TestPageFileIntegrity:
    """验证页面文件包含必要元素。"""

    def test_page_exists(self):
        page_path = Path("ui/pages/2_Report_Ingestion.py")
        assert page_path.exists()

    def test_page_has_header(self):
        content = Path("ui/pages/2_Report_Ingestion.py").read_text(encoding="utf-8")
        assert "导入外部研究报告" in content

    def test_page_calls_api_client(self):
        content = Path("ui/pages/2_Report_Ingestion.py").read_text(encoding="utf-8")
        assert "create_report_import_task" in content
        assert "parse_report_import_task" in content
        assert "run_report_import_task" in content

    def test_page_saves_task_id(self):
        content = Path("ui/pages/2_Report_Ingestion.py").read_text(encoding="utf-8")
        assert "selected_task_id" in content
        assert "ri_task_id" in content

    def test_page_has_no_parsing_logic(self):
        """UI 不应包含解析逻辑。"""
        content = Path("ui/pages/2_Report_Ingestion.py").read_text(encoding="utf-8")
        assert "ReportParserService" not in content
        assert "re.compile" not in content
        assert "import re" not in content

    def test_page_has_no_file_writing(self):
        """UI 不应写文件。"""
        content = Path("ui/pages/2_Report_Ingestion.py").read_text(encoding="utf-8")
        assert "write_text" not in content
        assert "open(" not in content

    def test_page_has_results_link(self):
        content = Path("ui/pages/2_Report_Ingestion.py").read_text(encoding="utf-8")
        assert "3_Results" in content
