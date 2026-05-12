"""Vault 内置模板 - Topic Index 等。"""

from app.vault.wikilinks import make_wikilink, make_wikilink_list

_TOPIC_INDEX_TEMPLATE = """# {topic}｜研究索引

## 必读资料

{must_read}

## 一手资料

{primary}

## 深度报道

{deep_profile}

## 图书资料

{books}

## 八卦与旁证

{gossip}

## 相关人物

{people}

## 相关公司

{organizations}

## 时间线

{timeline}

## 待核验信息

{unverified}
"""


def render_topic_index(
    topic: str,
    must_read: list[str] | None = None,
    primary: list[str] | None = None,
    deep_profile: list[str] | None = None,
    books: list[str] | None = None,
    gossip: list[str] | None = None,
    people: list[str] | None = None,
    organizations: list[str] | None = None,
    timeline: list[str] | None = None,
    unverified: list[str] | None = None,
) -> str:
    """渲染 topic index Markdown。"""

    def _format_list(items: list[str] | None, as_wikilinks: bool = False) -> str:
        if not items:
            return "（暂无）"
        if as_wikilinks:
            return "\n".join(f"- {make_wikilink(i)}" for i in items)
        return "\n".join(f"- {i}" for i in items)

    return _TOPIC_INDEX_TEMPLATE.format(
        topic=topic,
        must_read=_format_list(must_read),
        primary=_format_list(primary),
        deep_profile=_format_list(deep_profile),
        books=_format_list(books),
        gossip=_format_list(gossip),
        people=_format_list(people, as_wikilinks=True),
        organizations=_format_list(organizations, as_wikilinks=True),
        timeline=_format_list(timeline),
        unverified=_format_list(unverified),
    )
