"""Results 页面纯函数 - 可独立测试，不依赖 Streamlit。"""

from __future__ import annotations


# ============================================================
# Source Grouping & Filtering
# ============================================================


def group_sources_by_category(sources: list[dict]) -> dict[str, list[dict]]:
    """将来源按 category 分组（来自 API 的 categories 字段）。

    如果没有 category 信息，按 source_level 分组。
    """
    categories: dict[str, list[dict]] = {
        "必读资料": [],
        "一手资料": [],
        "深度报道": [],
        "图书资料": [],
        "采访与演讲": [],
        "八卦与旁证": [],
        "其他": [],
    }

    for item in sources:
        level = item.get("source_level", "C")
        source_type = item.get("source_type", "")
        gossip = item.get("gossip_score", 0)

        if level in ("S", "A"):
            categories["必读资料"].append(item)
        elif source_type == "book":
            categories["图书资料"].append(item)
        elif source_type in ("interview", "speech", "podcast"):
            categories["采访与演讲"].append(item)
        elif gossip >= 0.3:
            categories["八卦与旁证"].append(item)
        elif source_type in ("primary_source", "official"):
            categories["一手资料"].append(item)
        elif level == "B":
            categories["深度报道"].append(item)
        else:
            categories["其他"].append(item)

    return {k: v for k, v in categories.items() if v}


def build_source_filter_state(
    level: str = "全部",
    source_type: str = "全部",
    download_status: str = "全部",
    keyword: str = "",
    hide_low_quality: bool = True,
) -> dict:
    """构建来源筛选状态对象。"""
    return {
        "level": level,
        "source_type": source_type,
        "download_status": download_status,
        "keyword": keyword.strip().lower(),
        "hide_low_quality": hide_low_quality,
    }


def apply_source_filters(sources: list[dict], filters: dict) -> list[dict]:
    """应用筛选条件到来源列表。"""
    result = sources

    level = filters.get("level", "全部")
    if level != "全部":
        result = [s for s in result if s.get("source_level") == level]

    source_type = filters.get("source_type", "全部")
    if source_type != "全部":
        result = [s for s in result if s.get("source_type") == source_type]

    dl_status = filters.get("download_status", "全部")
    if dl_status != "全部":
        result = [s for s in result if s.get("download_status") == dl_status]

    keyword = filters.get("keyword", "")
    if keyword:
        result = [
            s for s in result
            if keyword in s.get("title", "").lower()
            or keyword in s.get("domain", "").lower()
            or keyword in s.get("snippet", "").lower()
        ]

    if filters.get("hide_low_quality", True):
        result = [s for s in result if s.get("source_level") != "D"]

    return result


# ============================================================
# Task Summary Cards
# ============================================================


def format_task_summary_cards(task: dict, sources: list[dict]) -> list[dict]:
    """构建任务摘要卡片数据。

    Returns:
        [{"label": "...", "value": ..., "variant": "..."}, ...]
    """
    total = len(sources)
    extracted = sum(1 for s in sources if s.get("download_status") in ("extracted", "exported"))
    high_quality = sum(1 for s in sources if s.get("source_level") in ("S", "A"))
    failed = sum(1 for s in sources if s.get("download_status") == "failed")

    cards = [
        {"label": "Sources", "value": total},
        {"label": "Extracted", "value": extracted},
        {"label": "High Quality", "value": high_quality},
    ]

    if failed > 0:
        cards.append({"label": "Failed", "value": failed, "variant": "error"})

    return cards


# ============================================================
# Synthesis Button State
# ============================================================


def get_synthesis_button_state(
    task_status: str,
    extracted_count: int,
    vault_usable: bool,
) -> dict:
    """判断合成按钮的状态。

    Returns:
        {
            "enabled": bool,
            "label": str,
            "reason": str | None,  # 不可用时的原因
        }
    """
    if task_status != "completed":
        return {
            "enabled": False,
            "label": "Clean & Synthesize",
            "reason": "任务尚未完成",
        }
    if extracted_count == 0:
        return {
            "enabled": False,
            "label": "Clean & Synthesize",
            "reason": "请先提取来源正文",
        }
    if not vault_usable:
        return {
            "enabled": False,
            "label": "Clean & Synthesize",
            "reason": "请先配置 Obsidian Vault",
        }
    return {
        "enabled": True,
        "label": "Clean & Synthesize Research Document",
        "reason": None,
    }


# ============================================================
# Export Button State
# ============================================================


def get_export_button_state(
    task_status: str,
    vault_usable: bool,
    vault_path: str = "",
) -> dict:
    """判断导出按钮的状态。

    Returns:
        {
            "enabled": bool,
            "label": str,
            "reason": str | None,
            "target_path": str,
        }
    """
    if task_status != "completed":
        return {
            "enabled": False,
            "label": "Export to Obsidian",
            "reason": "任务尚未完成",
            "target_path": "",
        }
    if not vault_usable:
        return {
            "enabled": False,
            "label": "Export to Obsidian",
            "reason": "Vault 未配置或不可用",
            "target_path": "",
        }
    return {
        "enabled": True,
        "label": "Export Research Index",
        "reason": None,
        "target_path": vault_path,
    }
