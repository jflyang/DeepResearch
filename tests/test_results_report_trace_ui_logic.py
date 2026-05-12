"""Results 页面 Report Ingestion Trace UI 纯函数测试。"""

import pytest


# === Pure functions to test ===

def group_report_ingestion_trace_events(events: list[dict]) -> dict[str, list[dict]]:
    """将 report ingestion trace events 按阶段分组。"""
    sections = {
        "报告解析": [],
        "LLM 增强": [],
        "引用合并": [],
        "URL 抓取": [],
        "书籍/论文补充检索": [],
        "导出": [],
        "其他": [],
    }

    step_to_section = {
        "report_parse_started": "报告解析",
        "report_parse_finished": "报告解析",
        "report_parse_failed": "报告解析",
        "report_understanding_started": "LLM 增强",
        "report_understanding_finished": "LLM 增强",
        "report_understanding_fallback": "LLM 增强",
        "report_reference_extraction_started": "LLM 增强",
        "report_reference_extraction_finished": "LLM 增强",
        "report_reference_extraction_fallback": "LLM 增强",
        "llm_enhancement_skipped": "LLM 增强",
        "reference_merge_finished": "引用合并",
        "url_extraction_started": "URL 抓取",
        "url_extraction_finished": "URL 抓取",
        "imported_url_extraction_failed": "URL 抓取",
        "book_enrichment_started": "书籍/论文补充检索",
        "book_enrichment_finished": "书籍/论文补充检索",
        "paper_enrichment_started": "书籍/论文补充检索",
        "paper_enrichment_finished": "书籍/论文补充检索",
        "imported_report_export_started": "导出",
        "imported_report_export_finished": "导出",
    }

    for event in events:
        step = event.get("step", "")
        section = step_to_section.get(step, "其他")
        sections[section].append(event)

    return {k: v for k, v in sections.items() if v}


def build_report_trace_summary(events: list[dict]) -> dict:
    """从 trace events 构建 report ingestion 摘要。"""
    summary = {
        "parse_url_count": 0,
        "parse_book_count": 0,
        "parse_paper_count": 0,
        "llm_used": False,
        "llm_skipped_reason": None,
        "url_extracted": 0,
        "url_failed": 0,
        "enriched_count": 0,
    }

    for event in events:
        step = event.get("step", "")
        output = event.get("output_summary") or {}

        if step == "report_parse_finished":
            summary["parse_url_count"] = output.get("url_count", 0)
            summary["parse_book_count"] = output.get("book_count", 0)
            summary["parse_paper_count"] = output.get("paper_count", 0)
        elif step == "report_understanding_finished":
            if output.get("status") == "used_llm":
                summary["llm_used"] = True
        elif step == "llm_enhancement_skipped":
            summary["llm_skipped_reason"] = "LLM 不可用"
        elif step == "url_extraction_finished":
            summary["url_extracted"] = output.get("extracted_count", 0)
            summary["url_failed"] = output.get("failed_count", 0)
        elif step in ("book_enrichment_finished", "paper_enrichment_finished"):
            summary["enriched_count"] += output.get("enriched_count", 0)

    return summary


def format_report_trace_status(event: dict) -> str:
    """格式化单个 trace event 的状态 badge。"""
    step = event.get("step", "")
    output = event.get("output_summary") or {}
    level = event.get("level", "info")

    if level == "error":
        return "❌ 失败"
    if "failed" in step or "fallback" in step:
        return "⚠️ 部分失败"
    if "skipped" in step:
        return "⏭️ 跳过"
    if output.get("status") == "used_llm":
        return "🤖 使用 LLM"
    if "finished" in step:
        return "✅ 成功"
    if "started" in step:
        return "⏳ 进行中"
    return "⚙️ 规则逻辑"


def get_report_trace_sections(task_type: str) -> list[str]:
    """根据 task_type 返回应显示的 trace sections。"""
    if task_type == "report_ingestion":
        return [
            "报告解析",
            "LLM 增强",
            "引用合并",
            "URL 抓取",
            "书籍/论文补充检索",
            "导出",
        ]
    else:
        return [
            "主题理解",
            "语言规划",
            "查询扩展",
            "搜索",
            "去重与评分",
            "提取",
            "导出",
        ]


# === Tests ===


class TestGroupReportIngestionTraceEvents:
    def test_report_ingestion_sections(self):
        """report_ingestion task 显示 Report Ingestion sections。"""
        events = [
            {"step": "report_parse_started", "message": "开始"},
            {"step": "report_parse_finished", "message": "完成", "output_summary": {"url_count": 5}},
            {"step": "report_understanding_finished", "message": "LLM", "output_summary": {"status": "used_llm"}},
            {"step": "url_extraction_started", "message": "URL"},
            {"step": "url_extraction_finished", "message": "done", "output_summary": {"extracted_count": 3}},
        ]
        grouped = group_report_ingestion_trace_events(events)
        assert "报告解析" in grouped
        assert "LLM 增强" in grouped
        assert "URL 抓取" in grouped

    def test_search_research_sections(self):
        """search_research task 显示普通 Research sections。"""
        sections = get_report_trace_sections("search_research")
        assert "主题理解" in sections
        assert "搜索" in sections
        assert "报告解析" not in sections


class TestBuildReportTraceSummary:
    def test_parse_counts(self):
        events = [
            {"step": "report_parse_finished", "output_summary": {"url_count": 10, "book_count": 3, "paper_count": 2}},
        ]
        summary = build_report_trace_summary(events)
        assert summary["parse_url_count"] == 10
        assert summary["parse_book_count"] == 3
        assert summary["parse_paper_count"] == 2

    def test_llm_used(self):
        events = [
            {"step": "report_understanding_finished", "output_summary": {"status": "used_llm"}},
        ]
        summary = build_report_trace_summary(events)
        assert summary["llm_used"] is True

    def test_llm_skipped(self):
        events = [
            {"step": "llm_enhancement_skipped", "message": "LLM 不可用"},
        ]
        summary = build_report_trace_summary(events)
        assert summary["llm_used"] is False
        assert summary["llm_skipped_reason"] is not None

    def test_url_extraction_counts(self):
        events = [
            {"step": "url_extraction_finished", "output_summary": {"extracted_count": 8, "failed_count": 2}},
        ]
        summary = build_report_trace_summary(events)
        assert summary["url_extracted"] == 8
        assert summary["url_failed"] == 2


class TestFormatReportTraceStatus:
    def test_url_extraction_failed(self):
        """URL extraction failed 被标记为失败。"""
        event = {"step": "imported_url_extraction_failed", "level": "error"}
        assert "失败" in format_report_trace_status(event)

    def test_llm_skipped(self):
        """LLM skipped 显示跳过。"""
        event = {"step": "llm_enhancement_skipped", "level": "info"}
        assert "跳过" in format_report_trace_status(event)

    def test_llm_used(self):
        """LLM used 显示 LLM badge。"""
        event = {"step": "report_understanding_finished", "output_summary": {"status": "used_llm"}}
        assert "LLM" in format_report_trace_status(event)

    def test_success(self):
        event = {"step": "url_extraction_finished", "level": "info", "output_summary": {}}
        assert "成功" in format_report_trace_status(event)


class TestGetReportTraceSections:
    def test_report_ingestion_has_correct_sections(self):
        sections = get_report_trace_sections("report_ingestion")
        assert "报告解析" in sections
        assert "LLM 增强" in sections
        assert "URL 抓取" in sections
        assert "书籍/论文补充检索" in sections

    def test_search_research_has_correct_sections(self):
        sections = get_report_trace_sections("search_research")
        assert "搜索" in sections
        assert "报告解析" not in sections
