"""测试自动合成流程 - run_auto_synthesis。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.research_service import load_synthesis_policy, run_auto_synthesis


# === Fixtures ===


def _mock_policy(enabled=True, min_docs=1, run_after=True):
    return {
        "enabled": enabled,
        "require_extracted_documents": True,
        "min_extracted_documents": min_docs,
        "run_after_auto_fetch": run_after,
        "write_index": True,
    }


def _mock_synthesis_result(synthesized=True, **kwargs):
    result = {
        "task_id": "task-001",
        "synthesized": synthesized,
        "normalized_document_count": 5,
        "deduplicated_claim_count": 20,
        "confirmed_fact_count": 10,
        "verification_needed_count": 3,
        "index_path": "/vault/Research/topic/index.md",
    }
    result.update(kwargs)
    return result


# === Tests ===


class TestAutoFetchWithDocuments:
    """auto_fetch 后有文档 → 自动调用 synthesis。"""

    @pytest.mark.asyncio
    async def test_calls_synthesis_when_docs_available(self):
        """有足够文档时调用 synthesize_research_task。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy()
            mock_synth.return_value = _mock_synthesis_result()

            result = await run_auto_synthesis(task_id="task-001", extracted_count=3)

        assert result["status"] == "completed"
        assert result["synthesized"] is True
        mock_synth.assert_called_once_with("task-001")

    @pytest.mark.asyncio
    async def test_min_docs_threshold(self):
        """extracted_count >= min_extracted_documents 时执行。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy(min_docs=3)
            mock_synth.return_value = _mock_synthesis_result()

            result = await run_auto_synthesis(task_id="task-001", extracted_count=3)

        assert result["status"] == "completed"
        mock_synth.assert_called_once()


class TestNoDocumentsSkipped:
    """没文档 → 跳过并记录原因。"""

    @pytest.mark.asyncio
    async def test_skipped_when_no_docs(self):
        """extracted_count=0 时跳过。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy(min_docs=1)

            result = await run_auto_synthesis(task_id="task-001", extracted_count=0)

        assert result["status"] == "skipped"
        assert "extracted_count" in result["reason"]
        mock_synth.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_below_min(self):
        """extracted_count < min 时跳过。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy(min_docs=5)

            result = await run_auto_synthesis(task_id="task-001", extracted_count=3)

        assert result["status"] == "skipped"
        mock_synth.assert_not_called()


class TestSynthesisFailureFallback:
    """synthesis 失败 → fallback 到旧 index。"""

    @pytest.mark.asyncio
    async def test_failure_returns_failed_status(self):
        """合成抛异常时返回 failed 状态，不抛出。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy()
            mock_synth.side_effect = RuntimeError("LLM 全部超时")

            result = await run_auto_synthesis(task_id="task-001", extracted_count=5)

        # 不抛异常
        assert result["status"] == "failed"
        assert "超时" in result["reason"]

    @pytest.mark.asyncio
    async def test_synthesis_error_result_returns_failed(self):
        """合成返回 error 时返回 failed 状态。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy()
            mock_synth.return_value = {"error": "内部错误", "synthesized": False}

            result = await run_auto_synthesis(task_id="task-001", extracted_count=5)

        assert result["status"] == "failed"
        assert "内部错误" in result["reason"]


class TestAutoGeneratesIndex:
    """自动生成 index.md。"""

    @pytest.mark.asyncio
    async def test_index_path_in_result(self):
        """成功时结果包含 index_path。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy()
            mock_synth.return_value = _mock_synthesis_result(
                index_path="/vault/Research/topic/index.md"
            )

            result = await run_auto_synthesis(task_id="task-001", extracted_count=3)

        assert result["index_path"] == "/vault/Research/topic/index.md"


class TestDisabledPolicy:
    """不影响未开启 auto_synthesis 的任务。"""

    @pytest.mark.asyncio
    async def test_disabled_policy_skips(self):
        """enabled=false 时跳过。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy(enabled=False)

            result = await run_auto_synthesis(task_id="task-001", extracted_count=10)

        assert result["status"] == "skipped"
        assert "disabled" in result["reason"]
        mock_synth.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_after_false_skips(self):
        """run_after_auto_fetch=false 时跳过。"""
        with patch("app.services.research_service.load_synthesis_policy") as mock_policy, \
             patch("app.services.research_service.synthesize_research_task") as mock_synth:

            mock_policy.return_value = _mock_policy(run_after=False)

            result = await run_auto_synthesis(task_id="task-001", extracted_count=10)

        assert result["status"] == "skipped"
        assert "run_after_auto_fetch" in result["reason"]
        mock_synth.assert_not_called()


class TestPolicyLoading:
    """策略加载测试。"""

    def test_load_default_policy(self):
        """加载默认策略。"""
        policy = load_synthesis_policy()
        assert policy["enabled"] is True
        assert policy["min_extracted_documents"] >= 1
        assert policy["run_after_auto_fetch"] is True
