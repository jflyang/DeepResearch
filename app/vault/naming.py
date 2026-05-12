"""Vault 文件命名 - 清洗、截断、生成稳定文件名。"""

import re
import unicodedata

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_SPACE = re.compile(r"\s+")
_MULTI_DASH = re.compile(r"-{2,}")

DEFAULT_MAX_LENGTH = 120


def sanitize_filename(name: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """清洗文件名：去除非法字符，保留中文，限制长度。"""
    if not name:
        return "untitled"
    # 去除非法字符
    cleaned = _ILLEGAL_CHARS.sub("", name)
    # 规范化 Unicode
    cleaned = unicodedata.normalize("NFC", cleaned)
    # 去除首尾空白和点
    cleaned = cleaned.strip().strip(".")
    # 合并多余空格
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    # 截断
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip()
    return cleaned or "untitled"


def slugify(text: str, max_length: int = 60) -> str:
    """生成 URL-safe slug，保留中文。"""
    if not text:
        return "untitled"
    # 去除非法字符，空格转连字符
    slug = _ILLEGAL_CHARS.sub("", text)
    slug = slug.strip().lower()
    slug = _MULTI_SPACE.sub("-", slug)
    slug = _MULTI_DASH.sub("-", slug)
    slug = slug.strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug or "untitled"


def source_note_filename(
    date: str,
    title: str,
    domain: str,
    max_length: int = DEFAULT_MAX_LENGTH,
) -> str:
    """生成 source note 文件名：YYYY-MM-DD_{slug}_{domain}.md"""
    slug = slugify(title, max_length=50)
    domain_clean = domain.replace("www.", "").split("/")[0].split(":")[0]
    base = f"{date}_{slug}_{domain_clean}"
    if len(base) > max_length - 3:
        base = base[: max_length - 3]
    return f"{base}.md"
