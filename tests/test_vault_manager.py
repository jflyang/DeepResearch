"""VaultManager 测试。"""

from pathlib import Path

import pytest

from app.vault.errors import VaultFileExistsError
from app.vault.manager import VaultManager
from app.vault.workspace import VaultWorkspace


@pytest.fixture
def vault(tmp_path: Path) -> VaultManager:
    ws = VaultWorkspace(root_path=tmp_path)
    ws.ensure_base_dirs()
    return VaultManager(workspace=ws)


class TestEnsureWorkspace:
    def test_creates_base_dirs(self, tmp_path: Path) -> None:
        ws = VaultWorkspace(root_path=tmp_path)
        mgr = VaultManager(workspace=ws)
        mgr.ensure_workspace()
        assert (tmp_path / "Topics").exists()
        assert (tmp_path / "Entities").exists()
        assert (tmp_path / "Concepts").exists()


class TestEnsureTopicWorkspace:
    def test_creates_topic_dirs(self, vault: VaultManager, tmp_path: Path) -> None:
        vault.ensure_topic_workspace("量子计算")
        topic_dir = tmp_path / "Topics" / "量子计算"
        assert topic_dir.exists()
        assert (topic_dir / "sources").exists()
        assert (topic_dir / "cards").exists()
        assert (topic_dir / "timeline").exists()
        assert (topic_dir / "attachments").exists()


class TestSaveSourceNote:
    def test_creates_file(self, vault: VaultManager, tmp_path: Path) -> None:
        path = vault.save_source_note(
            topic="AI",
            title="Research Paper",
            url="https://arxiv.org/abs/123",
            domain="arxiv.org",
            content="张三 published a paper on AI.",
            source_level="A",
            people=["张三"],
        )
        assert path.exists()
        assert path.suffix == ".md"
        content = path.read_text(encoding="utf-8")
        assert "Research Paper" in content
        assert "https://arxiv.org/abs/123" in content
        assert "[[张三]]" in content

    def test_no_overwrite_creates_suffix(self, vault: VaultManager) -> None:
        path1 = vault.save_source_note(
            topic="AI", title="Same Title", url="http://a.com", domain="a.com", content="v1",
        )
        path2 = vault.save_source_note(
            topic="AI", title="Same Title", url="http://a.com", domain="a.com", content="v2",
            overwrite=False,
        )
        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_frontmatter_valid_yaml(self, vault: VaultManager) -> None:
        import yaml
        path = vault.save_source_note(
            topic="Test", title="Title", url="http://x.com", domain="x.com",
            content="body", people=["A", "B"], concepts=["C"],
        )
        text = path.read_text(encoding="utf-8")
        # 提取 frontmatter
        parts = text.split("---")
        assert len(parts) >= 3
        fm = yaml.safe_load(parts[1])
        assert fm["title"] == "Title"
        assert fm["url"] == "http://x.com"
        assert fm["people"] == ["A", "B"]


class TestSaveTopicIndex:
    def test_creates_index(self, vault: VaultManager, tmp_path: Path) -> None:
        path = vault.save_topic_index(
            topic="量子计算",
            must_read=["Paper A", "Paper B"],
            people=["Feynman"],
            organizations=["IBM"],
        )
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "量子计算" in content
        assert "Paper A" in content
        assert "[[Feynman]]" in content
        assert "[[IBM]]" in content

    def test_overwrite_false_raises(self, vault: VaultManager) -> None:
        vault.save_topic_index(topic="Test", overwrite=True)
        with pytest.raises(VaultFileExistsError):
            vault.save_topic_index(topic="Test", overwrite=False)


class TestSaveEntityNote:
    def test_creates_entity_note(self, vault: VaultManager, tmp_path: Path) -> None:
        path = vault.save_entity_note("Elon Musk", entity_type="person")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Elon Musk" in content
        assert "type: person" in content

    def test_does_not_overwrite(self, vault: VaultManager) -> None:
        path1 = vault.save_entity_note("张三", entity_type="person")
        # 写入自定义内容
        path1.write_text("custom content", encoding="utf-8")
        # 再次调用不应覆盖
        path2 = vault.save_entity_note("张三", entity_type="person")
        assert path1 == path2
        assert path2.read_text(encoding="utf-8") == "custom content"


class TestSaveConceptNote:
    def test_creates_concept_note(self, vault: VaultManager, tmp_path: Path) -> None:
        path = vault.save_concept_note("深度学习")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "深度学习" in content
        assert "type: concept" in content


class TestSaveCard:
    def test_creates_card(self, vault: VaultManager) -> None:
        path = vault.save_card(
            topic="AI",
            title="Key Finding",
            content="Important discovery.",
            card_type="fact",
        )
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Key Finding" in content
        assert "type: fact" in content

    def test_no_overwrite(self, vault: VaultManager) -> None:
        path1 = vault.save_card(topic="AI", title="Same", content="v1")
        path2 = vault.save_card(topic="AI", title="Same", content="v2", overwrite=False)
        assert path1 != path2


class TestEnsureAttachmentDir:
    def test_creates_dir(self, vault: VaultManager, tmp_path: Path) -> None:
        path = vault.ensure_attachment_dir("AI")
        assert path.exists()
        assert path.is_dir()
        assert "attachments" in str(path)
