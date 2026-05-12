"""测试 Results 页面合成按钮状态逻辑（纯函数）。"""

import pytest


# === 纯函数（从 UI 中抽出） ===


def get_synthesis_button_state(
    task_status: str,
    extracted_count: int,
    vault_configured: bool,
) -> dict:
    """计算合成按钮状态。

    Returns:
        {"enabled": bool, "reason": str}
    """
    if task_status != "completed":
        return {"enabled": False, "reason": "任务尚未完成，请等待研究完成后再合成。"}

    if extracted_count <= 0:
        return {"enabled": False, "reason": "请先抓取 A/S 级来源正文，再进行内容合成。"}

    if not vault_configured:
        return {"enabled": False, "reason": "请先到 Settings 配置 Obsidian Vault 路径。"}

    return {"enabled": True, "reason": ""}


def format_synthesis_result(result: dict) -> dict:
    """格式化合成结果用于 UI 展示。

    Returns:
        {"success": bool, "message": str, "details": dict}
    """
    if result.get("error"):
        return {
            "success": False,
            "message": result.get("error", "合成失败"),
            "details": {},
        }

    return {
        "success": True,
        "message": "研究文档合成完成",
        "details": {
            "normalized_document_count": result.get("normalized_document_count", 0),
            "deduplicated_claim_count": result.get("deduplicated_claim_count", 0),
            "confirmed_fact_count": result.get("confirmed_fact_count", 0),
            "verification_needed_count": result.get("verification_needed_count", 0),
            "index_path": result.get("index_path", ""),
        },
    }


# === Tests ===


class TestGetSynthesisButtonState:
    """按钮状态逻辑测试。"""

    def test_completed_with_extracted_and_vault_enabled(self):
        """completed + extracted_count>0 + vault ok → enabled。"""
        state = get_synthesis_button_state(
            task_status="completed",
            extracted_count=5,
            vault_configured=True,
        )
        assert state["enabled"] is True
        assert state["reason"] == ""

    def test_no_extracted_docs_disabled(self):
        """no extracted docs → disabled。"""
        state = get_synthesis_button_state(
            task_status="completed",
            extracted_count=0,
            vault_configured=True,
        )
        assert state["enabled"] is False
        assert "抓取" in state["reason"]

    def test_running_task_disabled(self):
        """running task → disabled。"""
        state = get_synthesis_button_state(
            task_status="running",
            extracted_count=5,
            vault_configured=True,
        )
        assert state["enabled"] is False
        assert "完成" in state["reason"]

    def test_pending_task_disabled(self):
        """pending task → disabled。"""
        state = get_synthesis_button_state(
            task_status="pending",
            extracted_count=0,
            vault_configured=True,
        )
        assert state["enabled"] is False

    def test_no_vault_disabled(self):
        """no vault → disabled 或提示需配置 Vault。"""
        state = get_synthesis_button_state(
            task_status="completed",
            extracted_count=5,
            vault_configured=False,
        )
        assert state["enabled"] is False
        assert "Vault" in state["reason"] or "配置" in state["reason"]

    def test_failed_task_disabled(self):
        """failed task → disabled。"""
        state = get_synthesis_button_state(
            task_status="failed",
            extracted_count=3,
            vault_configured=True,
        )
        assert state["enabled"] is False


class TestFormatSynthesisResult:
    """格式化合成结果测试。"""

    def test_success_result(self):
        """成功结果格式化。"""
        result = {
            "task_id": "task-001",
            "synthesized": True,
            "normalized_document_count": 12,
            "deduplicated_claim_count": 45,
            "confirmed_fact_count": 20,
            "verification_needed_count": 7,
            "index_path": "/vault/Research/topic/index.md",
        }
        formatted = format_synthesis_result(result)
        assert formatted["success"] is True
        assert formatted["details"]["normalized_document_count"] == 12
        assert formatted["details"]["index_path"] == "/vault/Research/topic/index.md"

    def test_error_result(self):
        """错误结果格式化。"""
        result = {"error": "请先抓取 A/S 级来源正文，再进行内容合成。"}
        formatted = format_synthesis_result(result)
        assert formatted["success"] is False
        assert "抓取" in formatted["message"]
