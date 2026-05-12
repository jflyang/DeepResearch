"""Playwright 浏览器正文提取器 - 用于 JavaScript 渲染页面。

当 trafilatura 无法获取内容时（如 SPA、JS 渲染页面），
使用 headless 浏览器加载页面后再提取正文。

依赖：playwright（可选依赖，未安装时优雅降级）。
安装：pip install playwright && playwright install chromium
"""

import asyncio
import logging

from providers.extraction.base import BaseExtractor, ExtractedContent

logger = logging.getLogger(__name__)

# 检查 playwright 是否可用
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


def is_playwright_available() -> bool:
    """检查 playwright 是否已安装。"""
    return _PLAYWRIGHT_AVAILABLE


class PlaywrightExtractor(BaseExtractor):
    """使用 Playwright headless 浏览器提取网页正文。

    适用于：
    - JavaScript 渲染的页面
    - 需要模拟真实浏览器访问的网站
    - trafilatura 无法获取内容的页面
    """

    def __init__(self, timeout_ms: int = 30000, wait_for_idle: bool = True):
        self._timeout_ms = timeout_ms
        self._wait_for_idle = wait_for_idle

    @property
    def name(self) -> str:
        return "playwright"

    async def extract(self, url: str) -> ExtractedContent:
        """使用 headless 浏览器提取网页正文。"""
        if not _PLAYWRIGHT_AVAILABLE:
            return ExtractedContent(
                source_url=url,
                success=False,
                error="Playwright 未安装。请运行: pip install playwright && playwright install chromium",
            )

        if not url or not url.startswith(("http://", "https://")):
            return ExtractedContent(
                source_url=url,
                success=False,
                error="Invalid URL",
            )

        logger.info("extraction_started extractor=%s url=%s", self.name, url)

        try:
            return await self._extract_with_browser(url)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            logger.warning("extraction_failed extractor=%s url=%s error=%s", self.name, url, error_msg)
            return ExtractedContent(
                source_url=url,
                success=False,
                error=error_msg,
            )

    async def _extract_with_browser(self, url: str) -> ExtractedContent:
        """启动浏览器，加载页面，提取正文。"""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()

                # 导航到页面
                await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)

                # 等待网络空闲（JS 渲染完成）
                if self._wait_for_idle:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass  # 超时不影响，继续提取

                # 获取页面标题
                title = await page.title()

                # 提取正文：优先用 article/main，否则用 body
                text = await self._extract_text_from_page(page)

                if not text or not text.strip():
                    return ExtractedContent(
                        source_url=url,
                        success=False,
                        error="Browser rendered page but extracted empty content",
                    )

                # 尝试获取作者
                author = await self._extract_author(page)

                logger.info(
                    "extraction_completed extractor=%s url=%s chars=%d title=%s",
                    self.name, url, len(text), title[:50],
                )

                return ExtractedContent(
                    title=title,
                    author=author,
                    source_url=url,
                    text=text,
                    success=True,
                    metadata={"extractor": "playwright"},
                )

            finally:
                await browser.close()

    async def _extract_text_from_page(self, page) -> str:
        """从页面提取正文，尝试多种选择器。"""
        # 优先级：article > main > [role=main] > body
        selectors = [
            "article",
            "main",
            "[role='main']",
            ".post-content",
            ".article-content",
            ".entry-content",
            "#content",
            ".content",
        ]

        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and len(text.strip()) > 200:
                        return self._clean_text(text)
            except Exception:
                continue

        # Fallback: 整个 body
        try:
            body = await page.query_selector("body")
            if body:
                text = await body.inner_text()
                return self._clean_text(text)
        except Exception:
            pass

        return ""

    async def _extract_author(self, page) -> str:
        """尝试从页面提取作者信息。"""
        author_selectors = [
            "meta[name='author']",
            "[rel='author']",
            ".author",
            ".byline",
        ]

        for selector in author_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # meta 标签用 content 属性
                    content = await element.get_attribute("content")
                    if content:
                        return content.strip()
                    # 其他元素用 inner_text
                    text = await element.inner_text()
                    if text and len(text.strip()) < 100:
                        return text.strip()
            except Exception:
                continue

        return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        """清理提取的文本。"""
        import re
        # 移除多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 移除行首尾空白
        lines = [line.strip() for line in text.split('\n')]
        # 移除过短的行（可能是导航/按钮文本）
        # 但保留空行作为段落分隔
        cleaned = []
        for line in lines:
            if not line:
                if cleaned and cleaned[-1]:  # 避免连续空行
                    cleaned.append("")
            else:
                cleaned.append(line)
        return '\n'.join(cleaned).strip()
