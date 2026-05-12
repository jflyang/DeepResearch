"""文件驱动的研究合成服务 - 从 sources/ 目录读取 .md 文件，合并为 research.md。

工作流程：
1. 用户点击"提取" → 异步抓取正文 → 保存为 .md 到 Obsidian/Research/{topic}/sources/
2. 用户点击"清洗并合成研究文档" → 读取 sources/ 下所有 .md → 提取事实 → 去重 → 合成 → 写入 research.md

本服务负责第 2 步：从文件系统读取已清洗的 source notes，合并为研究文档。
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_research_dir(vault_path: str, topic: str) -> Path:
    """获取研究目录路径。"""
    from utils.filesystem import sanitize_filename
    safe_topic = sanitize_filename(topic, max_length=80)
    return Path(vault_path) / "Research" / safe_topic


def get_sources_dir(vault_path: str, topic: str) -> Path:
    """获取 sources 子目录路径。"""
    return get_research_dir(vault_path, topic) / "sources"


def list_source_files(vault_path: str, topic: str) -> list[Path]:
    """列出 sources/ 目录下所有 .md 文件。"""
    sources_dir = get_sources_dir(vault_path, topic)
    if not sources_dir.exists():
        # 尝试直接用 topic 名（兼容已有目录）
        alt_dir = Path(vault_path) / "Research" / topic / "sources"
        if alt_dir.exists():
            sources_dir = alt_dir
        else:
            return []
    return sorted(sources_dir.glob("*.md"))


def read_source_file(path: Path) -> dict:
    """读取单个 source .md 文件，解析 frontmatter 和正文。

    Returns:
        {
            "path": str,
            "filename": str,
            "title": str,
            "url": str,
            "source_level": str,
            "source_type": str,
            "topic": str,
            "people": list,
            "places": list,
            "summary": str,
            "content": str,
            "key_quotes": list,
            "concepts": list,
        }
    """
    text = path.read_text(encoding="utf-8")

    # 解析 YAML frontmatter
    frontmatter = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                pass
            body = parts[2].strip()

    # 提取各节内容
    sections = _parse_sections(body)

    return {
        "path": str(path),
        "filename": path.name,
        "title": frontmatter.get("title", path.stem),
        "url": frontmatter.get("url", ""),
        "source_level": frontmatter.get("source_level", ""),
        "source_type": frontmatter.get("source_type", ""),
        "topic": frontmatter.get("topic", ""),
        "people": frontmatter.get("people", []),
        "places": frontmatter.get("places", []),
        "summary": sections.get("摘要", sections.get("中文摘要", "")),
        "content": sections.get("正文", sections.get("原文正文", "")),
        "key_quotes": _extract_quotes(sections.get("关键摘录", "")),
        "concepts": frontmatter.get("concepts", []) or _extract_list(sections.get("重点名词", "")),
        "key_points": _extract_list(sections.get("关键事实", "")),
        "story_points": _extract_list(sections.get("可用于播客的故事点", "")),
        "reason_to_read": sections.get("为什么值得看", ""),
    }


def synthesize_from_source_files(
    vault_path: str,
    topic: str,
) -> dict:
    """从 sources/ 目录读取所有 .md 文件，合成为 research.md。

    Args:
        vault_path: Obsidian vault 路径
        topic: 研究主题

    Returns:
        {
            "success": bool,
            "source_count": int,
            "research_path": str,
            "error": str | None,
        }
    """
    source_files = list_source_files(vault_path, topic)

    if not source_files:
        return {
            "success": False,
            "source_count": 0,
            "research_path": "",
            "error": "sources/ 目录下没有 .md 文件。请先提取来源正文。",
        }

    # 读取所有 source 文件
    source_data: list[dict] = []
    book_count = 0
    for path in source_files:
        try:
            data = read_source_file(path)
            # 跳过图书类来源（图书作为参考资料单独展示，不参与正文合成）
            if data.get("source_type") == "book":
                book_count += 1
                logger.debug("skip_book_in_synthesis path=%s", path)
                continue
            source_data.append(data)
        except Exception as e:
            logger.warning("read_source_file_failed path=%s error=%s", path, str(e))

    if not source_data:
        if book_count > 0:
            return {
                "success": False,
                "source_count": 0,
                "research_path": "",
                "error": f"sources/ 目录下有 {book_count} 个图书文件，但没有可合成的正文来源。图书不参与合成，请先提取非图书来源的正文。",
            }
        return {
            "success": False,
            "source_count": 0,
            "research_path": "",
            "error": "无法读取 sources/ 目录下的文件。",
        }
        return {
            "success": False,
            "source_count": 0,
            "research_path": "",
            "error": "无法读取 sources/ 目录下的文件。",
        }

    # 合成 research.md
    research_content = _render_merged_index(topic, source_data)

    # 写入 research.md（使用 source 文件所在的 research 目录）
    first_source_path = Path(source_data[0]["path"])
    research_dir = first_source_path.parent.parent  # sources/ 的上级
    research_path = research_dir / "research.md"
    research_path.write_text(research_content, encoding="utf-8")

    logger.info(
        "file_based_synthesis_done topic=%s sources=%d research=%s",
        topic, len(source_data), research_path,
    )

    return {
        "success": True,
        "source_count": len(source_data),
        "research_path": str(research_path),
        "error": None,
    }


# === 内部方法 ===


def _parse_sections(body: str) -> dict[str, str]:
    """解析 Markdown 正文为 {section_title: content} 字典。"""
    sections: dict[str, str] = {}
    current_title = ""
    current_lines: list[str] = []

    for line in body.split("\n"):
        if line.startswith("# ") and not line.startswith("## "):
            # 一级标题
            if current_title:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = line[2:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title:
        sections[current_title] = "\n".join(current_lines).strip()

    return sections


def _extract_quotes(text: str) -> list[str]:
    """从 blockquote 格式提取引用。"""
    quotes = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("> "):
            quotes.append(line[2:].strip())
    return quotes


def _extract_list(text: str) -> list[str]:
    """从 Markdown 列表提取条目。"""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return items


def _render_merged_index(topic: str, sources: list[dict]) -> str:
    """将多个 source 数据合并渲染为 index.md。"""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []

    # Frontmatter
    lines.append("---")
    lines.append(f'title: "{topic}｜研究文档"')
    lines.append(f'created_at: "{now}"')
    lines.append('status: "completed"')
    lines.append("synthesis: true")
    lines.append(f"source_count: {len(sources)}")
    lines.append("tags:")
    lines.append("  - research-index")
    lines.append("  - synthesized")
    lines.append("---")
    lines.append("")

    # 标题
    lines.append(f"# {topic}｜研究文档")
    lines.append("")

    # 一、研究概览
    lines.append("## 一、研究概览")
    lines.append("")
    s_a_count = sum(1 for s in sources if s.get("source_level") in ("S", "A"))
    b_count = sum(1 for s in sources if s.get("source_level") == "B")
    lines.append(
        f"本研究围绕「{topic}」展开，共整合 {len(sources)} 篇已抓取资料。"
        f"其中高质量来源（S/A 级）{s_a_count} 篇，B 级来源 {b_count} 篇。"
    )
    lines.append("")

    # 二、核心摘要（合并所有 source 的 summary）
    lines.append("## 二、各来源摘要")
    lines.append("")
    for src in sources:
        title = src.get("title", src.get("filename", ""))
        url = src.get("url", "")
        summary = src.get("summary", "").strip()
        level = src.get("source_level", "")
        level_badge = f"[{level}] " if level else ""

        if url:
            lines.append(f"### {level_badge}[{title}]({url})")
        else:
            lines.append(f"### {level_badge}{title}")
        lines.append("")
        if summary:
            lines.append(summary)
        else:
            lines.append("（无摘要）")
        lines.append("")

    # 三、关键事实（合并所有 key_points）
    all_key_points: list[tuple[str, str]] = []  # (fact, source_title)
    for src in sources:
        title = src.get("title", "")
        for point in src.get("key_points", []):
            if point.strip():
                all_key_points.append((point.strip(), title))

    if all_key_points:
        lines.append("## 三、关键事实")
        lines.append("")
        for fact, source_title in all_key_points:
            lines.append(f"- {fact} — *来源: {source_title}*")
        lines.append("")

    # 四、时间线（从 key_points 中提取含年份的条目）
    timeline_items: list[tuple[str, str, str]] = []  # (date, fact, source)
    date_pattern = re.compile(r'((?:19|20)\d{2}(?:[-/年]\d{1,2})?)')
    for fact, source_title in all_key_points:
        match = date_pattern.search(fact)
        if match:
            timeline_items.append((match.group(1), fact, source_title))

    if timeline_items:
        timeline_items.sort(key=lambda x: x[0])
        lines.append("## 四、时间线")
        lines.append("")
        lines.append("| 时间 | 事件 | 来源 |")
        lines.append("|---|---|---|")
        for date, fact, source_title in timeline_items:
            fact_clean = fact.replace("|", "\\|")
            lines.append(f"| {date} | {fact_clean} | {source_title} |")
        lines.append("")

    # 五、相关人物
    all_people: set[str] = set()
    for src in sources:
        for p in src.get("people", []):
            if isinstance(p, str) and p.strip():
                all_people.add(p.strip())

    if all_people:
        lines.append("## 五、相关人物")
        lines.append("")
        for person in sorted(all_people):
            lines.append(f"- [[{person}]]")
        lines.append("")

    # 六、重点名词
    all_concepts: set[str] = set()
    for src in sources:
        for c in src.get("concepts", []):
            if isinstance(c, str) and c.strip():
                all_concepts.add(c.strip())

    if all_concepts:
        lines.append("## 六、重点名词")
        lines.append("")
        for concept in sorted(all_concepts):
            lines.append(f"- [[{concept}]]")
        lines.append("")

    # 七、可用于播客的故事点
    all_story_points: list[tuple[str, str]] = []
    for src in sources:
        title = src.get("title", "")
        for sp in src.get("story_points", []):
            if sp.strip():
                all_story_points.append((sp.strip(), title))

    if all_story_points:
        lines.append("## 七、可用于播客的故事点")
        lines.append("")
        for point, source_title in all_story_points:
            lines.append(f"- {point} — *{source_title}*")
        lines.append("")

    # 八、关键引用
    all_quotes: list[tuple[str, str]] = []
    for src in sources:
        title = src.get("title", "")
        for q in src.get("key_quotes", []):
            if q.strip():
                all_quotes.append((q.strip(), title))

    if all_quotes:
        lines.append("## 八、关键引用")
        lines.append("")
        for quote, source_title in all_quotes:
            lines.append(f"> {quote}")
            lines.append(f"> — *{source_title}*")
            lines.append("")

    # 九、资料来源地图
    lines.append("## 九、资料来源地图")
    lines.append("")
    for src in sources:
        title = src.get("title", src.get("filename", ""))
        url = src.get("url", "")
        level = src.get("source_level", "")
        filename = src.get("filename", "")
        level_badge = f"[{level}] " if level else ""

        if url:
            lines.append(f"- {level_badge}**[{title}]({url})** → `sources/{filename}`")
        else:
            lines.append(f"- {level_badge}**{title}** → `sources/{filename}`")
    lines.append("")

    # 十、下一步
    lines.append("## 十、下一步深挖方向")
    lines.append("")
    lines.append("- 交叉验证关键事实")
    lines.append("- 补充缺失时间段的资料")
    if len(sources) < 5:
        lines.append("- 抓取更多来源正文以提高覆盖度")
    lines.append("")

    return "\n".join(lines)
