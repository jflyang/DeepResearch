"""Vault 路径逻辑测试。"""

from pathlib import Path

import pytest

from app.vault.paths import VaultPaths
from app.vault.workspace import VaultWorkspace
from app.vault.errors import VaultNotFoundError


class TestVaultPaths:
    def test_topic_dir(self, tmp_path: Path) -> None:
        paths = VaultPaths(root=tmp_path)
        result = paths.topic_dir("量子计算")
        assert result == tmp_path / "Topics" / "量子计算"

    def test_topic_sources(self, tmp_path: Path) -> None:
        paths = VaultPaths(root=tmp_path)
        result = paths.topic_sources("AI")
        assert result == tmp_path / "Topics" / "AI" / "sources"

    def test_topic_cards(self, tmp_path: Path) -> None:
        paths = VaultPaths(root=tmp_path)
        result = paths.topic_cards("AI")
        assert result == tmp_path / "Topics" / "AI" / "cards"

    def test_entity_note(self, tmp_path: Path) -> None:
        paths = VaultPaths(root=tmp_path)
        result = paths.entity_note("Elon Musk")
        assert result == tmp_path / "Entities" / "Elon Musk.md"

    def test_concept_note(self, tmp_path: Path) -> None:
        paths = VaultPaths(root=tmp_path)
        result = paths.concept_note("深度学习")
        assert result == tmp_path / "Concepts" / "深度学习.md"

    def test_custom_dirs(self, tmp_path: Path) -> None:
        paths = VaultPaths(root=tmp_path, topics_dir="研究", entities_dir="人物")
        assert paths.topics == tmp_path / "研究"
        assert paths.entities == tmp_path / "人物"


class TestVaultWorkspace:
    def test_ensure_base_dirs(self, tmp_path: Path) -> None:
        ws = VaultWorkspace(root_path=tmp_path)
        ws.ensure_base_dirs()
        assert (tmp_path / "Topics").exists()
        assert (tmp_path / "Entities").exists()
        assert (tmp_path / "Concepts").exists()

    def test_validate_existing(self, tmp_path: Path) -> None:
        ws = VaultWorkspace(root_path=tmp_path)
        ws.validate()  # 不应抛出

    def test_validate_missing_raises(self) -> None:
        ws = VaultWorkspace(root_path=Path("/nonexistent/vault/path"))
        with pytest.raises(VaultNotFoundError):
            ws.validate()

    def test_exists_property(self, tmp_path: Path) -> None:
        ws = VaultWorkspace(root_path=tmp_path)
        assert ws.exists is True

        ws2 = VaultWorkspace(root_path=Path("/nonexistent"))
        assert ws2.exists is False
