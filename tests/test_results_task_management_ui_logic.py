"""Results 页面任务管理 UI 逻辑测试。

抽取纯函数进行测试，不依赖 Streamlit 运行时。
"""

import pytest


# === 纯函数（从 UI 逻辑中抽取） ===


def build_task_action_state(task: dict) -> dict:
    """根据任务状态构建可用操作。"""
    status = task.get("status", "pending")
    is_deleted = task.get("deleted_at") is not None

    return {
        "can_rename": not is_deleted,
        "can_clone": True,  # 任何状态都可以复制
        "can_delete": not is_deleted,
        "can_rerun": status in ("completed", "failed"),
        "is_deleted": is_deleted,
        "show_warning_before_delete": status == "running",
    }


def validate_rename_topic(topic: str) -> dict:
    """验证重命名主题。"""
    if not topic:
        return {"valid": False, "error": "主题名称不能为空"}
    topic = topic.strip()
    if not topic:
        return {"valid": False, "error": "主题名称不能为空"}
    if len(topic) > 500:
        return {"valid": False, "error": "主题名称不能超过 500 字符"}
    return {"valid": True, "topic": topic}


def confirm_delete_state(checkbox_checked: bool) -> dict:
    """确认删除状态。"""
    return {
        "can_proceed": checkbox_checked,
        "button_disabled": not checkbox_checked,
    }


def build_clone_payload(
    task: dict,
    topic_override: str | None = None,
    rerun_immediately: bool = False,
) -> dict:
    """构建复制任务请求 payload。"""
    payload = {
        "rerun_immediately": rerun_immediately,
    }
    if topic_override and topic_override.strip():
        payload["topic_override"] = topic_override.strip()
    return payload


# === 测试 ===


class TestBuildTaskActionState:
    """测试任务操作状态构建。"""

    def test_completed_task_can_clone(self):
        task = {"status": "completed", "deleted_at": None}
        state = build_task_action_state(task)
        assert state["can_clone"] is True
        assert state["can_rerun"] is True

    def test_running_task_needs_warning_before_delete(self):
        task = {"status": "running", "deleted_at": None}
        state = build_task_action_state(task)
        assert state["show_warning_before_delete"] is True
        assert state["can_delete"] is True

    def test_deleted_task_cannot_rename(self):
        task = {"status": "completed", "deleted_at": "2025-01-01T00:00:00"}
        state = build_task_action_state(task)
        assert state["can_rename"] is False
        assert state["can_delete"] is False
        assert state["is_deleted"] is True

    def test_pending_task_cannot_rerun(self):
        task = {"status": "pending", "deleted_at": None}
        state = build_task_action_state(task)
        assert state["can_rerun"] is False

    def test_failed_task_can_rerun(self):
        task = {"status": "failed", "deleted_at": None}
        state = build_task_action_state(task)
        assert state["can_rerun"] is True


class TestValidateRenameTopic:
    """测试重命名主题验证。"""

    def test_empty_topic_invalid(self):
        result = validate_rename_topic("")
        assert result["valid"] is False

    def test_whitespace_only_invalid(self):
        result = validate_rename_topic("   ")
        assert result["valid"] is False

    def test_valid_topic(self):
        result = validate_rename_topic("新的研究主题")
        assert result["valid"] is True
        assert result["topic"] == "新的研究主题"

    def test_topic_trimmed(self):
        result = validate_rename_topic("  带空格的主题  ")
        assert result["valid"] is True
        assert result["topic"] == "带空格的主题"

    def test_too_long_topic(self):
        result = validate_rename_topic("x" * 501)
        assert result["valid"] is False
        assert "500" in result["error"]


class TestConfirmDeleteState:
    """测试删除确认状态。"""

    def test_unchecked_cannot_proceed(self):
        state = confirm_delete_state(False)
        assert state["can_proceed"] is False
        assert state["button_disabled"] is True

    def test_checked_can_proceed(self):
        state = confirm_delete_state(True)
        assert state["can_proceed"] is True
        assert state["button_disabled"] is False


class TestBuildClonePayload:
    """测试复制任务 payload 构建。"""

    def test_basic_clone(self):
        task = {"task_id": "task-001", "topic": "原始主题", "mode": "auto"}
        payload = build_clone_payload(task)
        assert payload == {"rerun_immediately": False}

    def test_clone_with_topic_override(self):
        task = {"task_id": "task-001", "topic": "原始主题"}
        payload = build_clone_payload(task, topic_override="新主题")
        assert payload["topic_override"] == "新主题"

    def test_clone_with_rerun(self):
        task = {"task_id": "task-001", "topic": "原始主题"}
        payload = build_clone_payload(task, rerun_immediately=True)
        assert payload["rerun_immediately"] is True

    def test_clone_empty_topic_override_ignored(self):
        task = {"task_id": "task-001", "topic": "原始主题"}
        payload = build_clone_payload(task, topic_override="  ")
        assert "topic_override" not in payload

    def test_clone_with_all_options(self):
        task = {"task_id": "task-001", "topic": "原始主题"}
        payload = build_clone_payload(task, topic_override="覆盖主题", rerun_immediately=True)
        assert payload["topic_override"] == "覆盖主题"
        assert payload["rerun_immediately"] is True
