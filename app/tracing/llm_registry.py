"""LLM Task Registry - 所有可能使用 LLM 的任务登记。

每个任务都有明确的 implementation_status，即使当前未实现也要登记。
Trace 页面通过此 registry 展示完整 LLM 使用情况。
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LLM_TASKS_PATH = _PROJECT_ROOT / "config" / "llm_tasks.yaml"
_PROMPT_TEMPLATES_DIR = _PROJECT_ROOT / "config" / "prompt_templates"


class LLMTaskInfo(BaseModel):
    """LLM 任务注册信息。"""

    task_name: str
    stage: str = "unknown"
    prompt_template: str = ""
    prompt_template_exists: bool = False
    expected_trigger: str = ""
    enabled: bool = True
    implemented: bool = True
    fallback: str = ""
    implementation_status: str = "implemented"  # implemented / planned / disabled / not_applicable
    covered_by: str = ""  # 如果此任务由另一个任务覆盖
    wait_for: str = ""  # 等待条件（如 extraction）
    group: str = ""  # UI 分组：executed / waiting / export / planned


class LLMTaskStatus(BaseModel):
    """单个 LLM 任务在某次研究中的执行状态。"""

    task_name: str
    stage: str = ""
    status: str = "unknown"  # used_llm / fallback / skipped_disabled / skipped_not_reached / skipped_not_implemented / skipped_missing_prompt / rule_only
    provider: str | None = None
    model: str | None = None
    prompt_template: str = ""
    prompt_template_exists: bool = False
    input_chars: int | None = None
    output_chars: int | None = None
    duration_ms: int | None = None
    fallback_used: bool = False
    fallback_name: str = ""
    skipped_reason: str = ""
    error_message: str = ""


# === Task metadata (stage, trigger, prompt mapping) ===

_TASK_METADATA: dict[str, dict[str, str]] = {
    "topic_understanding": {
        "stage": "planning",
        "prompt_template": "topic_understanding.zh.md",
        "expected_trigger": "task_start",
    },
    "language_planning": {
        "stage": "planning",
        "prompt_template": "topic_understanding.zh.md",
        "expected_trigger": "task_start",
    },
    "query_expansion": {
        "stage": "planning",
        "prompt_template": "query_expansion.zh.md",
        "expected_trigger": "before_search",
    },
    "query_translation": {
        "stage": "planning",
        "prompt_template": "query_expansion.zh.md",
        "expected_trigger": "before_search",
    },
    "source_review": {
        "stage": "scoring",
        "prompt_template": "source_review.zh.md",
        "expected_trigger": "after_search",
    },
    "source_reason_generation": {
        "stage": "scoring",
        "prompt_template": "source_reason_generation.zh.md",
        "expected_trigger": "after_scoring",
    },
    "entity_extraction": {
        "stage": "analysis",
        "prompt_template": "entity_extraction.zh.md",
        "expected_trigger": "after_extraction",
    },
    "document_summary": {
        "stage": "analysis",
        "prompt_template": "document_summary.zh.md",
        "expected_trigger": "after_extraction",
    },
    "story_point_extraction": {
        "stage": "analysis",
        "prompt_template": "document_summary.zh.md",
        "expected_trigger": "after_extraction",
    },
    "gossip_classification": {
        "stage": "analysis",
        "prompt_template": "source_review.zh.md",
        "expected_trigger": "after_source_review",
    },
    "contradiction_detection": {
        "stage": "synthesis",
        "prompt_template": "contradiction_detection.zh.md",
        "expected_trigger": "after_multiple_documents_extracted",
    },
    "timeline_extraction": {
        "stage": "analysis",
        "prompt_template": "document_summary.zh.md",
        "expected_trigger": "after_extraction",
    },
    "research_card_generation": {
        "stage": "synthesis",
        "prompt_template": "research_card.zh.md",
        "expected_trigger": "after_document_analysis",
    },
    "markdown_summary_generation": {
        "stage": "export",
        "prompt_template": "markdown_summary_generation.zh.md",
        "expected_trigger": "before_export_source_note",
    },
    "final_index_synthesis": {
        "stage": "export",
        "prompt_template": "final_index_synthesis.zh.md",
        "expected_trigger": "export_index",
    },
    "reranking": {
        "stage": "processing",
        "prompt_template": "source_review.zh.md",
        "expected_trigger": "after_dedupe",
    },
}

# Rule-only steps that never use LLM
RULE_ONLY_STEPS = [
    "url_normalize",
    "url_dedupe",
    "db_save",
    "file_path_validation",
    "markdown_template_render",
    "provider_http_request",
    "vault_write",
]


def get_all_task_info() -> list[LLMTaskInfo]:
    """获取所有已注册 LLM 任务的信息。"""
    try:
        config = _load_config()
    except Exception:
        config = {}

    tasks_config = config.get("tasks", {})
    results = []

    for task_name, meta in _TASK_METADATA.items():
        prompt_template = meta.get("prompt_template", "")
        prompt_exists = _check_prompt_exists(prompt_template)

        # 从 yaml 获取 enabled/implemented 状态
        task_yaml = tasks_config.get(task_name, {}) or {}
        enabled = task_yaml.get("enabled", True)
        implemented = task_yaml.get("implemented", task_name in tasks_config)
        fallback = task_yaml.get("fallback", "")
        covered_by = task_yaml.get("covered_by", "")
        wait_for = task_yaml.get("wait_for", "")
        stage = task_yaml.get("stage", meta.get("stage", "unknown"))

        # 确定 implementation_status
        if covered_by:
            impl_status = "covered"
        elif not implemented:
            impl_status = "planned"
        elif not enabled:
            impl_status = "disabled"
        else:
            impl_status = "implemented"

        # 确定 UI 分组
        if covered_by:
            group = "covered"
        elif not implemented:
            group = "planned"
        elif stage == "export":
            group = "export"
        elif wait_for:
            group = "waiting"
        elif not enabled:
            group = "disabled"
        else:
            group = "executed"

        results.append(LLMTaskInfo(
            task_name=task_name,
            stage=stage,
            prompt_template=prompt_template,
            prompt_template_exists=prompt_exists,
            expected_trigger=meta.get("expected_trigger", ""),
            enabled=enabled,
            implemented=implemented,
            fallback=fallback,
            implementation_status=impl_status,
            covered_by=covered_by,
            wait_for=wait_for,
            group=group,
        ))

    return results


def get_task_info(task_name: str) -> LLMTaskInfo | None:
    """获取单个任务信息。"""
    all_tasks = get_all_task_info()
    return next((t for t in all_tasks if t.task_name == task_name), None)


def _check_prompt_exists(template_name: str) -> bool:
    """检查 prompt 模板文件是否存在。"""
    if not template_name:
        return False
    return (_PROMPT_TEMPLATES_DIR / template_name).exists()


def _load_config() -> dict:
    """加载 llm_tasks.yaml。"""
    if not _LLM_TASKS_PATH.exists():
        return {}
    with open(_LLM_TASKS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
