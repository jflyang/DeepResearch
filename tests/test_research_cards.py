"""研究卡片服务测试。"""

import pytest
from pathlib import Path

from models.enums import CardType, Confidence, DownloadStatus, SourceLevel, SourceType
from models.schemas import ExtractedDocument, ResearchCard, SourceItem
from services.research_card_service import (
    export_card_markdown,
    generate_cards,
    generate_concept_cards,
    generate_gossip_cards,
    generate_person_cards,
    generate_story_cards,
)


# === Fixtures ===


@pytest.fixture
def source_item():
    return SourceItem(
        task_id="task-1",
        title="Test Article",
        url="https://example.com/article",
        domain="example.com",
        source_type=SourceType.NEWS,
        source_level=SourceLevel.A,
        relevance_score=0.8,
        authority_score=0.7,
        originality_score=0.6,
        gossip_score=0.0,
        reason_to_read="[A] In-depth profile",
        download_status=DownloadStatus.EXTRACTED,
    )


@pytest.fixture
def extracted_doc(source_item):
    return ExtractedDocument(
        source_item_id=source_item.id,
        title="The Rise of Elon Musk",
        author="John Reporter",
        content=(
            "Elon Musk grew up in Pretoria, South Africa. His childhood was marked by "
            "a difficult relationship with his father.\n\n"
            "He co-founded Zip2 in 1995, which was his first major venture. The company "
            "was later sold to Compaq for $307 million.\n\n"
            "In 2008, Tesla faced a severe crisis and nearly went bankrupt. Musk invested "
            "his last $35 million to keep the company alive.\n\n"
            "There are persistent rumors about his personal life and dating history. "
            "Multiple sources allege various relationship controversies."
        ),
        people=["Elon Musk", "Errol Musk", "Kimbal Musk"],
        places=["Pretoria", "Silicon Valley"],
        organizations=["Tesla", "SpaceX", "Zip2"],
        concepts=["electric vehicles", "reusable rockets"],
        events=["Zip2 sale 1999", "Tesla crisis 2008"],
    )


@pytest.fixture
def gossip_source():
    return SourceItem(
        task_id="task-1",
        title="Celebrity Gossip",
        url="https://tmz.com/article",
        domain="tmz.com",
        source_type=SourceType.SOCIAL,
        source_level=SourceLevel.C,
        relevance_score=0.4,
        authority_score=0.2,
        originality_score=0.2,
        gossip_score=0.6,
        reason_to_read="[C] Gossip source",
        download_status=DownloadStatus.EXTRACTED,
    )


# === Person Cards ===


class TestPersonCards:
    def test_generates_card_per_person(self, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        assert len(cards) == 3  # Elon, Errol, Kimbal

    def test_card_title_is_person_name(self, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        titles = [c.title for c in cards]
        assert "Elon Musk" in titles
        assert "Errol Musk" in titles

    def test_card_links_source_url(self, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert source_item.url in card.linked_sources

    def test_card_type_is_fact(self, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert card.type == CardType.FACT

    def test_confidence_from_source_level(self, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        # source_level=A → LIKELY
        for card in cards:
            assert card.confidence == Confidence.LIKELY

    def test_empty_people_returns_empty(self, source_item):
        doc = ExtractedDocument(source_item_id=source_item.id, people=[])
        cards = generate_person_cards(doc, source_item, "task-1")
        assert cards == []


# === Concept Cards ===


class TestConceptCards:
    def test_generates_from_concepts(self, extracted_doc, source_item):
        cards = generate_concept_cards(extracted_doc, source_item, "task-1")
        titles = [c.title for c in cards]
        assert "electric vehicles" in titles
        assert "reusable rockets" in titles

    def test_generates_from_organizations(self, extracted_doc, source_item):
        cards = generate_concept_cards(extracted_doc, source_item, "task-1")
        titles = [c.title for c in cards]
        assert "Tesla" in titles
        assert "SpaceX" in titles

    def test_generates_from_places(self, extracted_doc, source_item):
        cards = generate_concept_cards(extracted_doc, source_item, "task-1")
        titles = [c.title for c in cards]
        assert "Pretoria" in titles
        assert "Silicon Valley" in titles

    def test_total_count(self, extracted_doc, source_item):
        cards = generate_concept_cards(extracted_doc, source_item, "task-1")
        # 2 concepts + 3 orgs + 2 places = 7
        assert len(cards) == 7


# === Story Cards ===


class TestStoryCards:
    def test_detects_childhood_paragraph(self, extracted_doc, source_item):
        cards = generate_story_cards(extracted_doc, source_item, "task-1")
        titles = [c.title for c in cards]
        # "grew up" matches
        assert any("Grew Up" in t or "Childhood" in t for t in titles)

    def test_detects_founding_paragraph(self, extracted_doc, source_item):
        cards = generate_story_cards(extracted_doc, source_item, "task-1")
        titles = [c.title for c in cards]
        assert any("Co-Founded" in t or "Founded" in t for t in titles)

    def test_detects_crisis_paragraph(self, extracted_doc, source_item):
        cards = generate_story_cards(extracted_doc, source_item, "task-1")
        titles = [c.title for c in cards]
        assert any("Crisis" in t or "Bankrupt" in t for t in titles)

    def test_card_type_is_timeline(self, extracted_doc, source_item):
        cards = generate_story_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert card.type == CardType.TIMELINE

    def test_content_is_paragraph_snippet(self, extracted_doc, source_item):
        cards = generate_story_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert len(card.content) > 0
            assert len(card.content) <= 303  # 300 + "..."

    def test_no_story_keywords_returns_empty(self, source_item):
        doc = ExtractedDocument(
            source_item_id=source_item.id,
            content="This is a plain technical document about algorithms.",
        )
        cards = generate_story_cards(doc, source_item, "task-1")
        assert cards == []


# === Gossip Cards ===


class TestGossipCards:
    def test_detects_gossip_keywords(self, extracted_doc, source_item):
        cards = generate_gossip_cards(extracted_doc, source_item, "task-1")
        # "rumors" and "personal life" and "relationship" in last paragraph
        assert len(cards) >= 1

    def test_gossip_source_with_keywords(self, extracted_doc, gossip_source):
        cards = generate_gossip_cards(extracted_doc, gossip_source, "task-1")
        assert len(cards) >= 1

    def test_card_type_is_controversy(self, extracted_doc, source_item):
        cards = generate_gossip_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert card.type == CardType.CONTROVERSY

    def test_confidence_is_rumor(self, extracted_doc, source_item):
        cards = generate_gossip_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert card.confidence == Confidence.RUMOR

    def test_no_gossip_returns_empty(self, source_item):
        doc = ExtractedDocument(
            source_item_id=source_item.id,
            content="A purely technical paper about quantum computing algorithms.",
        )
        cards = generate_gossip_cards(doc, source_item, "task-1")
        assert cards == []


# === Aggregate ===


class TestGenerateCards:
    def test_generates_all_types(self, extracted_doc, source_item):
        cards = generate_cards(extracted_doc, source_item, "task-1")
        types = {c.type for c in cards}
        assert CardType.FACT in types
        assert CardType.TIMELINE in types
        assert CardType.CONTROVERSY in types

    def test_all_cards_have_task_id(self, extracted_doc, source_item):
        cards = generate_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert card.task_id == "task-1"

    def test_all_cards_have_linked_sources(self, extracted_doc, source_item):
        cards = generate_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert len(card.linked_sources) > 0

    def test_returns_research_card_instances(self, extracted_doc, source_item):
        cards = generate_cards(extracted_doc, source_item, "task-1")
        for card in cards:
            assert isinstance(card, ResearchCard)


# === Export ===


class TestExportCardMarkdown:
    def test_creates_file(self, tmp_path, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        card = cards[0]
        path = export_card_markdown(card, tmp_path)
        assert path.exists()
        assert path.suffix == ".md"

    def test_file_contains_frontmatter(self, tmp_path, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        card = cards[0]
        path = export_card_markdown(card, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "confidence:" in content
        assert "type:" in content

    def test_file_contains_source_link(self, tmp_path, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        card = cards[0]
        path = export_card_markdown(card, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert source_item.url in content

    def test_updates_markdown_path(self, tmp_path, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        card = cards[0]
        path = export_card_markdown(card, tmp_path)
        assert card.markdown_path == str(path)

    def test_duplicate_names_get_suffix(self, tmp_path, extracted_doc, source_item):
        cards = generate_person_cards(extracted_doc, source_item, "task-1")
        card = cards[0]
        path1 = export_card_markdown(card, tmp_path)
        card2 = cards[0].model_copy()
        path2 = export_card_markdown(card2, tmp_path)
        assert path1 != path2
