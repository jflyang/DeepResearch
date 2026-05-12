"""研究卡片导出服务 - 生成 cards/*.md 文件。

从提取的文档中收集人物、地点、概念、故事点、待核验信息，
为每个实体生成独立的 Obsidian 卡片文件。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from utils.filesystem import ensure_dir, sanitize_filename, write_file

if TYPE_CHECKING:
    from app.ai.schemas import FinalIndexSynthesisOutput

logger = logging.getLogger(__name__)


def export_research_cards(
    task: ResearchTask,
    sources: list[SourceItem],
    extracted_docs: dict[str, ExtractedDocument],
    vault_path: Path,
    synthesis: "FinalIndexSynthesisOutput | None" = None,
) -> int:
    """
    生成研究卡片到 cards/ 目录。

    卡片类型：
    - 人物卡片（person）
    - 地点卡片（place）
    - 概念卡片（concept）
    - 故事点卡片（story）
    - 待核验卡片（unverified）

    Returns:
        生成的卡片数量
    """
    research_dir = vault_path / "Research" / sanitize_filename(task.topic, max_length=80)
    cards_dir = ensure_dir(research_dir / "cards")

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    card_count = 0

    # 收集所有实体
    people = _collect_people(extracted_docs, synthesis)
    places = _collect_places(extracted_docs, synthesis)
    concepts = _collect_concepts(extracted_docs, synthesis)
    story_points = _collect_story_points(extracted_docs, synthesis)
    unverified = _collect_unverified(synthesis)

    # 生成人物卡片
    for person in people:
        try:
            _write_person_card(cards_dir, person, task.topic, now)
            card_count += 1
        except Exception as e:
            logger.warning("card_export_failed type=person name=%s error=%s", person["name"], str(e)[:80])

    # 生成地点卡片
    for place in places:
        try:
            _write_place_card(cards_dir, place, task.topic, now)
            card_count += 1
        except Exception as e:
            logger.warning("card_export_failed type=place name=%s error=%s", place["name"], str(e)[:80])

    # 生成概念卡片
    for concept in concepts:
        try:
            _write_concept_card(cards_dir, concept, task.topic, now)
            card_count += 1
        except Exception as e:
            logger.warning("card_export_failed type=concept name=%s error=%s", concept, str(e)[:80])

    # 生成故事点卡片
    for story in story_points:
        try:
            _write_story_card(cards_dir, story, task.topic, now)
            card_count += 1
        except Exception as e:
            logger.warning("card_export_failed type=story error=%s", str(e)[:80])

    # 生成待核验卡片
    for item in unverified:
        try:
            _write_unverified_card(cards_dir, item, task.topic, now)
            card_count += 1
        except Exception as e:
            logger.warning("card_export_failed type=unverified error=%s", str(e)[:80])

    logger.info("cards_exported task_id=%s count=%d", task.id, card_count)
    return card_count


# === 实体收集 ===


def _collect_people(
    extracted_docs: dict[str, ExtractedDocument],
    synthesis: "FinalIndexSynthesisOutput | None",
) -> list[dict]:
    """收集人物信息，去重合并。"""
    people: dict[str, dict] = {}

    # 从 extracted docs 收集
    for doc in extracted_docs.values():
        for person in doc.people:
            if person and person not in people:
                people[person] = {
                    "name": person,
                    "role": "",
                    "importance": "medium",
                    "sources": [doc.title],
                }
            elif person in people:
                people[person]["sources"].append(doc.title)

    # 从 synthesis 补充
    if synthesis:
        for sp in synthesis.key_people:
            if sp.name in people:
                people[sp.name]["role"] = sp.role
                people[sp.name]["importance"] = sp.importance
            elif sp.name:
                people[sp.name] = {
                    "name": sp.name,
                    "role": sp.role,
                    "importance": sp.importance,
                    "sources": [],
                }

    return list(people.values())


def _collect_places(
    extracted_docs: dict[str, ExtractedDocument],
    synthesis: "FinalIndexSynthesisOutput | None",
) -> list[dict]:
    """收集地点信息。"""
    places: dict[str, dict] = {}

    for doc in extracted_docs.values():
        for place in doc.places:
            if place and place not in places:
                places[place] = {
                    "name": place,
                    "significance": "",
                    "sources": [doc.title],
                }
            elif place in places:
                places[place]["sources"].append(doc.title)

    if synthesis:
        for sp in synthesis.key_places:
            if sp.name in places:
                places[sp.name]["significance"] = sp.significance
            elif sp.name:
                places[sp.name] = {
                    "name": sp.name,
                    "significance": sp.significance,
                    "sources": [],
                }

    return list(places.values())


def _collect_concepts(
    extracted_docs: dict[str, ExtractedDocument],
    synthesis: "FinalIndexSynthesisOutput | None",
) -> list[str]:
    """收集概念/关键词。"""
    concepts: set[str] = set()

    for doc in extracted_docs.values():
        concepts.update(c for c in doc.concepts if c)

    if synthesis:
        concepts.update(c for c in synthesis.key_concepts if c)

    return sorted(concepts)


def _collect_story_points(
    extracted_docs: dict[str, ExtractedDocument],
    synthesis: "FinalIndexSynthesisOutput | None",
) -> list[dict]:
    """收集故事点。"""
    stories: list[dict] = []

    # 从 extracted docs 的 events 字段
    for doc in extracted_docs.values():
        for event in doc.events:
            if event:
                stories.append({
                    "point": event,
                    "source": doc.title,
                    "verified": True,  # 来自正文
                })

    # 从 synthesis
    if synthesis:
        for sp in synthesis.story_points:
            if sp.point and not any(s["point"] == sp.point for s in stories):
                stories.append({
                    "point": sp.point,
                    "source": sp.source,
                    "verified": sp.verified,
                })

    return stories[:20]  # 限制数量


def _collect_unverified(
    synthesis: "FinalIndexSynthesisOutput | None",
) -> list[dict]:
    """收集待核验信息。"""
    if not synthesis:
        return []
    return [
        {"claim": vw.claim, "source": vw.source, "risk": vw.risk}
        for vw in synthesis.verification_warnings
        if vw.claim
    ]


# === 卡片写入 ===


def _write_person_card(cards_dir: Path, person: dict, topic: str, now: str) -> None:
    """写入人物卡片。"""
    name = person["name"]
    filename = sanitize_filename(f"人物_{name}") + ".md"
    path = cards_dir / filename

    sources_list = person.get("sources", [])
    sources_str = "\n".join(f"- {s}" for s in sources_list[:5]) if sources_list else "- （待补充）"

    content = f"""---
title: "{name}"
type: person_card
topic: "{topic}"
importance: "{person.get('importance', 'medium')}"
created: "{now}"
tags:
  - person
  - research-card
---

# {name}

## 与研究主题的关系

{person.get('role', '待确认')}

## 重要性

{person.get('importance', 'medium')}

## 出现来源

{sources_str}

## 备注

（待补充）
"""
    write_file(path, content)


def _write_place_card(cards_dir: Path, place: dict, topic: str, now: str) -> None:
    """写入地点卡片。"""
    name = place["name"]
    filename = sanitize_filename(f"地点_{name}") + ".md"
    path = cards_dir / filename

    sources_list = place.get("sources", [])
    sources_str = "\n".join(f"- {s}" for s in sources_list[:5]) if sources_list else "- （待补充）"

    content = f"""---
title: "{name}"
type: place_card
topic: "{topic}"
created: "{now}"
tags:
  - place
  - research-card
---

# {name}

## 与研究主题的关系

{place.get('significance', '待确认')}

## 出现来源

{sources_str}

## 备注

（待补充）
"""
    write_file(path, content)


def _write_concept_card(cards_dir: Path, concept: str, topic: str, now: str) -> None:
    """写入概念卡片。"""
    filename = sanitize_filename(f"概念_{concept}") + ".md"
    path = cards_dir / filename

    content = f"""---
title: "{concept}"
type: concept_card
topic: "{topic}"
created: "{now}"
tags:
  - concept
  - research-card
---

# {concept}

## 定义

（待补充）

## 与研究主题的关系

（待补充）

## 备注

（待补充）
"""
    write_file(path, content)


def _write_story_card(cards_dir: Path, story: dict, topic: str, now: str) -> None:
    """写入故事点卡片。"""
    point = story["point"]
    # 用故事点前 30 字符作为文件名
    short_name = point[:30].replace("\n", " ")
    filename = sanitize_filename(f"故事_{short_name}") + ".md"
    path = cards_dir / filename

    verified_str = "✅ 已从正文确认" if story.get("verified") else "⚠️ 待核验"

    content = f"""---
title: "{point[:60]}"
type: story_card
topic: "{topic}"
verified: {str(story.get('verified', False)).lower()}
created: "{now}"
tags:
  - story
  - research-card
---

# 故事点

{point}

## 来源

{story.get('source', '未知')}

## 验证状态

{verified_str}

## 可用于

- 播客叙事
- 文章开头
- 人物侧写

## 备注

（待补充）
"""
    write_file(path, content)


def _write_unverified_card(cards_dir: Path, item: dict, topic: str, now: str) -> None:
    """写入待核验卡片。"""
    claim = item["claim"]
    short_name = claim[:30].replace("\n", " ")
    filename = sanitize_filename(f"待核验_{short_name}") + ".md"
    path = cards_dir / filename

    content = f"""---
title: "{claim[:60]}"
type: unverified_card
topic: "{topic}"
created: "{now}"
tags:
  - unverified
  - research-card
---

# ⚠️ 待核验

{claim}

## 来源

{item.get('source', '未知')}

## 风险

{item.get('risk', '未评估')}

## 核验方法

- 查找一手来源确认
- 交叉验证其他资料
- 联系当事人确认

## 状态

- [ ] 已核验
- [ ] 已否定
- [ ] 无法确认
"""
    write_file(path, content)
