"""Settings 页面纯函数逻辑测试。"""

import sys
sys.path.insert(0, ".")

from ui.pages._settings_helpers import (
    build_service_display_state,
    group_services_by_type,
    get_provider_card_status,
    mask_api_key_status,
)


class TestBuildServiceDisplayState:
    def test_active_ok(self):
        svc = {"name": "DeepSeek", "type": "llm", "severity": "ok", "active": True}
        result = build_service_display_state(svc)
        assert result["status"] == "active"
        assert result["icon"] == "✅"
        assert result["label"] == "当前使用"

    def test_ok_not_active(self):
        svc = {"name": "Ollama", "type": "llm", "severity": "ok", "active": False}
        result = build_service_display_state(svc)
        assert result["status"] == "ok"
        assert result["label"] == "可用"

    def test_warning(self):
        svc = {"name": "OpenAI", "type": "llm", "severity": "warning", "active": False, "message": "缺少 API Key"}
        result = build_service_display_state(svc)
        assert result["status"] == "warning"
        assert result["icon"] == "⚠️"
        assert result["message"] == "缺少 API Key"

    def test_inactive(self):
        svc = {"name": "Brave", "type": "search", "severity": "inactive", "active": False}
        result = build_service_display_state(svc)
        assert result["status"] == "inactive"
        assert result["icon"] == "⚪"

    def test_error(self):
        svc = {"name": "Tavily", "type": "search", "severity": "error", "active": False}
        result = build_service_display_state(svc)
        assert result["status"] == "error"
        assert result["icon"] == "❌"

    def test_missing_fields(self):
        result = build_service_display_state({})
        assert result["name"] == "Unknown"
        assert result["status"] == "inactive"


class TestGroupServicesByType:
    def test_empty(self):
        result = group_services_by_type([])
        assert result == {}

    def test_groups_correctly(self):
        services = [
            {"name": "DeepSeek", "type": "llm", "severity": "ok", "active": True},
            {"name": "Ollama", "type": "llm", "severity": "ok", "active": False},
            {"name": "Tavily", "type": "search", "severity": "ok", "active": False},
            {"name": "Obsidian", "type": "storage", "severity": "ok", "active": False},
        ]
        result = group_services_by_type(services)
        assert "llm" in result
        assert "search" in result
        assert "storage" in result
        assert len(result["llm"]) == 2
        assert len(result["search"]) == 1


class TestGetProviderCardStatus:
    def test_not_enabled(self):
        result = get_provider_card_status("OpenAI", enabled=False)
        assert result["status"] == "inactive"
        assert result["label"] == "未启用"
        assert result["needs_action"] is False

    def test_active_configured(self):
        result = get_provider_card_status("DeepSeek", enabled=True, configured=True, is_active=True)
        assert result["status"] == "active"
        assert result["label"] == "当前使用"

    def test_enabled_configured_not_active(self):
        result = get_provider_card_status("Ollama", enabled=True, configured=True, is_active=False)
        assert result["status"] == "ok"
        assert result["label"] == "可用"

    def test_enabled_not_configured(self):
        result = get_provider_card_status("OpenAI", enabled=True, configured=False, api_key_set=False)
        assert result["status"] == "warning"
        assert result["needs_action"] is True
        assert "API Key" in result["action_hint"]

    def test_enabled_not_configured_key_set(self):
        result = get_provider_card_status("OpenAI", enabled=True, configured=False, api_key_set=True)
        assert result["status"] == "warning"
        assert result["needs_action"] is True


class TestMaskApiKeyStatus:
    def test_configured(self):
        result = mask_api_key_status({"api_key_configured": True})
        assert result["configured"] is True
        assert "已配置" in result["placeholder"]
        assert "✅" in result["help_text"]

    def test_not_configured(self):
        result = mask_api_key_status({"api_key_configured": False})
        assert result["configured"] is False
        assert "请输入" in result["placeholder"]
        assert "⚠️" in result["help_text"]

    def test_empty_config(self):
        result = mask_api_key_status({})
        assert result["configured"] is False


def _run_all():
    test_classes = [
        TestBuildServiceDisplayState,
        TestGroupServicesByType,
        TestGetProviderCardStatus,
        TestMaskApiKeyStatus,
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
