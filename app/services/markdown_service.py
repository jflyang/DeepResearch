"""Markdown 渲染服务 - 将 SynthesizedResearchDocument 渲染为 Obsidian 兼容 index.md。

职责：
- 将 SynthesizedResearchDocument 渲染为高质量研究文档 Markdown
- 输出结构化、有来源引用、Obsidian 兼容的 index.md
- 不修改数据库、不写文件（只返回字符串）
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from models.enums import ClaimConfidence
from models.schemas import DeduplicatedClaimGroup, SynthesizedResearchDocument

if TYPE_CHECKING:
    from models.schemas import SourceItem


def render_synthesized_index(
    synthesis: SynthesizedResearchDocument,
    sources: list["SourceItem"] | None = None,
) -> str:
    """将 SynthesizedResearchDocument 渲染为 Obsidian 兼容 Markdown。

    Args:
        synthesis: 合成研究文档对象
        sources: 可选的 SourceItem 列表（用于补充来源地图信息）

    Returns:
        完整的 Markdown 文本
    """
    lines: list[str] = []

    # === YAML Frontmatter ===
    lines.append("---")
    lines.append(f'title: "{synthesis.topic}｜研究文档"')
    lines.append(f'created_at: "{synthesis.generated_at}"')
    lines.append('status: "completed"')
    lines.append("synthesis: true")
    lines.append("tags:")
    lines.append("  - research-index")
    lines.append("  - synthesized")
    lines.append("---")
    lines.append("")

    # === 标题 ===
    lines.append(f"# {synthesis.topic}｜研究文档")
    lines.append("")

    # === 一、研究概览 ===
    lines.append("## 一、研究概览")
    lines.append("")
    if synthesis.overview:
        lines.append(synthesis.overview)
    else:
        lines.append(f"关于「{synthesis.topic}」的研究资料正在整理中。")
    lines.append("")

    # === 二、核心摘要 ===
    lines.append("## 二、核心摘要")
    lines.append("")
    if synthesis.executive_summary:
        lines.append(synthesis.executive_summary)
    else:
        lines.append("暂无核心摘要。")
    lines.append("")

    # === 三、已确认的关键信息 ===
    lines.append("## 三、已确认的关键信息")
    lines.append("")
    if synthesis.confirmed_facts:
        for i, fact in enumerate(synthesis.confirmed_facts, 1):
            lines.append(f"### {i}. {fact.merged_claim}")
            lines.append("")
            # 置信度标注
            confidence_label = _confidence_label(fact.confidence)
            if confidence_label:
                lines.append(f"**置信度：** {confidence_label}")
                lines.append("")
            # 来源列表（含等级）
            lines.append("**来源：**")
            lines.append("")
            for src in fact.supporting_sources:
                title = src.get("title", "")
                url = src.get("url", "")
                source_id = src.get("source_id", "")
                source_level = src.get("source_level", "")
                level_badge = f"[{source_level}] " if source_level else ""
                if url:
                    lines.append(f"- {level_badge}[{title or '未命名来源'}]({url})")
                elif title:
                    lines.append(f"- {level_badge}{title} (source_id: {source_id})")
                elif source_id:
                    lines.append(f"- {level_badge}source_id: {source_id}")
            lines.append("")
    else:
        lines.append("暂无高置信度已确认事实。建议补充更多一手资料。")
        lines.append("")

    # === 四、时间线 ===
    lines.append("## 四、时间线")
    lines.append("")
    if synthesis.timeline:
        lines.append("| 时间 | 事件 | 来源 |")
        lines.append("|---|---|---|")
        for event in synthesis.timeline:
            date_str = ", ".join(event.dates) if event.dates else "—"
            claim = event.merged_claim.replace("|", "\\|")
            source_label = _first_source_label(event)
            lines.append(f"| {date_str} | {claim} | {source_label} |")
        lines.append("")
    else:
        lines.append("暂无时间线信息。")
        lines.append("")

    # === 五、相关人物 ===
    lines.append("## 五、相关人物")
    lines.append("")
    if synthesis.key_people:
        for person in synthesis.key_people:
            name = person.get("name", "未知")
            lines.append(f"### {name}")
            lines.append("")
            desc = person.get("description", "")
            relation = person.get("relation_to_topic", "")
            person_sources = person.get("sources", [])
            if desc:
                lines.append(f"- **身份/说明：** {desc}")
            if relation:
                lines.append(f"- **与主题关系：** {relation}")
            if person_sources:
                source_strs = [_format_source_ref(s) for s in person_sources]
                lines.append(f"- **来源：** {', '.join(source_strs)}")
            lines.append("")
    else:
        lines.append("暂无相关人物信息。")
        lines.append("")

    # === 六、相关地点 ===
    lines.append("## 六、相关地点")
    lines.append("")
    if synthesis.key_places:
        for place in synthesis.key_places:
            name = place.get("name", "未知")
            desc = place.get("description", place.get("relation_to_topic", ""))
            lines.append(f"- **{name}**：{desc}")
        lines.append("")
    else:
        lines.append("暂无相关地点信息。")
        lines.append("")

    # === 七、重点名词 ===
    lines.append("## 七、重点名词")
    lines.append("")
    if synthesis.key_concepts:
        for concept in synthesis.key_concepts:
            if isinstance(concept, dict):
                name = concept.get("name", "")
                desc = concept.get("description", "")
                lines.append(f"- **{name}**：{desc}")
            else:
                lines.append(f"- {concept}")
        lines.append("")
    else:
        lines.append("暂无重点名词。")
        lines.append("")

    # === 八、可用于播客的故事点 ===
    lines.append("## 八、可用于播客的故事点")
    lines.append("")
    if synthesis.story_points:
        for sp in synthesis.story_points:
            lines.append(f"- {sp.merged_claim}")
            source_label = _first_source_label(sp)
            if source_label:
                lines.append(f"  - 来源：{source_label}")
        lines.append("")
    else:
        lines.append("暂无故事点。")
        lines.append("")

    # === 九、图书与深度资料 ===
    lines.append("## 九、图书与深度资料")
    lines.append("")
    book_sources = _extract_book_sources(synthesis, sources)
    if book_sources:
        for book in book_sources:
            title = book.get("title", "未知")
            lines.append(f"### 《{title}》")
            lines.append("")
            if book.get("title_zh"):
                lines.append(f"- **中文名：** {book['title_zh']}")
            if book.get("author"):
                lines.append(f"- **作者：** {book['author']}")
            if book.get("book_type"):
                lines.append(f"- **类型：** {book['book_type']}")
            if book.get("why_read"):
                lines.append(f"- **为什么值得看：** {book['why_read']}")
            if book.get("status"):
                lines.append(f"- **当前状态：** {book['status']}")
            lines.append("")
    else:
        lines.append("暂无图书与深度资料。")
        lines.append("")

    # === 十、冲突与待核验信息 ===
    lines.append("## 十、冲突与待核验信息")
    lines.append("")
    verification_items = synthesis.controversies + synthesis.verification_needed
    if verification_items:
        lines.append("| 说法 | 问题 | 下一步核验 | 来源 |")
        lines.append("|---|---|---|---|")
        for item in verification_items:
            claim = item.merged_claim.replace("|", "\\|")[:80]
            # 问题描述
            if item.conflicting_sources:
                problem = "来源冲突"
            elif item.needs_verification:
                problem = "待核验"
            else:
                problem = "置信度不足"
            # 下一步
            next_step = "交叉验证" if item.conflicting_sources else "补充来源"
            # 来源
            source_label = _first_source_label(item)
            lines.append(f"| {claim} | {problem} | {next_step} | {source_label} |")
        lines.append("")
    else:
        lines.append("暂无冲突或待核验信息。")
        lines.append("")

    # === 十一、资料来源地图 ===
    lines.append("## 十一、资料来源地图")
    lines.append("")
    if synthesis.source_map:
        for src_entry in synthesis.source_map:
            title = src_entry.get("title", "未命名")
            url = src_entry.get("url", "")
            source_id = src_entry.get("source_id", "")
            contribution = src_entry.get("contribution", "")

            # 尝试从 sources 列表补充信息
            source_item = _find_source_item(source_id, sources)
            extracted = _is_extracted(source_item)
            participated = True  # 在 source_map 中的都参与了合成

            if url:
                lines.append(f"- **[{title}]({url})**")
            else:
                lines.append(f"- **{title}** (source_id: {source_id})")

            details: list[str] = []
            if contribution:
                details.append(f"贡献：{contribution}")
            details.append(f"已抓取正文：{'是' if extracted else '否'}")
            details.append(f"参与合成：{'是' if participated else '否'}")
            if details:
                lines.append(f"  - {' | '.join(details)}")
        lines.append("")
    else:
        lines.append("暂无来源地图。")
        lines.append("")

    # === 十二、下一步深挖方向 ===
    lines.append("## 十二、下一步深挖方向")
    lines.append("")
    if synthesis.suggested_next_steps:
        for step in synthesis.suggested_next_steps:
            lines.append(f"- {step}")
        lines.append("")
    else:
        lines.append("- 补充更多一手资料")
        lines.append("- 交叉验证关键事实")
        lines.append("")

    return "\n".join(lines)


# === 工具函数 ===


def _first_source_label(group: DeduplicatedClaimGroup) -> str:
    """获取 group 的第一个来源标签。"""
    if not group.supporting_sources:
        return "—"
    src = group.supporting_sources[0]
    title = src.get("title", "")
    url = src.get("url", "")
    if url:
        return f"[{title or '来源'}]({url})"
    elif title:
        return title
    return src.get("source_id", "—")


def _format_source_ref(src: any) -> str:
    """格式化来源引用。"""
    if isinstance(src, dict):
        title = src.get("title", "")
        url = src.get("url", "")
        if url:
            return f"[{title or '来源'}]({url})"
        return title or src.get("source_id", "")
    return str(src)


def _extract_book_sources(
    synthesis: SynthesizedResearchDocument,
    sources: list["SourceItem"] | None,
) -> list[dict]:
    """从 source_map 和 sources 中提取图书来源。"""
    books: list[dict] = []

    # 从 sources 列表中找 book 类型
    if sources:
        for s in sources:
            if getattr(s, "source_type", "") == "book":
                books.append({
                    "title": getattr(s, "title", ""),
                    "title_zh": "",
                    "author": "",
                    "book_type": "book",
                    "why_read": getattr(s, "reason_to_read", ""),
                    "status": getattr(s, "download_status", "pending"),
                })

    return books


def _find_source_item(source_id: str, sources: list["SourceItem"] | None) -> "SourceItem | None":
    """在 sources 列表中查找指定 source_id。"""
    if not sources or not source_id:
        return None
    for s in sources:
        if getattr(s, "id", "") == source_id:
            return s
    return None


def _is_extracted(source_item: "SourceItem | None") -> bool:
    """判断来源是否已抓取正文。"""
    if source_item is None:
        return True  # 在 source_map 中默认已参与
    status = getattr(source_item, "download_status", "")
    return status in ("extracted", "exported")


def _confidence_label(confidence) -> str:
    """将 confidence 枚举转为中文标签。"""
    confidence_val = confidence.value if hasattr(confidence, "value") else str(confidence)
    labels = {
        "high": "🟢 高（多源确认）",
        "medium": "🟡 中",
        "low": "🟠 低（单源/B级来源）",
        "unverified": "⚪ 未验证",
        "conflicting": "🔴 来源冲突",
    }
    return labels.get(confidence_val, "")
