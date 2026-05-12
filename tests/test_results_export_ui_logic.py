"""Results 页面纯函数逻辑测试。"""

import pytest


# === 辅助函数（从 Results 页面逻辑提取） ===


def classify_sources_for_ui(items: list[dict]) -> dict[str, list[dict]]:
    """前端轻量分类。"""
    result = {
        "必读资料": [],
        "一手资料": [],
        "深度报道": [],
        "图书资料": [],
        "采访与演讲": [],
        "八卦与旁证": [],
        "低质量隐藏": [],
    }

    for item in items:
        level = item.get("source_level", "C")
        stype = item.get("source_type", "other")
        gossip = item.get("gossip_score", 0)
        title_lower = item.get("title", "").lower()

        if level == "D":
            result["低质量隐藏"].append(item)
            continue

        if level in ("S", "A"):
            result["必读资料"].append(item)

        if stype in ("documentation", "government"):
            result["一手资料"].append(item)

        if stype == "book":
            result["图书资料"].append(item)

        if any(kw in title_lower for kw in ("interview", "speech", "talk", "keynote")):
            result["采访与演讲"].append(item)

        if level in ("S", "A") and len(item.get("snippet", "")) > 100:
            result["深度报道"].append(item)

        if gossip >= 0.3 or (level == "C" and gossip > 0):
            result["八卦与旁证"].append(item)

    return {k: v for k, v in result.items() if v}


def filter_sources(
    items: list[dict],
    level: str | None = None,
    source_type: str | None = None,
    keyword: str | None = None,
    hide_low: bool = True,
) -> list[dict]:
    """筛选来源。"""
    filtered = items.copy()

    if level and level != "全部":
        filtered = [i for i in filtered if i.get("source_level") == level]
    if source_type and source_type != "全部":
        filtered = [i for i in filtered if i.get("source_type") == source_type]
    if hide_low:
        filtered = [i for i in filtered if i.get("source_level") != "D"]
    if keyword:
        kw = keyword.lower()
        filtered = [
            i for i in filtered
            if kw in i.get("title", "").lower()
            or kw in i.get("domain", "").lower()
            or kw in i.get("snippet", "").lower()
        ]

    return filtered


def build_index_preview(topic: str, items: list[dict]) -> str:
    """生成研究索引预览 markdown。"""
    s_a = [i for i in items if i["source_level"] in ("S", "A")]
    books = [i for i in items if i["source_type"] == "book"]
    gossip = [i for i in items if i.get("gossip_score", 0) >= 0.3]

    lines = [
        f"# {topic}｜研究索引预览",
        "",
        "## 研究概览",
        f"- 来源总数：{len(items)}",
        f"- 高质量来源 (S/A)：{len(s_a)}",
        f"- 图书资料：{len(books)}",
        f"- 八卦与旁证：{len(gossip)}",
    ]

    if s_a:
        lines.append("")
        lines.append("## 必读资料")
        for item in s_a[:10]:
            lines.append(f"- **[{item['source_level']}]** {item['title']}")

    return "\n".join(lines)


def resolve_export_button_state(obsidian_settings: dict) -> dict:
    """根据 obsidian 配置决定导出按钮状态。"""
    configured = obsidian_settings.get("configured", False)
    exists = obsidian_settings.get("exists", False)
    writable = obsidian_settings.get("writable", False)

    if configured and exists and writable:
        return {"enabled": True, "message": None}
    elif configured and not exists:
        return {"enabled": False, "message": "Vault 路径不存在"}
    elif configured and not writable:
        return {"enabled": False, "message": "Vault 路径不可写"}
    else:
        return {"enabled": False, "message": "Vault 未配置"}


# === Tests ===


class TestClassifySources:
    def test_s_level_in_must_read(self):
        items = [{"source_level": "S", "source_type": "news", "title": "Test", "snippet": "x" * 200, "gossip_score": 0}]
        result = classify_sources_for_ui(items)
        assert "必读资料" in result
        assert len(result["必读资料"]) == 1

    def test_a_level_in_must_read(self):
        items = [{"source_level": "A", "source_type": "news", "title": "Test", "snippet": "x" * 200, "gossip_score": 0}]
        result = classify_sources_for_ui(items)
        assert "必读资料" in result

    def test_book_in_books(self):
        items = [{"source_level": "B", "source_type": "book", "title": "A Book", "snippet": "", "gossip_score": 0}]
        result = classify_sources_for_ui(items)
        assert "图书资料" in result
        assert len(result["图书资料"]) == 1

    def test_gossip_in_gossip(self):
        items = [{"source_level": "C", "source_type": "blog", "title": "Rumor", "snippet": "", "gossip_score": 0.5}]
        result = classify_sources_for_ui(items)
        assert "八卦与旁证" in result

    def test_d_level_in_low_quality(self):
        items = [{"source_level": "D", "source_type": "forum", "title": "Bad", "snippet": "", "gossip_score": 0}]
        result = classify_sources_for_ui(items)
        assert "低质量隐藏" in result
        assert "必读资料" not in result

    def test_interview_in_interviews(self):
        items = [{"source_level": "B", "source_type": "news", "title": "Interview with CEO", "snippet": "", "gossip_score": 0}]
        result = classify_sources_for_ui(items)
        assert "采访与演讲" in result


class TestFilterSources:
    def _items(self):
        return [
            {"source_level": "S", "source_type": "news", "title": "Apple CEO", "domain": "apple.com", "snippet": "official"},
            {"source_level": "A", "source_type": "book", "title": "Biography", "domain": "books.com", "snippet": "life story"},
            {"source_level": "D", "source_type": "forum", "title": "Random", "domain": "reddit.com", "snippet": "gossip"},
        ]

    def test_filter_by_level(self):
        result = filter_sources(self._items(), level="S")
        assert len(result) == 1
        assert result[0]["title"] == "Apple CEO"

    def test_filter_by_type(self):
        result = filter_sources(self._items(), source_type="book", hide_low=False)
        assert len(result) == 1
        assert result[0]["title"] == "Biography"

    def test_hide_low_quality(self):
        result = filter_sources(self._items(), hide_low=True)
        assert len(result) == 2
        assert all(i["source_level"] != "D" for i in result)

    def test_keyword_search(self):
        result = filter_sources(self._items(), keyword="apple", hide_low=False)
        assert len(result) == 1
        assert result[0]["domain"] == "apple.com"

    def test_no_filter_returns_all(self):
        result = filter_sources(self._items(), hide_low=False)
        assert len(result) == 3


class TestBuildIndexPreview:
    def test_contains_topic(self):
        items = [{"source_level": "S", "source_type": "news", "title": "Test", "gossip_score": 0}]
        preview = build_index_preview("Tim Cook", items)
        assert "Tim Cook" in preview

    def test_contains_stats(self):
        items = [
            {"source_level": "S", "source_type": "news", "title": "A", "gossip_score": 0},
            {"source_level": "B", "source_type": "book", "title": "B", "gossip_score": 0},
        ]
        preview = build_index_preview("Topic", items)
        assert "来源总数：2" in preview
        assert "高质量来源 (S/A)：1" in preview
        assert "图书资料：1" in preview

    def test_s_a_items_listed(self):
        items = [{"source_level": "A", "source_type": "news", "title": "Important Article", "gossip_score": 0}]
        preview = build_index_preview("Topic", items)
        assert "Important Article" in preview
        assert "必读资料" in preview


class TestResolveExportButtonState:
    def test_vault_usable(self):
        state = resolve_export_button_state({"configured": True, "exists": True, "writable": True})
        assert state["enabled"] is True
        assert state["message"] is None

    def test_vault_not_configured(self):
        state = resolve_export_button_state({"configured": False, "exists": False, "writable": False})
        assert state["enabled"] is False
        assert "未配置" in state["message"]

    def test_vault_not_exists(self):
        state = resolve_export_button_state({"configured": True, "exists": False, "writable": False})
        assert state["enabled"] is False
        assert "不存在" in state["message"]

    def test_vault_not_writable(self):
        state = resolve_export_button_state({"configured": True, "exists": True, "writable": False})
        assert state["enabled"] is False
        assert "不可写" in state["message"]
