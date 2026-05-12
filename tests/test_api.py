"""FastAPI API 层测试。"""

import pytest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# === Health ===


class TestHealth:
    def test_health_endpoint(self, client):
        response = client.get("/settings/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "providers" in data
        assert "tavily" in data["providers"]
        assert "brave" in data["providers"]
        assert "google_books" in data["providers"]
        assert "obsidian_configured" in data

    def test_health_shows_provider_status(self, client):
        response = client.get("/settings/health")
        data = response.json()
        # 没有配置 key，应该都不 available
        for provider in ("tavily", "brave"):
            assert "enabled" in data["providers"][provider]
            assert "available" in data["providers"][provider]


# === Create Task ===


class TestCreateTask:
    def test_create_task_success(self, client):
        response = client.post("/research/tasks", json={
            "topic": "Quantum Computing",
            "mode": "concept",
            "include_books": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert len(data["task_id"]) == 36  # UUID

    def test_create_task_minimal(self, client):
        response = client.post("/research/tasks", json={"topic": "Test"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"

    def test_create_task_with_all_options(self, client):
        response = client.post("/research/tasks", json={
            "topic": "Elon Musk",
            "mode": "person",
            "depth": "deep",
            "include_gossip": True,
            "include_books": True,
            "include_video": True,
            "obsidian_path": "/tmp/vault",
        })
        assert response.status_code == 200


# === Get Task ===


class TestGetTask:
    def test_get_task_success(self, client):
        # 先创建
        create_resp = client.post("/research/tasks", json={"topic": "Test"})
        task_id = create_resp.json()["task_id"]

        # 再获取
        response = client.get(f"/research/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["topic"] == "Test"
        assert data["status"] == "pending"

    def test_get_task_not_found(self, client):
        response = client.get("/research/tasks/nonexistent-id")
        assert response.status_code == 404


# === Run Research ===


class TestRunResearch:
    def test_run_not_found(self, client):
        response = client.post("/research/tasks/nonexistent/run")
        assert response.status_code == 404

    def test_run_returns_summary(self, client):
        """使用 mock providers 测试运行。"""
        # 创建任务
        create_resp = client.post("/research/tasks", json={
            "topic": "Test Topic",
            "mode": "concept",
            "include_books": False,
        })
        task_id = create_resp.json()["task_id"]

        # Mock search providers 返回空（没有 API key）
        response = client.post(f"/research/tasks/{task_id}/run")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert "total_queries" in data
        assert data["total_queries"] > 0

    def test_run_twice_fails(self, client):
        """已完成的任务不能再次运行。"""
        create_resp = client.post("/research/tasks", json={"topic": "Test"})
        task_id = create_resp.json()["task_id"]

        # 第一次运行
        client.post(f"/research/tasks/{task_id}/run")

        # 第二次运行应失败
        response = client.post(f"/research/tasks/{task_id}/run")
        assert response.status_code == 400


# === Get Sources ===


class TestGetSources:
    def test_get_sources_empty(self, client):
        create_resp = client.post("/research/tasks", json={"topic": "Test"})
        task_id = create_resp.json()["task_id"]

        response = client.get(f"/research/tasks/{task_id}/sources")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_get_sources_not_found(self, client):
        response = client.get("/research/tasks/nonexistent/sources")
        assert response.status_code == 404


# === Export Index ===


class TestExportIndex:
    def test_export_not_found(self, client):
        response = client.post("/research/tasks/nonexistent/export-index")
        assert response.status_code == 404

    def test_export_with_vault_path(self, client, tmp_path):
        create_resp = client.post("/research/tasks", json={
            "topic": "Export Test",
            "obsidian_path": str(tmp_path),
        })
        task_id = create_resp.json()["task_id"]

        response = client.post(f"/research/tasks/{task_id}/export-index")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "exported"
        assert "index_path" in data

    def test_export_without_vault_fails(self, client):
        """没有 vault 路径时报错。"""
        with patch("api.routes_export.get_settings") as mock_settings:
            mock_settings.return_value.obsidian_configured = False

            create_resp = client.post("/research/tasks", json={"topic": "No Vault"})
            task_id = create_resp.json()["task_id"]

            response = client.post(f"/research/tasks/{task_id}/export-index")
            assert response.status_code == 400


# === Error Format ===


class TestErrorFormat:
    def test_404_format(self, client):
        response = client.get("/research/tasks/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data  # FastAPI default 404


class TestGetEvents:
    def test_events_after_run(self, client):
        """运行任务后应有事件记录。"""
        create_resp = client.post("/research/tasks", json={"topic": "Events Test"})
        task_id = create_resp.json()["task_id"]
        client.post(f"/research/tasks/{task_id}/run")

        response = client.get(f"/research/tasks/{task_id}/events")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert len(data["events"]) > 0

        event_types = [e["event_type"] for e in data["events"]]
        assert "task_created" in event_types
        assert "task_completed" in event_types

    def test_events_not_found(self, client):
        response = client.get("/research/tasks/nonexistent/events")
        assert response.status_code == 404
