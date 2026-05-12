"""ContentExtractor - 从 HTML 中提取正文。

使用 trafilatura（项目已有依赖）作为主要提取器，
BeautifulSoup 作为 fallback。

不依赖 extraction_service，避免循环依赖。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContentExtractor:
    """从 HTML 提取正文的工具类。

    策略：trafilatura 优先 → BeautifulSoup fallback。
    """

    def extract_from_html(self, html: str, url: str | None = None) -> dict[str, Any]:
        """从 HTML 中提取正文。

        Args:
            html: 原始 HTML 内容
            url: 页面 URL（用于 trafilatura 的 URL 感知提取）

        Returns:
            dict with keys: title, text, content_chars, metadata
        """
        if not html or not html.strip():
            return {"title": "", "text": "", "content_chars": 0, "metadata": {}}

        # 1. 尝试 trafilatura
        result = self._extract_with_trafilatura(html, url)
        if result and result.get("text") and len(result["text"]) > 100:
            return result

        # 2. Fallback: BeautifulSoup
        result = self._extract_with_beautifulsoup(html)
        return result

    def _extract_with_trafilatura(self, html: str, url: str | None = None) -> dict[str, Any] | None:
        """使用 trafilatura 提取正文。"""
        try:
            import trafilatura

            # trafilatura 提取正文
            text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_precision=True,
            )

            if not text:
                return None

            # 提取元数据
            metadata = trafilatura.extract_metadata(html, default_url=url)

            title = ""
            if metadata:
                title = metadata.title or ""

            return {
                "title": title,
                "text": text,
                "content_chars": len(text),
                "metadata": {
                    "extractor": "trafilatura",
                    "author": metadata.author if metadata else None,
                    "date": str(metadata.date) if metadata and metadata.date else None,
                    "sitename": metadata.sitename if metadata else None,
                },
            }

        except Exception as e:
            logger.debug("trafilatura_extraction_failed url=%s error=%s", url, str(e)[:100])
            return None

    def _extract_with_beautifulsoup(self, html: str) -> dict[str, Any]:
        """使用 BeautifulSoup 提取正文（fallback）。"""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # 提取 title
            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

            # 移除无关标签
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]):
                tag.decompose()

            # 尝试找到主要内容区域
            main_content = (
                soup.find("article")
                or soup.find("main")
                or soup.find(attrs={"role": "main"})
                or soup.find("div", class_=lambda c: c and ("content" in c or "article" in c or "post" in c))
            )

            if main_content:
                text = main_content.get_text(separator="\n", strip=True)
            else:
                # 使用 body
                body = soup.find("body")
                text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

            # 清理多余空行
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n".join(lines)

            return {
                "title": title,
                "text": text,
                "content_chars": len(text),
                "metadata": {"extractor": "beautifulsoup"},
            }

        except Exception as e:
            logger.warning("beautifulsoup_extraction_failed error=%s", str(e)[:100])
            return {"title": "", "text": "", "content_chars": 0, "metadata": {"extractor": "failed"}}
