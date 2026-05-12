"""任务队列 UI 逻辑测试。"""

import pytest

from ui.components.task_queue_panel import build_queue_panel_state


class TestBuildQueuePanelState:
    """build_queue_panel_state 测试。"""

    def test_empty_queue(self):
        """空队列。"""
        data = {
            "running": None,
            "queued": [],
            "completed_recent": [],
            "failed_recent": [],
            "worker_running": False,
        }
        state = build_queue_panel_state(data)
        assert not state["has_activity"]
        assert state["running_task"] is None
        assert state["queued_tasks"] == []

    def test_correct_grouping(self):
        """正确分组。"""
        data = {
            "running": {"task_id": "t1", "started_at": "2024-01-01T00:00:00"},
            "queued": [
                {"task_id": "t2", "priority": 100, "created_at": "2024-01-01"},
                {"task_id": "t3", "priority": 200, "created_at": "2024-01-01"},
            ],
            "completed_recent": [
                {"task_id": "t4", "completed_at": "2024-01-01"},
            ],
            "failed_recent": [
                {"task_id": "t5", "error_message": "timeout", "completed_at": "2024-01-01"},
            ],
            "total_queued": 2,
            "total_completed": 1,
            "total_failed": 1,
            "worker_running": True,
        }
        state = build_queue_panel_state(data)

        assert state["has_activity"]
        assert state["worker_running"]
        assert state["running_task"]["task_id"] == "t1"
        assert len(state["queued_tasks"]) == 2
        assert len(state["completed_tasks"]) == 1
        assert len(state["failed_tasks"]) == 1

    def test_running_task_shows_details_button(self):
        """running task 显示查看详情按钮。"""
        data = {
            "running": {"task_id": "t1", "started_at": "2024-01-01T00:00:00"},
            "queued": [],
            "completed_recent": [],
            "failed_recent": [],
            "worker_running": True,
        }
        state = build_queue_panel_state(data)
        assert state["running_task"]["show_details_button"]

    def test_failed_task_shows_retry_button(self):
        """failed task 显示重试按钮。"""
        data = {
            "running": None,
            "queued": [],
            "completed_recent": [],
            "failed_recent": [
                {"task_id": "t1", "error_message": "error", "completed_at": "2024-01-01"},
            ],
            "worker_running": False,
        }
        state = build_queue_panel_state(data)
        assert state["failed_tasks"][0]["show_retry_button"]

    def test_queued_task_shows_cancel_button(self):
        """queued task 显示取消按钮。"""
        data = {
            "running": None,
            "queued": [
                {"task_id": "t1", "priority": 100, "created_at": "2024-01-01"},
            ],
            "completed_recent": [],
            "failed_recent": [],
            "worker_running": True,
        }
        state = build_queue_panel_state(data)
        assert state["queued_tasks"][0]["show_cancel_button"]

    def test_completed_task_shows_results_button(self):
        """completed task 显示查看结果按钮。"""
        data = {
            "running": None,
            "queued": [],
            "completed_recent": [
                {"task_id": "t1", "completed_at": "2024-01-01"},
            ],
            "failed_recent": [],
            "worker_running": False,
        }
        state = build_queue_panel_state(data)
        assert state["completed_tasks"][0]["show_results_button"]
