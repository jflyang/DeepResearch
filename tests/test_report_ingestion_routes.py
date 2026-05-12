"""外部报告导入 API 路由测试。"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.tables import Base


@pytest.fixture
def db_session_and_engine(tmp_path):
    """创建临时 SQLite 数据库。"""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session, engine


@pytest.fixture
def client(db_session_and_engine, tmp_path):
    """创建 TestClient，mock 掉 DB session 和 service。"""
    Session, engine = db_session_and_engine

    def _mock_get_session():
        return Session()

    def _mock_init_db():
        pass

    # Mock get_session 和 init_db
    with patch("db.session.get_session", _mock_get_session), \
         patch("db.session.init_db", _mock_init_db), \
         patch("app.api.routes_report_ingestion.get_session", _mock_get_session):
        from app.main import app
        yield TestClient(app)


SAMPLE_REPORT_TEXT = """
# Tim Cook 研究报告

根据 [Forbes Profile](https://forbes.com/profile/tim-cook) 的报道，
Tim Cook 于 1960 年出生于阿拉巴马州。

在《蒂姆·库克传》中详细描述了他的早期经历。

参考论文 arXiv:1706.03762 的方法。
"""


class TestCreateImportReport:
    def test_create_returns_task_id(self, client):
        """create 返回 task_id。"""
        response = client.post("/research/import-report", json={
            "topic": "Tim Cook 研究",
            "report_text": SAMPLE_REPORT_TEXT,
            "report_source": "ChatGPT",
            "output_language": "zh",
        })
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert data["task_type"] == "report_ingestion"

    def test_create_empty_report_text_fails(self, client):
        """空 report_text 返回 422。"""
        response = client.post("/research/import-report", json={
            "topic": "Test",
            "report_text": "",
        })
        assert response.status_code == 422


class TestParseImportReport:
    def test_parse_returns_counts(self, client):
        """parse 返回 url_count/book_count/paper_count。"""
        # 先创建任务
        create_resp = client.post("/research/import-report", json={
            "topic": "Tim Cook 研究",
            "report_text": SAMPLE_REPORT_TEXT,
        })
        task_id = create_resp.json()["task_id"]

        # 解析
        response = client.post(f"/research/import-report/{task_id}/parse")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["url_count"] >= 1
        assert data["book_count"] >= 1
        assert data["paper_count"] >= 1

    def test_parse_nonexistent_task_returns_404(self, client):
        """task 不存在返回 404。"""
        response = client.post("/research/import-report/nonexistent-id/parse")
        assert response.status_code == 404

    def test_parse_non_ingestion_task_returns_400(self, client, db_session_and_engine):
        """非 report_ingestion task 调 parse 返回 400。"""
        Session, _ = db_session_and_engine
        from db.repositories import TaskRepository

        # 创建普通 search_research 任务
        session = Session()
        try:
            repo = TaskRepository(session)
            repo.create_task(task_id="search-task-001", topic="普通搜索任务")
        finally:
            session.close()

        response = client.post("/research/import-report/search-task-001/parse")
        assert response.status_code == 400
        assert "not a report_ingestion" in response.json()["detail"]


class TestRunImportReport:
    def test_run_returns_result(self, client):
        """run 返回 completed/result。"""
        # 创建任务
        create_resp = client.post("/research/import-report", json={
            "topic": "Test",
            "report_text": "参考 [Link](https://example.com/page) 的内容",
        })
        task_id = create_resp.json()["task_id"]

        # Mock extraction service 和 search router
        mock_service = AsyncMock()
        mock_service.run_import_task = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {
                "task_id": task_id,
                "parsed_url_count": 1,
                "parsed_book_count": 0,
                "parsed_paper_count": 0,
                "extracted_document_count": 1,
                "enriched_source_count": 0,
                "enriched_book_count": 0,
                "enriched_paper_count": 0,
                "failed_count": 0,
                "source_count": 1,
                "exported_path": None,
            }
        ))

        with patch(
            "app.api.routes_report_ingestion._get_ingestion_service",
            return_value=mock_service,
        ):
            response = client.post(f"/research/import-report/{task_id}/run")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["source_count"] >= 0

    def test_run_nonexistent_task_returns_404(self, client):
        """task 不存在返回 404。"""
        response = client.post("/research/import-report/nonexistent/run")
        assert response.status_code == 404


class TestGetImportedReport:
    def test_get_imported_report(self, client):
        """获取导入报告详情。"""
        # 创建任务
        create_resp = client.post("/research/import-report", json={
            "topic": "Test Report",
            "report_text": "A" * 600,
            "report_source": "Perplexity",
        })
        task_id = create_resp.json()["task_id"]

        response = client.get(f"/research/tasks/{task_id}/imported-report")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["report_source"] == "Perplexity"
        # 默认不返回完整文本（截断到 500）
        assert len(data["report_text_preview"]) <= 503  # 500 + "..."
        assert data["status"] == "pending"

    def test_get_nonexistent_returns_404(self, client):
        """task 不存在返回 404。"""
        response = client.get("/research/tasks/nonexistent/imported-report")
        assert response.status_code == 404
