"""UI Design System 格式化逻辑测试。

验证 status badge、layout 组件的纯函数输出正确性。
不依赖 Streamlit 运行时。
"""

import sys
sys.path.insert(0, ".")

from ui.components.status import (
    status_badge,
    service_status_badge,
    task_status_badge,
    source_level_badge,
    llm_task_status_badge,
    download_status_badge,
    status_dot,
)
from ui.styles import COLORS, SPACING, TYPOGRAPHY, RADIUS


# ============================================================
# task_status_badge
# ============================================================


class TestTaskStatusBadge:
    def test_completed_contains_ok_style(self):
        html = task_status_badge("completed")
        assert "ds-badge-ok" in html
        assert "已完成" in html

    def test_running_contains_running_style(self):
        html = task_status_badge("running")
        assert "ds-badge-running" in html
        assert "运行中" in html

    def test_pending_contains_info_style(self):
        html = task_status_badge("pending")
        assert "ds-badge-info" in html
        assert "等待中" in html

    def test_failed_contains_error_style(self):
        html = task_status_badge("failed")
        assert "ds-badge-error" in html
        assert "失败" in html

    def test_unknown_status_does_not_crash(self):
        html = task_status_badge("some_unknown_status")
        assert "ds-badge" in html
        assert "some_unknown_status" in html


# ============================================================
# service_status_badge
# ============================================================


class TestServiceStatusBadge:
    def test_disabled_shows_inactive(self):
        html = service_status_badge(enabled=False)
        assert "ds-badge-inactive" in html
        assert "未启用" in html

    def test_enabled_not_configured_shows_warning(self):
        html = service_status_badge(enabled=True, configured=False)
        assert "ds-badge-warning" in html
        assert "未配置" in html

    def test_enabled_configured_shows_ok(self):
        html = service_status_badge(enabled=True, configured=True)
        assert "ds-badge-ok" in html
        assert "已配置" in html

    def test_active_shows_running(self):
        html = service_status_badge(enabled=True, configured=True, active=True)
        assert "ds-badge-running" in html
        assert "运行中" in html


# ============================================================
# source_level_badge
# ============================================================


class TestSourceLevelBadge:
    def test_level_S(self):
        html = source_level_badge("S")
        assert "ds-level-S" in html
        assert ">S<" in html

    def test_level_A(self):
        html = source_level_badge("A")
        assert "ds-level-A" in html
        assert ">A<" in html

    def test_level_B(self):
        html = source_level_badge("B")
        assert "ds-level-B" in html

    def test_level_C(self):
        html = source_level_badge("C")
        assert "ds-level-C" in html

    def test_level_D(self):
        html = source_level_badge("D")
        assert "ds-level-D" in html

    def test_empty_level_does_not_crash(self):
        html = source_level_badge("")
        assert "ds-level" in html

    def test_none_level_does_not_crash(self):
        html = source_level_badge(None)
        assert "ds-level" in html


# ============================================================
# status_badge (generic)
# ============================================================


class TestStatusBadge:
    def test_empty_status_does_not_crash(self):
        html = status_badge("测试", "")
        assert "ds-badge" in html
        assert "测试" in html

    def test_none_status_does_not_crash(self):
        html = status_badge("测试", None)
        assert "ds-badge" in html

    def test_custom_label(self):
        html = status_badge("自定义标签", "ok")
        assert "自定义标签" in html
        assert "ds-badge-ok" in html

    def test_default_label_from_status(self):
        html = status_badge(None, "completed")
        assert "已完成" in html

    def test_all_known_statuses_produce_valid_html(self):
        statuses = [
            "ok", "completed", "configured", "running", "pending",
            "warning", "error", "failed", "inactive", "disabled",
            "planned", "skipped", "info", "llm", "search", "export",
        ]
        for s in statuses:
            html = status_badge(None, s)
            assert "ds-badge" in html, f"Failed for status: {s}"
            assert "<span" in html, f"Failed for status: {s}"


# ============================================================
# llm_task_status_badge
# ============================================================


class TestLLMTaskStatusBadge:
    def test_used_llm(self):
        html = llm_task_status_badge("used_llm")
        assert "ds-badge-ok" in html
        assert "已执行" in html

    def test_fallback(self):
        html = llm_task_status_badge("fallback")
        assert "ds-badge-warning" in html

    def test_skipped_disabled(self):
        html = llm_task_status_badge("skipped_disabled")
        assert "ds-badge-inactive" in html

    def test_unknown_does_not_crash(self):
        html = llm_task_status_badge("unknown_status")
        assert "ds-badge" in html


# ============================================================
# download_status_badge
# ============================================================


class TestDownloadStatusBadge:
    def test_pending(self):
        html = download_status_badge("pending")
        assert "待提取" in html

    def test_extracted(self):
        html = download_status_badge("extracted")
        assert "ds-badge-ok" in html
        assert "已提取" in html

    def test_failed(self):
        html = download_status_badge("failed")
        assert "ds-badge-error" in html


# ============================================================
# status_dot
# ============================================================


class TestStatusDot:
    def test_active_green(self):
        html = status_dot(True, "在线")
        assert "#16A34A" in html
        assert "在线" in html

    def test_inactive_gray(self):
        html = status_dot(False, "离线")
        assert "#D1D5DB" in html
        assert "离线" in html


# ============================================================
# Design Tokens
# ============================================================


class TestDesignTokens:
    def test_colors_defined(self):
        assert "primary" in COLORS
        assert "ok" in COLORS
        assert "error" in COLORS
        assert "warning" in COLORS
        assert "running" in COLORS
        assert "inactive" in COLORS
        assert "planned" in COLORS
        assert COLORS["primary"].startswith("#")

    def test_spacing_defined(self):
        assert "page_top" in SPACING
        assert "section" in SPACING
        assert "card_padding" in SPACING
        assert "card_gap" in SPACING

    def test_typography_defined(self):
        assert "page_title" in TYPOGRAPHY
        assert "section_title" in TYPOGRAPHY
        assert "body" in TYPOGRAPHY
        assert "caption" in TYPOGRAPHY
        assert TYPOGRAPHY["page_title"]["size"] == "28px"
        assert TYPOGRAPHY["page_title"]["weight"] == "700"

    def test_radius_defined(self):
        assert "sm" in RADIUS
        assert "md" in RADIUS
        assert "lg" in RADIUS
        assert RADIUS["lg"] == "12px"


# ============================================================
# Run all tests
# ============================================================


def _run_all():
    """Run all test classes manually (for quick validation without pytest)."""
    test_classes = [
        TestTaskStatusBadge,
        TestServiceStatusBadge,
        TestSourceLevelBadge,
        TestStatusBadge,
        TestLLMTaskStatusBadge,
        TestDownloadStatusBadge,
        TestStatusDot,
        TestDesignTokens,
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
