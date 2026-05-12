"""UI Vault 路径解析逻辑测试。

测试 resolve_task_obsidian_path 函数：根据 Settings 中的 Obsidian 配置，
决定新建任务时使用的 vault_path。
"""

import pytest


def resolve_task_obsidian_path(obsidian_settings: dict) -> tuple[str | None, str]:
    """根据 Obsidian 配置决定任务使用的 vault_path。

    Args:
        obsidian_settings: GET /settings/obsidian 返回的字典

    Returns:
        (vault_path, status_message)
        - vault_path: 可用路径或 None
        - status_message: 状态描述
    """
    configured = obsidian_settings.get("configured", False)
    exists = obsidian_settings.get("exists", False)
    writable = obsidian_settings.get("writable", False)
    vault_path = obsidian_settings.get("vault_path", "")

    if not configured:
        return None, "未配置默认 Vault。研究可以运行，但导出功能不可用。"

    if not exists:
        return None, f"默认 Vault 路径不存在：{vault_path}"

    if not writable:
        return None, f"默认 Vault 路径不可写：{vault_path}"

    return vault_path, f"默认 Vault 可用：{vault_path}"


class TestResolveTaskObsidianPath:
    """resolve_task_obsidian_path 逻辑测试。"""

    def test_configured_exists_writable_returns_path(self):
        """configured=true exists=true writable=true → 返回 vault_path。"""
        settings = {
            "vault_path": "/Users/me/Obsidian/ResearchVault",
            "configured": True,
            "exists": True,
            "writable": True,
        }
        path, msg = resolve_task_obsidian_path(settings)
        assert path == "/Users/me/Obsidian/ResearchVault"
        assert "可用" in msg

    def test_not_configured_returns_none_with_warning(self):
        """configured=false → 返回 None 和 warning。"""
        settings = {
            "vault_path": "",
            "configured": False,
            "exists": False,
            "writable": False,
        }
        path, msg = resolve_task_obsidian_path(settings)
        assert path is None
        assert "未配置" in msg

    def test_configured_not_exists_returns_none(self):
        """configured=true exists=false → 返回 None 和 warning。"""
        settings = {
            "vault_path": "/nonexistent/path",
            "configured": True,
            "exists": False,
            "writable": False,
        }
        path, msg = resolve_task_obsidian_path(settings)
        assert path is None
        assert "不存在" in msg

    def test_configured_not_writable_returns_none(self):
        """configured=true writable=false → 返回 None 和 warning。"""
        settings = {
            "vault_path": "/readonly/path",
            "configured": True,
            "exists": True,
            "writable": False,
        }
        path, msg = resolve_task_obsidian_path(settings)
        assert path is None
        assert "不可写" in msg

    def test_task_payload_uses_settings_path(self):
        """新建任务 payload 中 obsidian_path 使用 Settings 默认路径。"""
        settings = {
            "vault_path": "/Users/me/Obsidian/ResearchVault",
            "configured": True,
            "exists": True,
            "writable": True,
        }
        path, _ = resolve_task_obsidian_path(settings)

        # 模拟构造任务 payload
        payload = {
            "topic": "库克的童年故事",
            "mode": "person",
            "depth": "standard",
            "obsidian_path": path or "",
        }
        assert payload["obsidian_path"] == "/Users/me/Obsidian/ResearchVault"

    def test_unconfigured_vault_still_allows_task(self):
        """未配置 Vault 时仍允许构造任务 payload。"""
        settings = {
            "vault_path": "",
            "configured": False,
            "exists": False,
            "writable": False,
        }
        path, _ = resolve_task_obsidian_path(settings)

        # 模拟构造任务 payload
        payload = {
            "topic": "库克的童年故事",
            "mode": "person",
            "depth": "standard",
            "obsidian_path": path or "",
        }
        # 任务仍可创建，obsidian_path 为空
        assert payload["obsidian_path"] == ""
        assert payload["topic"] == "库克的童年故事"

    def test_empty_settings_dict(self):
        """空字典 → 返回 None。"""
        path, msg = resolve_task_obsidian_path({})
        assert path is None
        assert "未配置" in msg


class TestSettingsAPIObsidian:
    """Settings API Obsidian 端点测试（使用 FastAPI TestClient）。"""

    @pytest.fixture
    def test_client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_get_obsidian_unconfigured(self, test_client, monkeypatch):
        """GET /settings/obsidian 未配置时 configured=false。"""
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "")
        # Also ensure runtime_settings doesn't have obsidian configured
        from unittest.mock import patch
        from core.config import reset_settings
        with patch("core.config._load_runtime_settings", return_value={}):
            reset_settings()
            response = test_client.get("/settings/obsidian")
            assert response.status_code == 200
            data = response.json()
            assert data["configured"] is False

    def test_save_obsidian_valid_path(self, test_client, tmp_path):
        """POST /settings/obsidian/save 对 tmp_path 成功。"""
        from core.config import reset_settings, save_runtime_settings, _load_runtime_settings

        # 保存当前状态以便恢复
        runtime = _load_runtime_settings()
        original_obsidian = runtime.get("obsidian")

        try:
            response = test_client.post(
                "/settings/obsidian/save",
                json={"vault_path": str(tmp_path)},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
        finally:
            # 恢复原始状态
            if original_obsidian is None:
                # 删除 obsidian key
                runtime = _load_runtime_settings()
                runtime.pop("obsidian", None)
                import json
                from pathlib import Path
                settings_path = Path("config/runtime_settings.json")
                if settings_path.exists():
                    with open(settings_path, "w", encoding="utf-8") as f:
                        json.dump(runtime, f, indent=2, ensure_ascii=False)
            else:
                save_runtime_settings("obsidian", original_obsidian)
            reset_settings()

    def test_save_obsidian_nonexistent_path(self, test_client):
        """不存在路径保存失败。"""
        response = test_client.post(
            "/settings/obsidian/save",
            json={"vault_path": "/this/path/does/not/exist/at/all"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "不存在" in data["message"]

    def test_test_obsidian_valid_path(self, test_client, tmp_path):
        """POST /settings/obsidian/test 对有效路径返回 exists=true。"""
        response = test_client.post(
            "/settings/obsidian/test",
            json={"vault_path": str(tmp_path)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["writable"] is True
        assert data["error"] is None

    def test_test_obsidian_invalid_path(self, test_client):
        """POST /settings/obsidian/test 对无效路径返回 exists=false。"""
        response = test_client.post(
            "/settings/obsidian/test",
            json={"vault_path": "/nonexistent/path/xyz"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["error"] is not None
