"""外部报告导入 Obsidian 导出测试。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from models.enums import DownloadStatus, ResearchTaskType, SourceLevel, SourceType, TaskStatus
from models.schemas import ResearchTask, SourceItem
from services.markdown_service import (
    export_imported_report,
    export_report_ingestion_index,
    export_research_index,
)


@pytest.fixture
def vault_dir(tmp_path):
    """临时 vault 目录。"""
    return tmp_path / "vault"


@pytest.fixture
def report_ingestion_task():
    """report_ingestion 类型任务。"""
    return ResearchTask(
        id="ri-test-001",
        task_type=ResearchTaskType.REPORT_INGESTION,
        topic="Tim Cook 研究",
        status=TaskStatus.COMPLETED,
        created_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def search_research_task():
    """普通 search_research 类型任务。"""
    return ResearchTask(
        id="sr-test-001",
        topic="OpenAI 宫斗",
        status=TaskStatus.COMPLETED,
        created_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_sources():
    """示例来源列表。"""
    return [
        SourceItem(
            id="s1",
            task_id="ri-test-001",
            title="Forbes Tim Cook Profile",
            url="https://forbes.com/profile/tim-cook",
            domain="forbes.com",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.A,
            source_origin="imported_report",
            download_status=DownloadStatus.EXTRACTED,
        ),
        SourceItem(
            id="s2",
            task_id="ri-test-001",
            title="Tim Cook Book - Open Library",
            url="https://openlibrary.org/works/tim-cook",
            domain="openlibrary.org",
            source_type=SourceType.BOOK,
            source_level=SourceLevel.B,
            source_origin="imported_report_enriched",
            download_status=DownloadStatus.PENDING,
        ),
        SourceItem(
            id="s3",
            task_id="ri-test-001",
            title="Failed Source",
            url="https://example.com/broken",
            domain="example.com",
            source_type=SourceType.WEB,
            source_level=SourceLevel.C,
            source_origin="imported_report",
            download_status=DownloadStatus.FAILED,
        ),
    ]


SAMPLE_REPORT_TEXT = """# Tim Cook 研究报告

根据 Forbes 的报道，Tim Cook 于 1960 年出生于阿拉巴马州。

在《蒂姆·库克传》中详细描述了他的早期经历。

参考论文 arXiv:1706.03762 的方法。
"""


class TestExportImportedReport:
    def test_imported_report_md_exists(self, vault_dir, report_ingestion_task):
        """report_ingestion task 导出后存在 imported_report.md。"""
        path = export_imported_report(
            task=report_ingestion_task,
            report_text=SAMPLE_REPORT_TEXT,
            report_source="ChatGPT",
            vault_path=vault_dir,
        )
        assert path.exists()
        assert path.name == "imported_report.md"

    def test_imported_report_contains_report_text(self, vault_dir, report_ingestion_task):
        """imported_report.md 包含原始报告文本。"""
        export_imported_report(
            task=report_ingestion_task,
            report_text=SAMPLE_REPORT_TEXT,
            report_source="ChatGPT",
            vault_path=vault_dir,
        )
        research_dir = vault_dir / "Research" / "Tim_Cook_研究"
        report_path = research_dir / "imported_report.md"
        content = report_path.read_text(encoding="utf-8")

        assert "Tim Cook 研究报告" in content
        assert "1960 年出生于阿拉巴马州" in content
        assert "蒂姆·库克传" in content

    def test_imported_report_has_frontmatter(self, vault_dir, report_ingestion_task):
        """imported_report.md 包含 frontmatter。"""
        path = export_imported_report(
            task=report_ingestion_task,
            report_text=SAMPLE_REPORT_TEXT,
            report_source="Perplexity",
            vault_path=vault_dir,
        )
        content = path.read_text(encoding="utf-8")
        assert "---" in content
        assert "type: imported_report" in content
        assert 'source: "Perplexity"' in content
        assert f'task_id: "{report_ingestion_task.id}"' in content

    def test_imported_report_with_parsed_summary(self, vault_dir, report_ingestion_task):
        """imported_report.md 包含解析出的引用。"""
        parsed_summary = {
            "urls": [{"url": "https://example.com", "title_hint": "Example"}],
            "books": [{"title": "深度学习", "author_hint": "Goodfellow"}],
            "papers": [{"title": "Transformer", "doi_hint": "10.1145/xxx", "arxiv_id": None}],
        }
        path = export_imported_report(
            task=report_ingestion_task,
            report_text=SAMPLE_REPORT_TEXT,
            report_source="Claude",
            parsed_summary=parsed_summary,
            vault_path=vault_dir,
        )
        content = path.read_text(encoding="utf-8")
        assert "## URLs" in content
        assert "## Books" in content
        assert "## Papers" in content
        assert "https://example.com" in content
        assert "深度学习" in content


class TestExportReportIngestionIndex:
    def test_index_contains_external_report_section(
        self, vault_dir, report_ingestion_task, sample_sources
    ):
        """index.md 包含"外部报告来源"。"""
        path = export_report_ingestion_index(
            task=report_ingestion_task,
            sources=sample_sources,
            report_source="ChatGPT",
            parsed_url_count=5,
            parsed_book_count=2,
            parsed_paper_count=1,
            vault_path=vault_dir,
        )
        content = path.read_text(encoding="utf-8")
        assert "## 外部报告来源" in content
        assert "ChatGPT" in content
        assert "解析 URL 数量：5" in content
        assert "解析书籍数量：2" in content
        assert "解析论文数量：1" in content

    def test_index_contains_direct_links(
        self, vault_dir, report_ingestion_task, sample_sources
    ):
        """index.md 包含报告中直接链接。"""
        path = export_report_ingestion_index(
            task=report_ingestion_task,
            sources=sample_sources,
            report_source="ChatGPT",
            vault_path=vault_dir,
        )
        content = path.read_text(encoding="utf-8")
        assert "## 报告中直接链接" in content
        assert "forbes.com" in content

    def test_index_contains_enriched_sources(
        self, vault_dir, report_ingestion_task, sample_sources
    ):
        """index.md 包含补充检索来源。"""
        path = export_report_ingestion_index(
            task=report_ingestion_task,
            sources=sample_sources,
            report_source="ChatGPT",
            vault_path=vault_dir,
        )
        content = path.read_text(encoding="utf-8")
        assert "## 补充检索来源" in content
        assert "openlibrary" in content


class TestSearchResearchNotAffected:
    def test_normal_task_no_imported_report_md(
        self, vault_dir, search_research_task
    ):
        """普通 search_research task 不生成 imported_report.md。"""
        # 使用普通导出
        sources = [
            SourceItem(
                id="s-normal",
                task_id="sr-test-001",
                title="Normal Source",
                url="https://example.com",
                domain="example.com",
            )
        ]
        export_research_index(
            task=search_research_task,
            sources=sources,
            extracted_docs={},
            vault_path=vault_dir,
        )

        research_dir = vault_dir / "Research" / "OpenAI_宫斗"
        # index.md 应该存在
        assert (research_dir / "index.md").exists()
        # imported_report.md 不应该存在
        assert not (research_dir / "imported_report.md").exists()
