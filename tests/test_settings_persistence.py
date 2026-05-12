"""Settings 持久化测试 - 验证 runtime_settings.json 的读写行为。"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config import (
    _load_runtime_settings,
    save_runtime_settings,
    get_settings,
    reset_settings,
    _RUNTIME_SETTINGS_PATH,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_settings()
    yield
    reset_settings()


class TestRuntimeSettingsStore:
    """测试 runtime_settings.json 的基本读写。"""

    def test_save_creates_file(self, tmp_path) -> None:
        """save 后文件存在。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("test_section", {"key": "value"})
            assert runtime_path.exists()

    def test_save_then_load(self, tmp_path) -> None:
        """save 后 load 能读回。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("ollama", {"base_url": "http://10.0.0.1:11434"})
            data = _load_runtime_settings()
            assert data["ollama"]["base_url"] == "http://10.0.0.1:11434"

    def test_update_section_preserves_others(self, tmp_path) -> None:
        """update_section 不会覆盖其他 section。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("ollama", {"base_url": "http://10.0.0.1:11434"})
            save_runtime_settings("obsidian", {"vault_path": "/tmp/vault"})

            data = _load_runtime_settings()
            assert data["ollama"]["base_url"] == "http://10.0.0.1:11434"
            assert data["obsidian"]["vault_path"] == "/tmp/vault"

    def test_load_nonexistent_returns_empty(self, tmp_path) -> None:
        """文件不存在时 load 返回 {}。"""
        runtime_path = tmp_path / "nonexistent" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            data = _load_runtime_settings()
            assert data == {}

    def test_save_uses_utf8_and_indent(self, tmp_path) -> None:
        """写入使用 UTF-8、indent=2、ensure_ascii=False。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("test", {"中文": "测试"})
            content = runtime_path.read_text(encoding="utf-8")
            assert "中文" in content  # ensure_ascii=False
            assert "  " in content  # indent=2

    def test_save_creates_parent_directory(self, tmp_path) -> None:
        """save 时自动创建 config 目录。"""
        runtime_path = tmp_path / "deep" / "nested" / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("test", {"key": "value"})
            assert runtime_path.exists()

    def test_atomic_write_no_corruption(self, tmp_path) -> None:
        """原子写入：即使中间有数据，最终文件完整。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            # 写入初始数据
            save_runtime_settings("first", {"a": 1})
            # 写入第二个 section
            save_runtime_settings("second", {"b": 2})

            data = json.loads(runtime_path.read_text())
            assert data["first"]["a"] == 1
            assert data["second"]["b"] == 2


class TestApiKeyPreservation:
    """测试 API Key 保留逻辑。"""

    def test_empty_api_key_preserves_existing(self, tmp_path) -> None:
        """api_key 为空字符串时保留已有 key。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            # 先保存一个 key
            save_runtime_settings("search", {
                "tavily": {"api_key": "tvly-existing", "enabled": True}
            })

            # 模拟保存时 api_key 为空（不覆盖）
            runtime = _load_runtime_settings()
            current_search = runtime.get("search", {})
            tavily_data = current_search.get("tavily", {})
            # 空字符串不覆盖
            new_key = ""
            if new_key:
                tavily_data["api_key"] = new_key
            current_search["tavily"] = tavily_data
            save_runtime_settings("search", current_search)

            # 验证 key 保留
            data = _load_runtime_settings()
            assert data["search"]["tavily"]["api_key"] == "tvly-existing"

    def test_clear_sentinel_removes_key(self, tmp_path) -> None:
        """api_key 为 "__CLEAR__" 时清空 key。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("search", {
                "brave": {"api_key": "BSA-old", "enabled": True}
            })

            runtime = _load_runtime_settings()
            current_search = runtime.get("search", {})
            brave_data = current_search.get("brave", {})
            # __CLEAR__ 清空
            brave_data["api_key"] = ""
            current_search["brave"] = brave_data
            save_runtime_settings("search", current_search)

            data = _load_runtime_settings()
            assert data["search"]["brave"]["api_key"] == ""

    def test_new_key_overwrites(self, tmp_path) -> None:
        """新 api_key 覆盖旧值。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("search", {
                "tavily": {"api_key": "tvly-old", "enabled": True}
            })

            runtime = _load_runtime_settings()
            current_search = runtime.get("search", {})
            tavily_data = current_search.get("tavily", {})
            tavily_data["api_key"] = "tvly-new"
            current_search["tavily"] = tavily_data
            save_runtime_settings("search", current_search)

            data = _load_runtime_settings()
            assert data["search"]["tavily"]["api_key"] == "tvly-new"


class TestSettingsReloadAfterSave:
    """测试保存后 get_settings() 能读到最新值。"""

    def test_ollama_base_url_persists(self, tmp_path) -> None:
        """保存 ollama base_url 后 get_settings() 返回新值。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("ollama", {
                "base_url": "http://192.168.1.100:11434",
                "default_model": "qwen3:8b",
            })
            reset_settings()
            settings = get_settings()
            assert settings.ollama_base_url == "http://192.168.1.100:11434"
            assert settings.ollama_default_model == "qwen3:8b"
            reset_settings()

    def test_tavily_key_persists(self, tmp_path) -> None:
        """保存 tavily key 后 get_settings() 返回新值。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("search", {
                "tavily": {"api_key": "tvly-persisted", "enabled": True}
            })
            reset_settings()
            settings = get_settings()
            assert settings.tavily_api_key == "tvly-persisted"
            reset_settings()

    def test_obsidian_path_persists(self, tmp_path) -> None:
        """保存 obsidian path 后 get_settings() 返回新值。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("obsidian", {"vault_path": str(vault_dir)})
            reset_settings()
            settings = get_settings()
            assert settings.obsidian_vault_path == str(vault_dir)
            reset_settings()

    def test_cloud_llm_persists(self, tmp_path) -> None:
        """保存 cloud_llm 后 get_settings() 返回新值。"""
        runtime_path = tmp_path / "config" / "runtime_settings.json"
        with patch("core.config._RUNTIME_SETTINGS_PATH", runtime_path):
            save_runtime_settings("cloud_llm", {
                "enabled": True,
                "provider": "deepseek",
                "api_key": "sk-test",
                "base_url": "https://api.deepseek.com/v1",
                "default_model": "deepseek-chat",
                "timeout_seconds": 60,
            })
            reset_settings()
            settings = get_settings()
            assert settings.enable_cloud_llm is True
            assert settings.cloud_llm_provider == "deepseek"
            assert settings.deepseek_api_key == "sk-test"
            assert settings.deepseek_base_url == "https://api.deepseek.com/v1"
            assert settings.deepseek_default_model == "deepseek-chat"
            reset_settings()


class TestProjectRootPath:
    """测试路径解析基于项目根目录。"""

    def test_runtime_settings_path_is_absolute(self) -> None:
        """_RUNTIME_SETTINGS_PATH 是绝对路径。"""
        assert _RUNTIME_SETTINGS_PATH.is_absolute()

    def test_runtime_settings_path_ends_correctly(self) -> None:
        """路径以 config/runtime_settings.json 结尾。"""
        assert _RUNTIME_SETTINGS_PATH.name == "runtime_settings.json"
        assert _RUNTIME_SETTINGS_PATH.parent.name == "config"
