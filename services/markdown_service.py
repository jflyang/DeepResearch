"""Markdown 导出服务 - 将提取内容导出为 Obsidian 兼容 Markdown。"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import get_settings
from core.errors import ResearchError
from models.enums import DownloadStatus, SourceLevel
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from utils.filesystem import ensure_dir, ensure_unique_path, sanitize_filename, write_file

logger = logging.getLogger(__name__)

# Jinja2 环境
_TEMPLATE_DIR = Path("templates")


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("md.j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _get_vault_path() -> Path:
    """获取 Obsidian vault 路径，未配置时抛出明确错误。"""
    settings = get_settings()
    if not settings.obsidian_configured:
        raise ResearchError(
            message="Obsidian vault path not configured. Set OBSIDIAN_VAULT_PATH in .env",
            step="markdown_export",
            details="Cannot export without a configured vault path.",
        )
    return settings.obsidian_path


def _research_dir(vault: Path, topic: str) -> Path:
    """获取研究目录路径。"""
    safe_topic = sanitize_filename(topic, max_length=80)
    return vault / "Research" / safe_topic


# === 单篇资料导出 ===


def export_source_note(
    source_item: SourceItem,
    extracted: ExtractedDocument,
    topic: str,
    vault_path: Path | None = None,
) -> Path:
    """
    导出单篇资料为 Obsidian Markdown。

    Args:
        source_item: 来源记录
        extracted: 提取的正文
        topic: 研究主题
        vault_path: 可选覆盖 vault 路径（测试用）

    Returns:
        写入的文件路径

    Raises:
        ResearchError: vault 路径未配置
    """
    vault = vault_path or _get_vault_path()
    research_dir = _research_dir(vault, topic)
    sources_dir = ensure_dir(research_dir / "sources")

    # 生成安全文件名
    filename = sanitize_filename(extracted.title or source_item.title) + ".md"
    file_path = ensure_unique_path(sources_dir / filename)

    # 渲染模板
    env = _get_jinja_env()
    template = env.get_template("source_note.md.j2")

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    # MVP: 简单摘要 = 正文前 200 字符
    summary = extracted.content[:200] + "..." if len(extracted.content) > 200 else extracted.content

    # MVP: 故事点为空
    story_points = ""

    # 判断是否启用双语模式
    source_lang = (
        source_item.source_language.value if source_item.source_language else None
    )
    output_lang = (
        extracted.summary_language.value if extracted.summary_language else None
    )
    bilingual_mode = (source_lang == "en" and output_lang == "zh")

    # 构建模板变量
    render_vars = dict(
        title=extracted.title or source_item.title,
        url=source_item.url,
        source_provider=source_item.domain,
        author=extracted.author,
        published_at=extracted.publish_date if hasattr(extracted, "publish_date") else "",
        accessed_at=now,
        source_level=source_item.source_level.value,
        source_type=source_item.source_type.value,
        topic=topic,
        people=extracted.people,
        places=extracted.places,
        status="extracted",
        summary=extracted.summary or summary,
        reason_to_read=source_item.reason_to_read,
        key_quotes=extracted.key_quotes,
        people_list=extracted.people,
        places_list=extracted.places,
        concepts=extracted.concepts,
        story_points=story_points,
        content=extracted.content,
        bilingual_mode=bilingual_mode,
    )

    # 语言元数据（仅在有值时传入）
    if source_item.original_topic:
        render_vars["original_topic"] = source_item.original_topic
    if source_item.canonical_topic:
        render_vars["canonical_topic"] = source_item.canonical_topic
    if source_item.query_language:
        render_vars["query_language"] = source_item.query_language.value
    if source_item.source_language:
        render_vars["source_language"] = source_item.source_language.value
    if source_item.matched_query:
        render_vars["matched_query"] = source_item.matched_query

    if extracted.summary_language:
        render_vars["output_language"] = extracted.summary_language.value
    if extracted.original_language:
        render_vars["user_language"] = ""  # 由调用方设置
    if source_item.source_language:
        render_vars["working_language"] = source_item.source_language.value

    content = template.render(**render_vars)

    write_file(file_path, content)

    # 更新 markdown_path
    extracted.markdown_path = str(file_path)
    source_item.download_status = DownloadStatus.EXPORTED

    logger.info(
        "markdown_exported source_id=%s path=%s",
        source_item.id,
        file_path,
    )

    return file_path


# === 研究索引页导出 ===


def export_research_index(
    task: ResearchTask,
    sources: list[SourceItem],
    extracted_docs: dict[str, ExtractedDocument],
    vault_path: Path | None = None,
) -> Path:
    """
    生成研究索引页。

    Args:
        task: 研究任务
        sources: 所有来源（已评分排序）
        extracted_docs: source_item_id → ExtractedDocument 映射
        vault_path: 可选覆盖 vault 路径

    Returns:
        index.md 文件路径
    """
    vault = vault_path or _get_vault_path()
    research_dir = _research_dir(vault, task.topic)
    index_path = research_dir / "index.md"

    # 分类来源
    must_read = []
    books = []
    interviews = []
    gossip = []
    all_people: set[str] = set()
    all_concepts: set[str] = set()

    for item in sources:
        entry = {
            "filename": sanitize_filename(item.title),
            "title": item.title,
            "level": item.source_level.value,
            "reason": item.reason_to_read,
            "author": "",
        }

        # 从 extracted 获取额外信息
        doc = extracted_docs.get(item.id)
        if doc:
            entry["author"] = doc.author
            all_people.update(doc.people)
            all_concepts.update(doc.concepts)

        if item.source_level in (SourceLevel.S, SourceLevel.A):
            must_read.append(entry)

        if item.source_type.value == "book":
            books.append(entry)

        text_lower = f"{item.title} {item.snippet}".lower()
        if any(kw in text_lower for kw in ("interview", "q&a", "speech", "talk")):
            interviews.append(entry)

        if item.gossip_score >= 0.3:
            gossip.append(entry)

    # 渲染
    env = _get_jinja_env()
    template = env.get_template("research_index.md.j2")

    content = template.render(
        topic=task.topic,
        created_at=task.created_at.strftime("%Y-%m-%d %H:%M"),
        status=task.status.value,
        total_sources=len(sources),
        research_goal=f"深度研究「{task.topic}」，模式：{task.mode.value}",
        must_read=must_read,
        books=books,
        interviews=interviews,
        gossip=gossip,
        concepts=sorted(all_concepts),
        people=sorted(all_people),
        timeline="（待补充）",
        unverified=["（暂无待核验信息）"],
        next_steps=["扩展搜索更多一手资料", "下载并提取剩余来源", "交叉验证关键事实"],
    )

    write_file(index_path, content)

    logger.info("research_index_exported task_id=%s path=%s", task.id, index_path)
    return index_path


# === 外部报告导入导出 ===


def export_imported_report(
    task: ResearchTask,
    report_text: str,
    report_source: str,
    parsed_summary: dict | None = None,
    vault_path: Path | None = None,
) -> Path:
    """
    导出外部研究报告原文为 Obsidian Markdown。

    Args:
        task: 研究任务
        report_text: 报告原文
        report_source: 报告来源（ChatGPT / Perplexity 等）
        parsed_summary: 解析摘要（url_count, book_count, paper_count 等）
        vault_path: 可选覆盖 vault 路径

    Returns:
        imported_report.md 文件路径
    """
    vault = vault_path or _get_vault_path()
    research_dir = _research_dir(vault, task.topic)
    ensure_dir(research_dir)
    report_path = research_dir / "imported_report.md"

    # 构建 frontmatter
    frontmatter = (
        "---\n"
        f'title: "{task.topic}｜外部研究报告"\n'
        f'source: "{report_source}"\n'
        f'task_id: "{task.id}"\n'
        "type: imported_report\n"
        "---\n\n"
    )

    # 构建引用摘要
    refs_section = ""
    if parsed_summary:
        urls = parsed_summary.get("urls", [])
        books = parsed_summary.get("books", [])
        papers = parsed_summary.get("papers", [])

        refs_section = "\n# 解析出的引用\n\n"
        refs_section += "## URLs\n\n"
        if urls:
            for u in urls:
                title = u.get("title_hint") or u.get("url", "")
                url = u.get("url", "")
                refs_section += f"- [{title}]({url})\n"
        else:
            refs_section += "（无）\n"

        refs_section += "\n## Books\n\n"
        if books:
            for b in books:
                refs_section += f"- 《{b.get('title', '')}》"
                if b.get("author_hint"):
                    refs_section += f" — {b['author_hint']}"
                refs_section += "\n"
        else:
            refs_section += "（无）\n"

        refs_section += "\n## Papers\n\n"
        if papers:
            for p in papers:
                refs_section += f"- {p.get('title', '')}"
                if p.get("doi_hint"):
                    refs_section += f" (DOI: {p['doi_hint']})"
                if p.get("arxiv_id"):
                    refs_section += f" (arXiv: {p['arxiv_id']})"
                refs_section += "\n"
        else:
            refs_section += "（无）\n"

    content = f"{frontmatter}# 外部研究报告\n\n{report_text}\n{refs_section}"

    write_file(report_path, content)
    logger.info("imported_report_exported task_id=%s path=%s", task.id, report_path)
    return report_path


def export_report_ingestion_index(
    task: ResearchTask,
    sources: list[SourceItem],
    report_source: str,
    parsed_url_count: int = 0,
    parsed_book_count: int = 0,
    parsed_paper_count: int = 0,
    vault_path: Path | None = None,
) -> Path:
    """
    生成报告导入任务的研究索引页。

    在普通 index 基础上增加外部报告来源信息和按 source_origin 分类。
    """
    vault = vault_path or _get_vault_path()
    research_dir = _research_dir(vault, task.topic)
    ensure_dir(research_dir)
    index_path = research_dir / "index.md"

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    # 按 source_origin 分类
    direct_links = [s for s in sources if getattr(s, "source_origin", "") == "imported_report"]
    enriched = [s for s in sources if getattr(s, "source_origin", "") == "imported_report_enriched"]
    failed = [s for s in sources if s.download_status == DownloadStatus.FAILED]

    lines = [
        "---",
        f"title: {task.topic}｜研究索引",
        f"task_id: {task.id}",
        "type: research_index",
        f"created: {now}",
        "---",
        "",
        f"# {task.topic}",
        "",
        "## 外部报告来源",
        "",
        f"- 报告来源：{report_source}",
        f"- 解析 URL 数量：{parsed_url_count}",
        f"- 解析书籍数量：{parsed_book_count}",
        f"- 解析论文数量：{parsed_paper_count}",
        f"- 总来源数：{len(sources)}",
        "",
        "## 报告中直接链接",
        "",
    ]

    if direct_links:
        for item in direct_links:
            lines.append(f"- [{item.title}]({item.url})")
    else:
        lines.append("（无）")

    lines.extend(["", "## 补充检索来源", ""])
    if enriched:
        for item in enriched:
            lines.append(f"- [{item.title}]({item.url})")
    else:
        lines.append("（无）")

    if failed:
        lines.extend(["", "## 提取失败 / 需手动处理", ""])
        for item in failed:
            lines.append(f"- [{item.title}]({item.url})")

    lines.extend([
        "",
        "## 下一步建议",
        "",
        "- 提取已保存来源的正文",
        "- 手动处理失败的来源",
        "- 交叉验证关键事实",
        "",
    ])

    content = "\n".join(lines)
    write_file(index_path, content)
    logger.info("report_ingestion_index_exported task_id=%s path=%s", task.id, index_path)
    return index_path


# === LLM 增强导出功能 ===


async def generate_markdown_summary(
    title: str,
    content: str,
    topic: str,
    level: str = "B",
    ai_gateway=None,
) -> str:
    """使用 LLM 生成来源摘要。失败时返回简单截取摘要。"""
    if not ai_gateway:
        return content[:200] + "..." if len(content) > 200 else content

    try:
        result = await ai_gateway.run_text(
            task_name="markdown_summary_generation",
            payload={
                "topic": topic,
                "title": title,
                "level": level,
                "content": content[:8000],
            },
            language="zh",
        )
        return result.strip() if result else content[:200]
    except Exception as e:
        logger.warning("markdown_summary_generation_failed title=%s error=%s", title[:50], str(e)[:100])
        return content[:200] + "..." if len(content) > 200 else content


async def generate_index_synthesis(
    topic: str,
    mode: str,
    sources: list[SourceItem],
    ai_gateway=None,
) -> str:
    """使用 LLM 生成研究概览。失败时返回规则生成的概览。"""
    if not ai_gateway:
        return _rule_based_index_synthesis(topic, mode, sources)

    top_sources = [
        {
            "title": s.title[:80],
            "level": s.source_level.value,
            "reason": s.reason_to_read,
        }
        for s in sources
        if s.source_level.value in ("S", "A")
    ][:10]

    high_quality_count = len([s for s in sources if s.source_level.value in ("S", "A")])

    try:
        result = await ai_gateway.run_text(
            task_name="final_index_synthesis",
            payload={
                "topic": topic,
                "mode": mode,
                "total_sources": len(sources),
                "high_quality_count": high_quality_count,
                "top_sources": top_sources,
            },
            language="zh",
        )
        return result.strip() if result else _rule_based_index_synthesis(topic, mode, sources)
    except Exception as e:
        logger.warning("final_index_synthesis_failed topic=%s error=%s", topic[:50], str(e)[:100])
        return _rule_based_index_synthesis(topic, mode, sources)


def _rule_based_index_synthesis(topic: str, mode: str, sources: list[SourceItem]) -> str:
    """规则生成的研究概览（fallback）。"""
    total = len(sources)
    high_quality = len([s for s in sources if s.source_level.value in ("S", "A")])
    books = len([s for s in sources if s.source_type.value == "book"])

    return f"""## 研究概览

本次研究围绕「{topic}」展开（模式：{mode}），共收集 {total} 条来源。
其中高质量来源（S/A 级）{high_quality} 条，图书资料 {books} 条。

建议优先阅读 S/A 级来源，提取正文后进行深度分析。
"""
