"""VaultManager - Vault 文件写入的唯一入口。"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.vault.entity_linker import ensure_concept_note, ensure_entity_note
from app.vault.errors import VaultFileExistsError, VaultWriteError
from app.vault.frontmatter import render_frontmatter, source_frontmatter
from app.vault.naming import sanitize_filename, source_note_filename
from app.vault.templates import render_topic_index
from app.vault.wikilinks import apply_wikilinks
from app.vault.workspace import VaultWorkspace

logger = logging.getLogger(__name__)


class VaultManager:
    """Vault 文件写入的唯一入口。业务 service 不允许直接写文件。"""

    def __init__(self, workspace: VaultWorkspace) -> None:
        self._ws = workspace

    @property
    def workspace(self) -> VaultWorkspace:
        return self._ws

    def ensure_workspace(self) -> None:
        """确保 Vault 基础目录存在。"""
        self._ws.ensure_base_dirs()

    def ensure_topic_workspace(self, topic: str) -> Path:
        """确保 topic 目录结构存在，返回 topic 目录路径。"""
        paths = self._ws.paths
        topic_dir = paths.topic_dir(topic)
        topic_dir.mkdir(parents=True, exist_ok=True)
        paths.topic_sources(topic).mkdir(parents=True, exist_ok=True)
        paths.topic_cards(topic).mkdir(parents=True, exist_ok=True)
        paths.topic_timeline(topic).mkdir(parents=True, exist_ok=True)
        paths.topic_attachments(topic).mkdir(parents=True, exist_ok=True)
        return topic_dir

    def save_source_note(
        self,
        topic: str,
        title: str,
        url: str,
        domain: str,
        content: str,
        source_level: str = "",
        people: list[str] | None = None,
        organizations: list[str] | None = None,
        places: list[str] | None = None,
        concepts: list[str] | None = None,
        published_at: str = "",
        overwrite: bool = False,
    ) -> Path:
        """保存 source note 到 topic/sources/ 目录。"""
        self.ensure_topic_workspace(topic)
        sources_dir = self._ws.paths.topic_sources(topic)

        date_str = published_at[:10] if published_at else datetime.now(UTC).strftime("%Y-%m-%d")
        filename = source_note_filename(date_str, title, domain)
        file_path = sources_dir / filename

        if file_path.exists() and not overwrite:
            file_path = self._unique_path(file_path)

        # 生成 frontmatter
        fm = source_frontmatter(
            title=title,
            url=url,
            source=domain,
            source_level=source_level,
            topic=topic,
            people=people,
            organizations=organizations,
            places=places,
            concepts=concepts,
            published_at=published_at,
            accessed_at=datetime.now(UTC).isoformat(),
        )

        # 应用 wikilinks
        all_entities = (people or []) + (organizations or []) + (places or [])
        body = apply_wikilinks(content, all_entities)

        full_content = f"{fm}\n# {title}\n\n{body}\n"
        self._write(file_path, full_content)

        logger.info("vault_source_saved path=%s", file_path)
        return file_path

    def save_topic_index(
        self,
        topic: str,
        must_read: list[str] | None = None,
        primary: list[str] | None = None,
        deep_profile: list[str] | None = None,
        books: list[str] | None = None,
        gossip: list[str] | None = None,
        people: list[str] | None = None,
        organizations: list[str] | None = None,
        timeline: list[str] | None = None,
        unverified: list[str] | None = None,
        overwrite: bool = True,
    ) -> Path:
        """保存 topic index.md。"""
        self.ensure_topic_workspace(topic)
        index_path = self._ws.paths.topic_index(topic)

        if index_path.exists() and not overwrite:
            raise VaultFileExistsError(
                f"Topic index already exists: {index_path}",
                path=str(index_path),
            )

        content = render_topic_index(
            topic=topic,
            must_read=must_read,
            primary=primary,
            deep_profile=deep_profile,
            books=books,
            gossip=gossip,
            people=people,
            organizations=organizations,
            timeline=timeline,
            unverified=unverified,
        )

        self._write(index_path, content)
        logger.info("vault_topic_index_saved topic=%s", topic)
        return index_path

    def save_entity_note(
        self,
        entity_name: str,
        entity_type: str = "person",
    ) -> Path:
        """确保 entity note 存在（不覆盖）。"""
        return ensure_entity_note(self._ws.paths, entity_name, entity_type)

    def save_concept_note(self, concept_name: str) -> Path:
        """确保 concept note 存在（不覆盖）。"""
        return ensure_concept_note(self._ws.paths, concept_name)

    def save_card(
        self,
        topic: str,
        title: str,
        content: str,
        card_type: str = "fact",
        overwrite: bool = False,
    ) -> Path:
        """保存研究卡片到 topic/cards/ 目录。"""
        self.ensure_topic_workspace(topic)
        cards_dir = self._ws.paths.topic_cards(topic)

        filename = sanitize_filename(title, max_length=80) + ".md"
        file_path = cards_dir / filename

        if file_path.exists() and not overwrite:
            file_path = self._unique_path(file_path)

        fm = render_frontmatter({"type": card_type, "topic": topic})
        full = f"{fm}\n# {title}\n\n{content}\n"
        self._write(file_path, full)
        return file_path

    def ensure_attachment_dir(self, topic: str) -> Path:
        """确保 attachments 目录存在，返回路径。"""
        self.ensure_topic_workspace(topic)
        return self._ws.paths.topic_attachments(topic)

    def _write(self, path: Path, content: str) -> None:
        """统一写入，UTF-8。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            raise VaultWriteError(
                f"Failed to write: {e}",
                path=str(path),
            ) from e

    def _unique_path(self, path: Path) -> Path:
        """文件冲突时自动加 suffix。"""
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
