"""UI 组件逻辑测试 - 验证纯函数输出正确性。"""

import sys
sys.path.insert(0, ".")


def test_badge_html():
    from ui.components.status import status_badge
    html = status_badge("已完成", "ok")
    assert "ds-badge-ok" in html
    assert "已完成" in html


def test_task_status_badge():
    from ui.components.status import task_status_badge
    html = task_status_badge("completed")
    assert "ds-badge-ok" in html
    assert "已完成" in html

    html = task_status_badge("failed")
    assert "ds-badge-error" in html
    assert "失败" in html


def test_level_badge():
    from ui.components.status import source_level_badge
    html = source_level_badge("S")
    assert "ds-level-S" in html
    assert ">S<" in html

    html = source_level_badge("A")
    assert "ds-level-A" in html


def test_download_status_badge():
    from ui.components.status import download_status_badge
    html = download_status_badge("extracted")
    assert "ds-badge-ok" in html
    assert "已提取" in html

    html = download_status_badge("pending")
    assert "ds-badge" in html


def test_status_dot():
    from ui.components.status import status_dot
    html = status_dot(True, "运行中")
    assert "#16A34A" in html
    assert "运行中" in html

    html = status_dot(False, "离线")
    assert "#D1D5DB" in html


def test_stat_card_html():
    from ui.components.cards import stat_card
    html = stat_card(120, "总来源")
    assert "120" in html
    assert "总来源" in html
    assert "metric-card" in html


def test_source_item_html():
    from ui.components.source_cards import render_source_item_html
    item = {
        "source_level": "A",
        "title": "Test Article",
        "url": "https://example.com",
        "domain": "example.com",
        "source_type": "article",
        "snippet": "A test snippet",
        "reason_to_read": "Important source",
        "relevance_score": 0.9,
        "authority_score": 0.8,
        "originality_score": 0.7,
    }
    html = render_source_item_html(item)
    assert "source-card" in html
    assert "Test Article" in html
    assert "ds-level-A" in html
    assert "example.com" in html


def test_timeline_step_map():
    from ui.components.trace_panel import STEP_ZH_MAP
    assert "task_created" in STEP_ZH_MAP
    assert "task_completed" in STEP_ZH_MAP
    assert STEP_ZH_MAP["task_created"] == "任务已创建"


def test_colors_defined():
    from ui.styles import COLORS
    assert "primary" in COLORS
    assert "ok" in COLORS
    assert "error" in COLORS
    assert COLORS["primary"].startswith("#")


if __name__ == "__main__":
    test_badge_html()
    test_task_status_badge()
    test_level_badge()
    test_download_status_badge()
    test_status_dot()
    test_stat_card_html()
    test_source_item_html()
    test_timeline_step_map()
    test_colors_defined()
    print("✅ All UI component tests passed")
