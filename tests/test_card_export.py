"""研究卡片导出测试。"""

import pytest
from pathlib import Path

from app.ai.schemas import (
    FinalIndexSynthesisOutput,
    SynthesisKeyPerson,
    SynthesisKeyPlace,
    SynthesisStoryPoint,
    SynthesisVerificationWarning,
)
from models.enums import SourceLevel, SourceType, TaskMode, TaskStatus
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from services.card_export_service import export_research_cards


@pytest.fixture
def task():
    return ResearchTask(
        id="test-cards-001",
        topic="Tim Cook 童年故事",
        mode=TaskMode.PERSON,
        status=TaskStatus.COMPLETED,
    )


@pytest.fixture
def sources():
    return [
        SourceItem(
            id="s1",
            task_id="test-cards-001",
            title="Tim Cook Biography",
            url="https://example.com/bio",
            domain="example.com",
            source_type=SourceType.NEWS,
            source_level=SourceLevel.S,
        ),
    ]


@pytest.fixture
def extracted_docs():
    return {
        "s1": ExtractedDocument(
            source_item_id="s1",
            title="Tim Cook Biography",
            author="John Smith",
            content="Full text...",
            people=["Tim Cook", "Steve Jobs", "Donald Cook"],
            places=["Robertsdale", "Alabama", "Auburn University"],
            concepts=["Apple", "Leadership", "Supply Chain"],
            events=["1960 年出生于 Alabama", "1982 年 Auburn 毕业"],
        ),
    }


@pytest.fixture
def synthesis():
    return FinalIndexSynthesisOutput(
        overview="研究概览",
        key_people=[
            SynthesisKeyPerson(name="Tim Cook", role="研究主体", importance="high"),
            SynthesisKeyPerson(name="Steve Jobs", role="前任 CEO", importance="high"),
        ],
        key_places=[
            SynthesisKeyPlace(name="Robertsdale", significance="Tim Cook 出生地"),
            SynthesisKeyPlace(name="Auburn University", significance="Cook 的大学"),
        ],
        key_concepts=["Apple", "Leadership"],
        story_points=[
            SynthesisStoryPoint(point="Cook 在小镇长大", source="传记", verified=False),
        ],
        verification_warnings=[
            SynthesisVerificationWarning(claim="Cook 家境贫寒", source="网络", risk="未验证"),
        ],
    )


class TestCardGeneration:
    """卡片生成测试。"""

    def test_generates_cards_directory(self, task, sources, extracted_docs, synthesis, tmp_path):
        """生成 cards/ 目录。"""
        count = export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        assert cards_dir.exists()
        assert count > 0

    def test_generates_person_cards(self, task, sources, extracted_docs, synthesis, tmp_path):
        """生成人物卡片。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        person_cards = list(cards_dir.glob("人物_*.md"))
        assert len(person_cards) >= 2  # Tim Cook + Steve Jobs at minimum

    def test_person_card_has_content(self, task, sources, extracted_docs, synthesis, tmp_path):
        """人物卡片有内容。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        person_cards = list(cards_dir.glob("人物_Tim_Cook*"))
        assert len(person_cards) == 1
        content = person_cards[0].read_text(encoding="utf-8")
        assert "Tim Cook" in content
        assert "person_card" in content
        assert "研究主体" in content  # role from synthesis

    def test_generates_place_cards(self, task, sources, extracted_docs, synthesis, tmp_path):
        """生成地点卡片。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        place_cards = list(cards_dir.glob("地点_*.md"))
        assert len(place_cards) >= 2

    def test_place_card_has_significance(self, task, sources, extracted_docs, synthesis, tmp_path):
        """地点卡片有意义说明。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        robertsdale_cards = list(cards_dir.glob("地点_Robertsdale*"))
        assert len(robertsdale_cards) == 1
        content = robertsdale_cards[0].read_text(encoding="utf-8")
        assert "出生地" in content

    def test_generates_concept_cards(self, task, sources, extracted_docs, synthesis, tmp_path):
        """生成概念卡片。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        concept_cards = list(cards_dir.glob("概念_*.md"))
        assert len(concept_cards) >= 2  # Apple, Leadership, Supply Chain

    def test_generates_story_cards(self, task, sources, extracted_docs, synthesis, tmp_path):
        """生成故事点卡片。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        story_cards = list(cards_dir.glob("故事_*.md"))
        assert len(story_cards) >= 1

    def test_story_card_has_verification_status(self, task, sources, extracted_docs, synthesis, tmp_path):
        """故事点卡片有验证状态。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        story_cards = list(cards_dir.glob("故事_*.md"))
        assert len(story_cards) >= 1
        content = story_cards[0].read_text(encoding="utf-8")
        assert "验证状态" in content

    def test_generates_unverified_cards(self, task, sources, extracted_docs, synthesis, tmp_path):
        """生成待核验卡片。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        unverified_cards = list(cards_dir.glob("待核验_*.md"))
        assert len(unverified_cards) >= 1
        content = unverified_cards[0].read_text(encoding="utf-8")
        assert "Cook 家境贫寒" in content
        assert "核验方法" in content

    def test_no_cards_without_extracted_docs(self, task, sources, tmp_path):
        """没有提取文档时不生成卡片。"""
        count = export_research_cards(task, sources, {}, tmp_path)
        assert count == 0

    def test_cards_have_frontmatter(self, task, sources, extracted_docs, synthesis, tmp_path):
        """卡片有 YAML frontmatter。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        all_cards = list(cards_dir.glob("*.md"))
        for card in all_cards:
            content = card.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{card.name} missing frontmatter"
            assert "research-card" in content

    def test_cards_have_obsidian_tags(self, task, sources, extracted_docs, synthesis, tmp_path):
        """卡片有 Obsidian 标签。"""
        export_research_cards(task, sources, extracted_docs, tmp_path, synthesis)
        cards_dir = tmp_path / "Research" / "Tim_Cook_童年故事" / "cards"
        person_cards = list(cards_dir.glob("人物_*.md"))
        content = person_cards[0].read_text(encoding="utf-8")
        assert "tags:" in content
        assert "person" in content
