"""Results 页面历史任务 UI 逻辑测试（纯函数）。"""

import pytest


# === 纯函数（从 Results 页面逻辑提取） ===


def choose_initial_task_id(
    history: list[dict],
    selected_task_id: str = "",
    last_task_id: str = "",
) -> str | None:
    """选择初始 task_id。

    优先级：
    1. selected_task_id（用户从历史列表点击）
    2. last_task_id（session_state 中的最近任务）
    3. 历史中第一个 completed 任务
    4. 历史中第一个任务
    5. None
    """
    if selected_task_id:
        return selected_task_id
    if last_task_id:
        return last_task_id
    if history:
        completed = [t for t in history if t.get("status") == "completed"]
        if completed:
            return completed[0]["task_id"]
        return history[0]["task_id"]
    return None


def filter_task_history(
    tasks: list[dict],
    status: str | None = None,
    q: str | None = None,
) -> list[dict]:
    """筛选历史任务列表。"""
    result = tasks
    if status and status != "全部":
        result = [t for t in result if t.get("status") == status]
    if q:
        q_lower = q.lower()
        result = [t for t in result if q_lower in t.get("topic", "").lower()]
    return result


def format_task_card(task: dict) -> dict:
    """格式化任务卡片显示信息。"""
    status_icons = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}
    return {
        "icon": status_icons.get(task.get("status", ""), "❓"),
        "topic_short": task["topic"][:25] + ("..." if len(task["topic"]) > 25 else ""),
        "source_info": f"{task.get('source_count', 0)} sources",
        "high_quality": task.get("high_quality_count", 0),
        "exported": task.get("exported", False),
        "time_str": (task.get("created_at") or "")[:10],
    }


def get_status_badge(status: str) -> str:
    """获取状态 badge。"""
    badges = {
        "completed": "✅",
        "running": "⏳",
        "pending": "🕐",
        "failed": "❌",
    }
    return badges.get(status, "❓")


# === Tests ===


class TestChooseInitialTaskId:
    def test_selected_task_id_highest_priority(self):
        history = [{"task_id": "t1", "status": "completed"}]
        result = choose_initial_task_id(history, selected_task_id="t-selected", last_task_id="t-last")
        assert result == "t-selected"

    def test_last_task_id_second_priority(self):
        history = [{"task_id": "t1", "status": "completed"}]
        result = choose_initial_task_id(history, selected_task_id="", last_task_id="t-last")
        assert result == "t-last"

    def test_first_completed_from_history(self):
        history = [
            {"task_id": "t1", "status": "running"},
            {"task_id": "t2", "status": "completed"},
            {"task_id": "t3", "status": "completed"},
        ]
        result = choose_initial_task_id(history)
        assert result == "t2"

    def test_first_task_if_no_completed(self):
        history = [
            {"task_id": "t1", "status": "running"},
            {"task_id": "t2", "status": "pending"},
        ]
        result = choose_initial_task_id(history)
        assert result == "t1"

    def test_none_if_empty_history(self):
        result = choose_initial_task_id([])
        assert result is None


class TestFilterTaskHistory:
    def _tasks(self):
        return [
            {"task_id": "t1", "topic": "Tim Cook 童年", "status": "completed"},
            {"task_id": "t2", "topic": "OpenAI 宫斗", "status": "completed"},
            {"task_id": "t3", "topic": "黄仁勋创业", "status": "running"},
        ]

    def test_no_filter_returns_all(self):
        result = filter_task_history(self._tasks())
        assert len(result) == 3

    def test_status_filter(self):
        result = filter_task_history(self._tasks(), status="completed")
        assert len(result) == 2

    def test_q_filter(self):
        result = filter_task_history(self._tasks(), q="Cook")
        assert len(result) == 1
        assert result[0]["task_id"] == "t1"

    def test_combined_filter(self):
        result = filter_task_history(self._tasks(), status="completed", q="OpenAI")
        assert len(result) == 1
        assert result[0]["task_id"] == "t2"

    def test_q_case_insensitive(self):
        result = filter_task_history(self._tasks(), q="cook")
        assert len(result) == 1


class TestFormatTaskCard:
    def test_completed_task(self):
        task = {
            "task_id": "t1",
            "topic": "Tim Cook 的童年故事研究",
            "status": "completed",
            "source_count": 91,
            "high_quality_count": 12,
            "exported": True,
            "created_at": "2026-05-12T14:22:00",
        }
        card = format_task_card(task)
        assert card["icon"] == "✅"
        assert len(card["topic_short"]) <= 28  # 25 + "..."
        assert card["source_info"] == "91 sources"
        assert card["high_quality"] == 12
        assert card["exported"] is True
        assert card["time_str"] == "2026-05-12"

    def test_running_task(self):
        task = {"task_id": "t2", "topic": "Short", "status": "running", "source_count": 0, "created_at": ""}
        card = format_task_card(task)
        assert card["icon"] == "⏳"
        assert card["topic_short"] == "Short"


class TestStatusBadge:
    def test_all_statuses(self):
        assert get_status_badge("completed") == "✅"
        assert get_status_badge("running") == "⏳"
        assert get_status_badge("pending") == "🕐"
        assert get_status_badge("failed") == "❌"
        assert get_status_badge("unknown") == "❓"
