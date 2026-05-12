"""Vault Frontmatter 生成 - YAML 合法序列化。"""

from datetime import datetime
from typing import Any

import yaml


def render_frontmatter(fields: dict[str, Any]) -> str:
    """生成 YAML frontmatter 块。"""
    # 过滤 None 值
    clean: dict[str, Any] = {}
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, datetime):
            clean[k] = v.isoformat()
        elif isinstance(v, list):
            clean[k] = v if v else []
        else:
            clean[k] = v

    yaml_str = yaml.dump(
        clean,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip()

    return f"---\n{yaml_str}\n---\n"


def source_frontmatter(
    title: str,
    url: str,
    source: str = "",
    source_level: str = "",
    topic: str = "",
    people: list[str] | None = None,
    organizations: list[str] | None = None,
    places: list[str] | None = None,
    concepts: list[str] | None = None,
    published_at: str = "",
    accessed_at: str = "",
    status: str = "extracted",
) -> str:
    """生成 source note frontmatter。"""
    return render_frontmatter({
        "title": title,
        "url": url,
        "source": source,
        "source_level": source_level,
        "topic": topic,
        "people": people or [],
        "organizations": organizations or [],
        "places": places or [],
        "concepts": concepts or [],
        "published_at": published_at,
        "accessed_at": accessed_at,
        "status": status,
    })
