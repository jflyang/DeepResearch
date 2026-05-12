"""Wiki Links - 将已知 entity 自动替换为 [[entity]]。"""

import re


def apply_wikilinks(text: str, entities: list[str]) -> str:
    """将已知 entity 替换为 [[entity]]，不重复包裹。"""
    if not entities:
        return text

    result = text
    for entity in sorted(entities, key=len, reverse=True):
        if not entity.strip():
            continue
        # 不替换已在 [[ ]] 内的
        pattern = re.compile(
            r"(?<!\[\[)" + re.escape(entity) + r"(?!\]\])",
            re.IGNORECASE,
        )
        # 只替换第一次出现
        result = pattern.sub(f"[[{entity}]]", result, count=1)

    return result


def make_wikilink(name: str) -> str:
    """生成单个 wikilink。"""
    return f"[[{name}]]"


def make_wikilink_list(names: list[str]) -> str:
    """生成 wikilink 列表。"""
    return ", ".join(f"[[{n}]]" for n in names if n.strip())
