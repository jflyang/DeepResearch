"""ReportParserService 单元测试。"""

import pytest

from app.services.report_parser_service import ReportParserService
from models.schemas import ParsedReport


@pytest.fixture
def parser():
    return ReportParserService()


class TestParseMarkdownLinks:
    def test_single_markdown_link(self, parser):
        text = "根据 [Tim Cook Biography](https://example.com/article) 的报道"
        result = parser.parse(text)
        assert len(result.urls) == 1
        assert result.urls[0].url == "https://example.com/article"
        assert result.urls[0].title_hint == "Tim Cook Biography"

    def test_multiple_markdown_links(self, parser):
        text = (
            "参考 [Article A](https://a.com/page) 和 "
            "[Article B](https://b.com/page) 的内容"
        )
        result = parser.parse(text)
        assert len(result.urls) == 2
        urls = {r.url for r in result.urls}
        assert "https://a.com/page" in urls
        assert "https://b.com/page" in urls


class TestParseBareUrls:
    def test_bare_url(self, parser):
        text = "详情见 https://example.com/research/2024 了解更多"
        result = parser.parse(text)
        assert len(result.urls) == 1
        assert result.urls[0].url == "https://example.com/research/2024"

    def test_bare_url_http(self, parser):
        text = "来源: http://legacy.example.org/data"
        result = parser.parse(text)
        assert len(result.urls) == 1
        assert result.urls[0].url == "http://legacy.example.org/data"


class TestParseFootnoteUrls:
    def test_footnote_bracket_number(self, parser):
        text = "正文内容\n[1] https://example.com/source1\n[2] https://example.com/source2"
        result = parser.parse(text)
        assert len(result.urls) == 2

    def test_footnote_caret_format(self, parser):
        text = "正文内容\n[^1]: https://example.com/footnote"
        result = parser.parse(text)
        assert len(result.urls) == 1
        assert result.urls[0].url == "https://example.com/footnote"


class TestParseHtmlLinks:
    def test_html_a_tag(self, parser):
        text = '参考 <a href="https://example.com/page">Example Title</a> 的内容'
        result = parser.parse(text)
        assert len(result.urls) == 1
        assert result.urls[0].url == "https://example.com/page"
        assert result.urls[0].title_hint == "Example Title"

    def test_html_a_tag_single_quotes(self, parser):
        text = "<a href='https://example.com/single'>Link</a>"
        result = parser.parse(text)
        assert len(result.urls) == 1
        assert result.urls[0].url == "https://example.com/single"


class TestUrlDeduplication:
    def test_same_url_different_formats(self, parser):
        text = (
            "[Article](https://example.com/page) 和裸链接 "
            "https://example.com/page 是同一个来源"
        )
        result = parser.parse(text)
        assert len(result.urls) == 1

    def test_same_url_with_and_without_tracking(self, parser):
        text = (
            "来源1: https://example.com/page?utm_source=twitter\n"
            "来源2: https://example.com/page?utm_medium=social"
        )
        result = parser.parse(text)
        # 去除 tracking 参数后 URL 相同，应去重
        assert len(result.urls) == 1
        assert "utm_" not in result.urls[0].url


class TestUrlTrackingRemoval:
    def test_removes_utm_params(self, parser):
        text = "https://example.com/article?utm_source=twitter&utm_medium=social&id=123"
        result = parser.parse(text)
        assert len(result.urls) == 1
        assert "utm_source" not in result.urls[0].url
        assert "utm_medium" not in result.urls[0].url
        assert "id=123" in result.urls[0].url

    def test_removes_fbclid(self, parser):
        text = "https://example.com/page?fbclid=abc123&valid=1"
        result = parser.parse(text)
        assert "fbclid" not in result.urls[0].url
        assert "valid=1" in result.urls[0].url

    def test_removes_gclid(self, parser):
        text = "https://example.com/page?gclid=xyz789"
        result = parser.parse(text)
        assert "gclid" not in result.urls[0].url


class TestParseChineseBooks:
    def test_chinese_book_title(self, parser):
        text = "在《蒂姆·库克传》中详细描述了他的管理风格"
        result = parser.parse(text)
        assert len(result.books) == 1
        assert result.books[0].title == "蒂姆·库克传"

    def test_multiple_chinese_books(self, parser):
        text = "《乔布斯传》和《蒂姆·库克传》都是关于苹果的书"
        result = parser.parse(text)
        assert len(result.books) == 2
        titles = {b.title for b in result.books}
        assert "乔布斯传" in titles
        assert "蒂姆·库克传" in titles

    def test_short_title_ignored(self, parser):
        """单字书名号内容不应被识别（太短，可能是引用标记）。"""
        text = "他说《好》就是好"
        result = parser.parse(text)
        assert len(result.books) == 0


class TestParseEnglishBooks:
    def test_book_by_author(self, parser):
        text = '"Tim Cook: The Genius Who Took Apple to the Next Level" by Leander Kahney'
        result = parser.parse(text)
        assert len(result.books) == 1
        assert "Tim Cook" in result.books[0].title
        assert result.books[0].author_hint == "Leander Kahney"

    def test_book_prefix(self, parser):
        text = "Book: Tim Cook: The Genius Who Took Apple to the Next Level"
        result = parser.parse(text)
        assert len(result.books) == 1
        assert "Tim Cook" in result.books[0].title

    def test_curly_quotes(self, parser):
        text = '\u201cSteve Jobs\u201d by Walter Isaacson'
        result = parser.parse(text)
        assert len(result.books) == 1
        assert result.books[0].title == "Steve Jobs"
        assert result.books[0].author_hint == "Walter Isaacson"


class TestParseDoi:
    def test_doi_with_prefix(self, parser):
        text = "该论文的标识为 DOI: 10.1145/3292500.3330648"
        result = parser.parse(text)
        assert len(result.papers) == 1
        assert result.papers[0].doi_hint == "10.1145/3292500.3330648"

    def test_doi_url_format(self, parser):
        text = "全文链接: doi.org/10.1038/s41586-021-03819-2"
        result = parser.parse(text)
        assert len(result.papers) == 1
        assert result.papers[0].doi_hint == "10.1038/s41586-021-03819-2"

    def test_doi_deduplication(self, parser):
        text = (
            "DOI: 10.1145/3292500.3330648 在正文中提到，"
            "参考文献也列出了 doi.org/10.1145/3292500.3330648"
        )
        result = parser.parse(text)
        assert len(result.papers) == 1


class TestParseArxiv:
    def test_arxiv_id(self, parser):
        text = "Transformer 论文 arXiv:1706.03762 开创了新范式"
        result = parser.parse(text)
        assert len(result.papers) == 1
        assert result.papers[0].arxiv_id == "1706.03762"

    def test_arxiv_with_version(self, parser):
        text = "GPT-4 技术报告 arXiv:2303.08774v2"
        result = parser.parse(text)
        assert len(result.papers) == 1
        assert result.papers[0].arxiv_id == "2303.08774v2"

    def test_arxiv_case_insensitive(self, parser):
        text = "参考 ARXIV: 2301.00001 的方法"
        result = parser.parse(text)
        assert len(result.papers) == 1
        assert result.papers[0].arxiv_id == "2301.00001"


class TestSurroundingText:
    def test_surrounding_text_not_empty(self, parser):
        text = "A" * 300 + " [Link](https://example.com) " + "B" * 300
        result = parser.parse(text)
        assert len(result.urls) == 1
        surrounding = result.urls[0].surrounding_text
        assert surrounding is not None
        assert len(surrounding) > 0
        # 应包含链接本身
        assert "https://example.com" in surrounding

    def test_surrounding_text_for_books(self, parser):
        text = "前文" * 50 + "《深度学习》" + "后文" * 50
        result = parser.parse(text)
        assert len(result.books) == 1
        assert result.books[0].surrounding_text is not None
        assert "深度学习" in result.books[0].surrounding_text

    def test_surrounding_text_for_papers(self, parser):
        text = "前文" * 50 + " DOI: 10.1000/test.123 " + "后文" * 50
        result = parser.parse(text)
        assert len(result.papers) == 1
        assert result.papers[0].surrounding_text is not None
        assert "10.1000/test.123" in result.papers[0].surrounding_text


class TestEdgeCases:
    def test_empty_text_raises(self, parser):
        with pytest.raises(ValueError):
            parser.parse("")

    def test_no_references(self, parser):
        text = "这是一段没有任何引用的普通文本。"
        result = parser.parse(text)
        assert result.urls == []
        assert result.books == []
        assert result.papers == []

    def test_returns_parsed_report_type(self, parser):
        text = "https://example.com"
        result = parser.parse(text)
        assert isinstance(result, ParsedReport)

    def test_complex_report(self, parser):
        """模拟一份包含多种引用格式的报告。"""
        text = """
# Tim Cook 研究报告

## 背景

根据 [Forbes Profile](https://forbes.com/profile/tim-cook) 的报道，
Tim Cook 于 1960 年出生于阿拉巴马州。

在《蒂姆·库克传》中详细描述了他的早期经历。英文版
"Tim Cook: The Genius Who Took Apple to the Next Level" by Leander Kahney
也有类似描述。

## 学术研究

关于苹果供应链管理的研究见 DOI: 10.1287/mnsc.2019.3404，
以及 arXiv:2106.09685 关于大语言模型的论文。

## 参考文献

[1] https://www.apple.com/leadership/tim-cook/
[^2]: https://en.wikipedia.org/wiki/Tim_Cook

<a href="https://hbr.org/tim-cook-interview">HBR Interview</a>
"""
        result = parser.parse(text)
        assert len(result.urls) >= 4
        assert len(result.books) >= 2
        assert len(result.papers) == 2
