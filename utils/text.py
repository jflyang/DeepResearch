"""文本处理工具。"""

import re


def sanitize_filename(text: str, max_length: int = 80) -> str:
    """将文本转为安全的文件名。"""
    # 移除非法字符
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    # 替换空格为下划线
    safe = re.sub(r"\s+", "_", safe.strip())
    return safe[:max_length]


def truncate(text: str, max_length: int = 200) -> str:
    """截断文本。"""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def count_words(text: str) -> int:
    """统计字数（中英文混合）。"""
    # 中文按字计数，英文按词计数
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    return chinese_chars + english_words
