"""Vault 文件命名测试。"""

import pytest

from app.vault.naming import sanitize_filename, slugify, source_note_filename


class TestSanitizeFilename:
    def test_basic(self) -> None:
        assert sanitize_filename("hello world") == "hello world"

    def test_removes_illegal_chars(self) -> None:
        assert sanitize_filename('file<>:"/\\|?*name') == "filename"

    def test_preserves_chinese(self) -> None:
        assert sanitize_filename("量子计算综述") == "量子计算综述"

    def test_max_length(self) -> None:
        long = "a" * 200
        result = sanitize_filename(long, max_length=50)
        assert len(result) <= 50

    def test_empty_returns_untitled(self) -> None:
        assert sanitize_filename("") == "untitled"

    def test_strips_dots(self) -> None:
        assert sanitize_filename("...test...") == "test"

    def test_collapses_spaces(self) -> None:
        assert sanitize_filename("hello   world") == "hello world"


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("Hello World") == "hello-world"

    def test_chinese(self) -> None:
        result = slugify("量子计算")
        assert "量子计算" in result

    def test_max_length(self) -> None:
        result = slugify("a" * 100, max_length=20)
        assert len(result) <= 20

    def test_empty(self) -> None:
        assert slugify("") == "untitled"

    def test_removes_illegal(self) -> None:
        result = slugify("test:file?name")
        assert ":" not in result
        assert "?" not in result


class TestSourceNoteFilename:
    def test_format(self) -> None:
        result = source_note_filename("2026-05-11", "Tim Cook Childhood", "wsj.com")
        assert result == "2026-05-11_tim-cook-childhood_wsj.com.md"

    def test_strips_www(self) -> None:
        result = source_note_filename("2026-01-01", "Article", "www.nytimes.com")
        assert "nytimes.com" in result
        assert "www." not in result

    def test_max_length(self) -> None:
        result = source_note_filename("2026-01-01", "A" * 200, "example.com", max_length=60)
        assert len(result) <= 63  # 60 + .md

    def test_chinese_title(self) -> None:
        result = source_note_filename("2026-05-11", "量子计算综述", "arxiv.org")
        assert result.startswith("2026-05-11_")
        assert result.endswith(".md")
        assert "arxiv.org" in result
