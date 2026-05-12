"""LLM 任务状态 UI 分组测试。"""

import pytest
from app.tracing.llm_registry import get_all_task_info


class TestTaskGrouping:
    """测试任务分组逻辑。"""

    def test_language_planning_covered_by_topic_understanding(self):
        """language_planning 应标记为 covered_by topic_understanding。"""
        tasks = get_all_task_info()
        lp = next(t for t in tasks if t.task_name == "language_planning")
        assert lp.covered_by == "topic_understanding"
        assert lp.group == "covered"
        assert lp.implementation_status == "covered"

    def test_planned_tasks_grouped_correctly(self):
        """未实现的任务应分到 planned 组。"""
        tasks = get_all_task_info()
        planned = [t for t in tasks if t.group == "planned"]
        planned_names = [t.task_name for t in planned]

        # 这些任务应该在 planned 组
        assert "story_point_extraction" in planned_names
        assert "gossip_classification" in planned_names
        assert "timeline_extraction" in planned_names
        assert "research_card_generation" in planned_names

        # 这些不应该在 planned 组
        assert "query_expansion" not in planned_names
        assert "source_reason_generation" not in planned_names

    def test_waiting_tasks_have_wait_for(self):
        """等待正文提取的任务应有 wait_for 字段。"""
        tasks = get_all_task_info()
        entity = next(t for t in tasks if t.task_name == "entity_extraction")
        assert entity.wait_for == "extraction"
        assert entity.group == "waiting"

        doc_sum = next(t for t in tasks if t.task_name == "document_summary")
        assert doc_sum.wait_for == "extraction"
        assert doc_sum.group == "waiting"

    def test_export_tasks_grouped(self):
        """导出阶段任务应分到 export 组。"""
        tasks = get_all_task_info()
        export_tasks = [t for t in tasks if t.group == "export"]
        export_names = [t.task_name for t in export_tasks]

        assert "markdown_summary_generation" in export_names
        assert "final_index_synthesis" in export_names

    def test_source_reason_generation_is_implemented(self):
        """source_reason_generation 应标记为已实现。"""
        tasks = get_all_task_info()
        srg = next(t for t in tasks if t.task_name == "source_reason_generation")
        assert srg.implemented is True
        assert srg.enabled is True
        assert srg.group == "executed"

    def test_all_tasks_have_stage(self):
        """所有任务都应有 stage。"""
        tasks = get_all_task_info()
        for t in tasks:
            assert t.stage != "unknown", f"{t.task_name} has unknown stage"

    def test_no_task_shows_not_implemented_for_implemented(self):
        """已实现的任务不应显示'当前版本未实现'。"""
        tasks = get_all_task_info()
        for t in tasks:
            if t.implemented:
                assert t.implementation_status != "planned", f"{t.task_name} is implemented but shows planned"
