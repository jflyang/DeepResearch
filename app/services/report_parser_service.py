"""报告解析服务 - 从外部研究报告中提取引用（URL / 书籍 / 论文）。

纯正则解析，不调用 LLM，不访问网络，不写数据库。
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from models.schemas import (
    ExtractedBookReference,
    ExtractedPaperReference,
    ExtractedUrlReference,
    ParsedReport,
)

logger = logging.getLogger(__name__)

# === Tracking 参数黑名单 ===
_TRACKING_PARAMS = frozenset([
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "dclid", "msclkid", "twclid",
    "mc_cid", "mc_eid", "yclid", "ref", "source",
])

# === 正则模式 ===

# Markdown 链接: [title](url)
_RE_MARKDOWN_LINK = re.compile(
    r'\[([^\]]+)\]\((https?://[^\s\)]+)\)', re.IGNORECASE
)

# HTML <a> 标签
_RE_HTML_LINK = re.compile(
    r'<a\s[^>]*href=["\']?(https?://[^\s"\'<>]+)["\']?[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

# 脚注格式: [1] url 或 [^1]: url
_RE_FOOTNOTE_URL = re.compile(
    r'(?:^\[\^?\d+\]:?\s*)(https?://[^\s<>]+)', re.MULTILINE
)

# 裸 URL（排除已被 markdown/html/脚注捕获的）
_RE_BARE_URL = re.compile(
    r'(?<!\()'           # 不在 ( 后面（排除 markdown 链接内的 URL）
    r'(?<!["\'])'        # 不在引号后面（排除 HTML href 内的 URL）
    r'(https?://[^\s<>\)\]"\']+)',
    re.IGNORECASE,
)

# 中文书名号
_RE_CHINESE_BOOK = re.compile(r'《([^》]{2,50})》')

# 英文书名模式:
# 1. "Title" by Author  或  "Title", by Author
# 2. Book: Title
_RE_ENGLISH_BOOK_BY = re.compile(
    r'["""\u201c\u201d]([^"""\u201c\u201d]{5,80})["""\u201c\u201d],?\s+by\s+([A-Z][a-zA-Z\s\.\-]+)',
)
_RE_ENGLISH_BOOK_PREFIX = re.compile(
    r'(?:^|\n)\s*Book:\s*(.{5,100}?)(?:\n|$)', re.IGNORECASE
)

# DOI 模式
_RE_DOI = re.compile(
    r'(?:DOI:\s*|doi\.org/)(10\.\d{4,9}/[^\s,;\"\'<>\]]+)', re.IGNORECASE
)

# arXiv ID 模式
_RE_ARXIV = re.compile(
    r'arXiv[:\s]*(\d{4}\.\d{4,5}(?:v\d+)?)', re.IGNORECASE
)

# surrounding_text 截取半径
_CONTEXT_RADIUS = 200


class ReportParserService:
    """从研究报告文本中解析引用。

    不调用 LLM，不访问网络，不写数据库。
    解析失败返回空 ParsedReport，不抛出致命错误（report_text 为空时抛 ValueError）。
    """

    def parse(self, report_text: str) -> ParsedReport:
        """解析报告文本，返回 ParsedReport。"""
        if not report_text:
            raise ValueError("report_text must not be empty")

        try:
            urls = self._extract_urls(report_text)
            books = self._extract_books(report_text)
            papers = self._extract_papers(report_text)
            return ParsedReport(urls=urls, books=books, papers=papers)
        except Exception:
            logger.exception("Report parsing failed, returning empty ParsedReport")
            return ParsedReport()

    # ------------------------------------------------------------------
    # URL 提取
    # ------------------------------------------------------------------

    def _extract_urls(self, text: str) -> list[ExtractedUrlReference]:
        """提取所有 URL 引用并去重。"""
        seen_urls: set[str] = set()
        results: list[ExtractedUrlReference] = []

        # 1. Markdown 链接
        for m in _RE_MARKDOWN_LINK.finditer(text):
            title, raw_url = m.group(1), m.group(2)
            clean = self._clean_url(raw_url)
            if clean and clean not in seen_urls:
                seen_urls.add(clean)
                results.append(ExtractedUrlReference(
                    url=clean,
                    title_hint=title.strip(),
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    citation_marker=None,
                ))

        # 2. HTML <a> 标签
        for m in _RE_HTML_LINK.finditer(text):
            raw_url, title = m.group(1), m.group(2)
            clean = self._clean_url(raw_url)
            if clean and clean not in seen_urls:
                seen_urls.add(clean)
                # 去除 HTML 标签残留
                title_clean = re.sub(r'<[^>]+>', '', title).strip()
                results.append(ExtractedUrlReference(
                    url=clean,
                    title_hint=title_clean or None,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    citation_marker=None,
                ))

        # 3. 脚注 URL
        for m in _RE_FOOTNOTE_URL.finditer(text):
            raw_url = m.group(1)
            clean = self._clean_url(raw_url)
            if clean and clean not in seen_urls:
                seen_urls.add(clean)
                results.append(ExtractedUrlReference(
                    url=clean,
                    title_hint=None,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    citation_marker=m.group(0).split("]")[0] + "]" if "]" in m.group(0) else None,
                ))

        # 4. 裸 URL
        for m in _RE_BARE_URL.finditer(text):
            raw_url = m.group(1)
            # 跳过已经被 markdown/html/脚注捕获的
            clean = self._clean_url(raw_url)
            if clean and clean not in seen_urls:
                seen_urls.add(clean)
                results.append(ExtractedUrlReference(
                    url=clean,
                    title_hint=None,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    citation_marker=None,
                ))

        return results

    # ------------------------------------------------------------------
    # 书籍提取
    # ------------------------------------------------------------------

    def _extract_books(self, text: str) -> list[ExtractedBookReference]:
        """提取书籍引用。"""
        results: list[ExtractedBookReference] = []
        seen_titles: set[str] = set()

        # 中文书名号
        for m in _RE_CHINESE_BOOK.finditer(text):
            title = m.group(1).strip()
            if title and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                results.append(ExtractedBookReference(
                    title=title,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    confidence=0.7,
                ))

        # 英文 "Title" by Author
        for m in _RE_ENGLISH_BOOK_BY.finditer(text):
            title = m.group(1).strip()
            author = m.group(2).strip()
            if title and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                results.append(ExtractedBookReference(
                    title=title,
                    author_hint=author,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    confidence=0.6,
                ))

        # Book: Title
        for m in _RE_ENGLISH_BOOK_PREFIX.finditer(text):
            title = m.group(1).strip()
            if title and title.lower() not in seen_titles:
                seen_titles.add(title.lower())
                results.append(ExtractedBookReference(
                    title=title,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    confidence=0.8,
                ))

        return results

    # ------------------------------------------------------------------
    # 论文提取
    # ------------------------------------------------------------------

    def _extract_papers(self, text: str) -> list[ExtractedPaperReference]:
        """提取论文引用（仅 DOI 和 arXiv ID）。"""
        results: list[ExtractedPaperReference] = []
        seen: set[str] = set()

        # DOI
        for m in _RE_DOI.finditer(text):
            doi = m.group(1).rstrip(".")
            key = f"doi:{doi}"
            if key not in seen:
                seen.add(key)
                results.append(ExtractedPaperReference(
                    title=f"DOI:{doi}",
                    doi_hint=doi,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    confidence=0.9,
                ))

        # arXiv
        for m in _RE_ARXIV.finditer(text):
            arxiv_id = m.group(1)
            key = f"arxiv:{arxiv_id}"
            if key not in seen:
                seen.add(key)
                results.append(ExtractedPaperReference(
                    title=f"arXiv:{arxiv_id}",
                    arxiv_id=arxiv_id,
                    surrounding_text=self._get_surrounding(text, m.start(), m.end()),
                    confidence=0.9,
                ))

        return results

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _clean_url(self, url: str) -> str | None:
        """清理 URL：去除 tracking 参数，标准化。"""
        url = url.strip().rstrip(".,;:!?)")
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return None
            # 去除 tracking 参数
            params = parse_qs(parsed.query, keep_blank_values=False)
            cleaned_params = {
                k: v for k, v in params.items()
                if k.lower() not in _TRACKING_PARAMS
            }
            clean_query = urlencode(cleaned_params, doseq=True)
            cleaned = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                clean_query,
                "",  # 去除 fragment
            ))
            return cleaned
        except Exception:
            return None

    def _get_surrounding(self, text: str, start: int, end: int) -> str:
        """获取匹配位置前后约 200 字符的上下文。"""
        ctx_start = max(0, start - _CONTEXT_RADIUS)
        ctx_end = min(len(text), end + _CONTEXT_RADIUS)
        return text[ctx_start:ctx_end].strip()
