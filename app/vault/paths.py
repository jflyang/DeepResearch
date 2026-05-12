"""Vault 路径逻辑 - 所有目录结构集中管理。"""

from pathlib import Path

from app.vault.naming import sanitize_filename


class VaultPaths:
    """Vault 目录结构 helper。"""

    def __init__(
        self,
        root: Path,
        topics_dir: str = "Topics",
        entities_dir: str = "Entities",
        concepts_dir: str = "Concepts",
    ) -> None:
        self.root = root
        self._topics_dir = topics_dir
        self._entities_dir = entities_dir
        self._concepts_dir = concepts_dir

    @property
    def topics(self) -> Path:
        return self.root / self._topics_dir

    @property
    def entities(self) -> Path:
        return self.root / self._entities_dir

    @property
    def concepts(self) -> Path:
        return self.root / self._concepts_dir

    def topic_dir(self, topic: str) -> Path:
        safe = sanitize_filename(topic, max_length=80)
        return self.topics / safe

    def topic_index(self, topic: str) -> Path:
        return self.topic_dir(topic) / "index.md"

    def topic_sources(self, topic: str) -> Path:
        return self.topic_dir(topic) / "sources"

    def topic_cards(self, topic: str) -> Path:
        return self.topic_dir(topic) / "cards"

    def topic_timeline(self, topic: str) -> Path:
        return self.topic_dir(topic) / "timeline"

    def topic_attachments(self, topic: str) -> Path:
        return self.topic_dir(topic) / "attachments"

    def entity_note(self, entity_name: str) -> Path:
        safe = sanitize_filename(entity_name, max_length=100)
        return self.entities / f"{safe}.md"

    def concept_note(self, concept_name: str) -> Path:
        safe = sanitize_filename(concept_name, max_length=100)
        return self.concepts / f"{safe}.md"
