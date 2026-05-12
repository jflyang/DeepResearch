"""Entity Note 管理 - 确保 entity note 存在但不覆盖。"""

from pathlib import Path

from app.vault.frontmatter import render_frontmatter
from app.vault.paths import VaultPaths


def ensure_entity_note(
    paths: VaultPaths,
    entity_name: str,
    entity_type: str = "person",
) -> Path:
    """确保 entity note 存在，不覆盖已有内容。返回文件路径。"""
    note_path = paths.entity_note(entity_name)
    if note_path.exists():
        return note_path

    note_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = render_frontmatter({
        "type": entity_type,
        "aliases": [],
    })
    content = f"{frontmatter}\n# {entity_name}\n\n## Related Topics\n"

    note_path.write_text(content, encoding="utf-8")
    return note_path


def ensure_concept_note(
    paths: VaultPaths,
    concept_name: str,
) -> Path:
    """确保 concept note 存在，不覆盖已有内容。"""
    note_path = paths.concept_note(concept_name)
    if note_path.exists():
        return note_path

    note_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = render_frontmatter({
        "type": "concept",
    })
    content = f"{frontmatter}\n# {concept_name}\n\n## Related Topics\n"

    note_path.write_text(content, encoding="utf-8")
    return note_path
