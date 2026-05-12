"""Feature flags - 从环境变量读取功能开关。"""

import os


def env_bool(key: str, default: bool = True) -> bool:
    """读取环境变量作为布尔值。"""
    val = os.environ.get(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def env_str(key: str, default: str = "") -> str:
    """读取环境变量字符串值。"""
    return os.environ.get(key, default).strip()


def env_has_value(key: str) -> bool:
    """检查环境变量是否有非空值。"""
    return bool(os.environ.get(key, "").strip())
