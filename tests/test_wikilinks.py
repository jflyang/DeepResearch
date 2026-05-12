"""Wikilinks 测试。"""

import pytest

from app.vault.wikilinks import apply_wikilinks, make_wikilink, make_wikilink_list


class TestApplyWikilinks:
    def test_basic_replacement(self) -> None:
        text = "Steve Jobs founded Apple."
        result = apply_wikilinks(text, ["Steve Jobs", "Apple"])
        assert "[[Steve Jobs]]" in result
        assert "[[Apple]]" in result

    def test_no_double_wrap(self) -> None:
        text = "Already linked [[Steve Jobs]] here."
        result = apply_wikilinks(text, ["Steve Jobs"])
        assert result.count("[[Steve Jobs]]") == 1
        assert "[[[[" not in result

    def test_case_insensitive(self) -> None:
        text = "steve jobs was a visionary."
        result = apply_wikilinks(text, ["Steve Jobs"])
        assert "[[Steve Jobs]]" in result

    def test_only_first_occurrence(self) -> None:
        text = "Apple makes iPhones. Apple also makes Macs."
        result = apply_wikilinks(text, ["Apple"])
        assert result.count("[[Apple]]") == 1

    def test_empty_entities(self) -> None:
        text = "No changes here."
        result = apply_wikilinks(text, [])
        assert result == text

    def test_longer_entity_first(self) -> None:
        text = "New York Times published an article about New York."
        result = apply_wikilinks(text, ["New York", "New York Times"])
        assert "[[New York Times]]" in result

    def test_chinese_entities(self) -> None:
        text = "张三在北京大学工作。"
        result = apply_wikilinks(text, ["张三", "北京大学"])
        assert "[[张三]]" in result
        assert "[[北京大学]]" in result


class TestMakeWikilink:
    def test_basic(self) -> None:
        assert make_wikilink("Test") == "[[Test]]"

    def test_chinese(self) -> None:
        assert make_wikilink("量子计算") == "[[量子计算]]"


class TestMakeWikilinkList:
    def test_basic(self) -> None:
        result = make_wikilink_list(["A", "B", "C"])
        assert result == "[[A]], [[B]], [[C]]"

    def test_empty(self) -> None:
        assert make_wikilink_list([]) == ""

    def test_filters_blank(self) -> None:
        result = make_wikilink_list(["A", "", "B", "  "])
        assert result == "[[A]], [[B]]"
