"""Research 页面逻辑测试 - 确认不包含导出功能。"""

import pytest


def test_research_page_has_no_export_call():
    """Research 页面不调用 export-index API。"""
    from pathlib import Path
    page_path = Path("ui/pages/1_Research.py")
    content = page_path.read_text(encoding="utf-8")

    # 不应包含 export_index 调用
    assert "export_index" not in content
    assert "export-index" not in content
    assert "export_research_index" not in content


def test_research_page_has_no_export_button():
    """Research 页面没有导出按钮（st.button 调用导出）。"""
    from pathlib import Path
    page_path = Path("ui/pages/1_Research.py")
    content = page_path.read_text(encoding="utf-8")

    # 不应包含 export API 调用
    assert "export_index(" not in content
    assert "export_research_index(" not in content
    # 不应有导出按钮的 st.button
    assert 'key="export_' not in content


def test_research_page_has_view_results_link():
    """Research 页面有查看研究结果的链接。"""
    from pathlib import Path
    page_path = Path("ui/pages/1_Research.py")
    content = page_path.read_text(encoding="utf-8")

    # 应包含跳转到 Results 页面的逻辑
    assert "Results" in content or "2_Results" in content
    assert "selected_task_id" in content


def test_research_page_saves_task_id():
    """Research 页面完成后保存 task_id 到 session_state。"""
    from pathlib import Path
    page_path = Path("ui/pages/1_Research.py")
    content = page_path.read_text(encoding="utf-8")

    assert "last_task_id" in content
    assert "selected_task_id" in content
