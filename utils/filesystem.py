"""文件系统工具 - 文件名清洗、目录创建。"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# 文件名非法字符
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# 连续空白/下划线
_MULTI_SPACE = re.compile(r"[\s_]+")


def sanitize_filename(text: str, max_length: int = 120) -> str:
    """
    将文本转为安全的文件名。

    规则：
    - 移除非法字符
    - 空白替换为下划线
    - 限制长度
    - 去除首尾空白和点号
    """
    safe = _ILLEGAL_CHARS.sub("", text)
    safe = _MULTI_SPACE.sub("_", safe.strip())
    safe = safe.strip("._")
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip("_")
    return safe or "untitled"


def ensure_unique_path(path: Path) -> Path:
    """如果文件已存在，自动加数字后缀。"""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def ensure_dir(path: Path) -> Path:
    """确保目录存在。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_file(path: Path, content: str) -> Path:
    """写入文件，自动创建父目录。"""
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    logger.debug("file_written path=%s bytes=%d", path, len(content))
    return path
