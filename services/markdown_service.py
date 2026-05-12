"""Markdown 导出服务 - 将提取内容导出为 Obsidian 兼容 Markdown。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import get_settings
from core.errors import ResearchError
from models.enums import DownloadStatus, SourceLevel
from models.schemas import ExtractedDocument, ResearchTask, SourceItem
from utils.filesystem import ensure_dir, ensure_unique_path, sanitize_filename, write_file

if TYPE_CHECKING:
    from app.ai.schemas import FinalIndexSynthesisOutput
    from services.book_relevance_service import BookRelevanceResult

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
    synthesis: "FinalIndexSynthesisOutput | None" = None,
    book_reviews: dict[str, "BookRelevanceResult"] | None = None,
    filtered_books: list[str] | None = None,
) -> Path:
    """
    生成研究索引页。

    Args:
        task: 研究任务
        sources: 所有来源（已评分排序）
        extracted_docs: source_item_id → ExtractedDocument 映射
        vault_path: 可选覆盖 vault 路径
        synthesis: LLM 生成的综合分析结果
        book_reviews: 图书相关性审核结果 {source_id: BookRelevanceResult}
        filtered_books: 被过滤的图书标题列表

    Returns:
        index.md 文件路径
    """
    vault = vault_path or _get_vault_path()
    research_dir = _research_dir(vault, task.topic)
    index_path = research_dir / "index.md"

    # 判断是否有正文提取
    content_extracted = bool(extracted_docs)

    # 分类来源
    must_read = []
    books = []
    interviews = []
    gossip = []
    all_people: list[dict] = []
    all_places: list[dict] = []
    all_concepts: set[str] = set()

    for item in sources:
        entry = {
            "filename": sanitize_filename(item.title),
            "title": item.title,
            "level": item.source_level.value,
            "reason": item.reason_to_read,
            "author": "",
            "title_zh": "",
            "book_type": "",
            "relevance_level": "",
            "why_relevant": "",
            "likely_contains": [],
            "extraction_status": "仅搜索摘要，尚未抓取正文",
        }

        # 从 extracted 获取额外信息
        doc = extracted_docs.get(item.id)
        if doc:
            entry["author"] = doc.author
            entry["extraction_status"] = "已提取正文"
            for person in doc.people:
                if person and not any(p["name"] == person for p in all_people):
                    all_people.append({"name": person, "role": "待确认"})
            all_concepts.update(doc.concepts)

        # 从 book_reviews 获取图书详情
        if book_reviews and item.id in book_reviews:
            review = book_reviews[item.id]
            entry["title_zh"] = review.book_title_zh
            entry["book_type"] = review.book_type
            entry["relevance_level"] = review.relevance_level
            entry["why_relevant"] = review.why_relevant
            entry["likely_contains"] = review.likely_contains

        if item.source_level in (SourceLevel.S, SourceLevel.A):
            must_read.append(entry)

        if item.source_type.value == "book":
            # 只有通过相关性过滤的图书才进入图书资料
            if book_reviews and item.id in book_reviews:
                review = book_reviews[item.id]
                if review.is_relevant:
                    books.append(entry)
            else:
                # 没有 review 信息时默认包含
                books.append(entry)

        text_lower = f"{item.title} {item.snippet}".lower()
        if any(kw in text_lower for kw in ("interview", "q&a", "speech", "talk")):
            interviews.append(entry)

        if item.gossip_score >= 0.3:
            gossip.append(entry)

    # 从 synthesis 获取丰富信息
    overview = ""
    topic_fit_warning: list[str] = []
    story_points: list[dict] = []
    timeline_events: list[dict] = []
    verification_warnings: list[dict] = []
    filtered_noise_summary: list[str] = filtered_books or []
    next_steps: list[str] = []

    if synthesis:
        overview = synthesis.overview or ""
        topic_fit_warning = synthesis.topic_fit_warning or []
        next_steps = synthesis.suggested_next_steps or []
        filtered_noise_summary = synthesis.filtered_noise_summary or filtered_noise_summary

        # 从 synthesis 补充人物
        for person in synthesis.key_people:
            if person.name and not any(p["name"] == person.name for p in all_people):
                all_people.append({"name": person.name, "role": person.role})

        # 从 synthesis 补充地点
        all_places = [{"name": p.name, "significance": p.significance} for p in synthesis.key_places]

        # 从 synthesis 补充概念
        all_concepts.update(synthesis.key_concepts)

        # 故事点
        story_points = [
            {"point": sp.point, "source": sp.source, "verified": sp.verified}
            for sp in synthesis.story_points
        ]

        # 时间线
        timeline_events = [
            {"date": te.date, "event": te.event, "source": te.source}
            for te in synthesis.timeline_events
        ]

        # 待核验
        verification_warnings = [
            {"claim": vw.claim, "source": vw.source, "risk": vw.risk}
            for vw in synthesis.verification_warnings
        ]

        # 从 synthesis 补充图书信息
        if synthesis.book_sources:
            for syn_book in synthesis.book_sources:
                # 尝试匹配已有图书
                matched = False
                for book_entry in books:
                    if syn_book.title and syn_book.title.lower() in book_entry["title"].lower():
                        # 补充 synthesis 提供的信息
                        if syn_book.title_zh and not book_entry["title_zh"]:
                            book_entry["title_zh"] = syn_book.title_zh
                        if syn_book.author and not book_entry["author"]:
                            book_entry["author"] = syn_book.author
                        if syn_book.book_type and not book_entry["book_type"]:
                            book_entry["book_type"] = syn_book.book_type
                        if syn_book.why_read and not book_entry["why_relevant"]:
                            book_entry["why_relevant"] = syn_book.why_read
                        if syn_book.likely_contains and not book_entry["likely_contains"]:
                            book_entry["likely_contains"] = syn_book.likely_contains
                        if syn_book.relevance and not book_entry["relevance_level"]:
                            book_entry["relevance_level"] = syn_book.relevance
                        matched = True
                        break

    # 如果没有 synthesis overview，生成规则 fallback
    if not overview:
        total = len(sources)
        high_quality = len([s for s in sources if s.source_level.value in ("S", "A")])
        book_count = len(books)
        overview = (
            f"本次研究围绕「{task.topic}」展开（模式：{task.mode.value}），"
            f"共收集 {total} 条来源。其中高质量来源（S/A 级）{high_quality} 条，"
            f"图书资料 {book_count} 条。"
        )
        if not content_extracted:
            overview += "\n\n⚠️ 当前所有来源尚未提取正文，以下分析仅基于搜索摘要，可信度有限。"
        overview += "\n\n建议优先阅读 S/A 级来源，提取正文后进行深度分析。"

    if not next_steps:
        next_steps = ["提取已保存来源的正文", "交叉验证关键事实", "扩展搜索更多一手资料"]

    # 渲染
    env = _get_jinja_env()
    template = env.get_template("research_index.md.j2")

    content = template.render(
        topic=task.topic,
        created_at=task.created_at.strftime("%Y-%m-%d %H:%M"),
        status=task.status.value,
        total_sources=len(sources),
        high_quality_count=len(must_read),
        book_count=len(books),
        content_extracted=content_extracted,
        overview=overview,
        topic_fit_warning=topic_fit_warning,
        must_read=must_read,
        books=books,
        interviews=interviews,
        gossip=gossip,
        concepts=sorted(all_concepts),
        people=all_people,
        places=all_places,
        story_points=story_points,
        timeline_events=timeline_events,
        verification_warnings=verification_warnings,
        filtered_noise_summary=filtered_noise_summary,
        next_steps=next_steps,
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
    book_reviews: dict[str, "BookRelevanceResult"] | None = None,
    extracted_docs: dict[str, ExtractedDocument] | None = None,
) -> "FinalIndexSynthesisOutput":
    """
    使用 LLM 生成结构化研究综合分析。失败时返回规则生成的结果。

    Returns:
        FinalIndexSynthesisOutput 结构化对象
    """
    from app.ai.schemas import FinalIndexSynthesisOutput

    if not ai_gateway:
        return _rule_based_index_synthesis(topic, mode, sources, extracted_docs)

    top_sources = [
        {
            "title": s.title[:80],
            "level": s.source_level.value,
            "type": s.source_type.value,
            "reason": s.reason_to_read,
        }
        for s in sources
        if s.source_level.value in ("S", "A")
    ][:10]

    high_quality_count = len([s for s in sources if s.source_level.value in ("S", "A")])
    book_sources_list = []

    # 构建图书来源信息
    for s in sources:
        if s.source_type.value == "book":
            book_info = {
                "title": s.title[:80],
                "author": "",
                "book_type": "",
                "relevance_level": "medium",
            }
            if book_reviews and s.id in book_reviews:
                review = book_reviews[s.id]
                book_info["author"] = ""  # 从 review 无法获取 author
                book_info["book_type"] = review.book_type
                book_info["relevance_level"] = review.relevance_level
            if extracted_docs and s.id in extracted_docs:
                book_info["author"] = extracted_docs[s.id].author
            book_sources_list.append(book_info)

    # 构建实体信息
    entities = []
    if extracted_docs:
        seen_entities: set[str] = set()
        for doc in extracted_docs.values():
            for person in doc.people:
                if person and person not in seen_entities:
                    entities.append({"name": person, "type": "person", "description": ""})
                    seen_entities.add(person)

    try:
        result: FinalIndexSynthesisOutput = await ai_gateway.run_json(
            task_name="final_index_synthesis",
            payload={
                "topic": topic,
                "mode": mode,
                "total_sources": len(sources),
                "high_quality_count": high_quality_count,
                "book_count": len(book_sources_list),
                "top_sources": top_sources,
                "book_sources": book_sources_list,
                "entities": entities,
            },
            output_schema=FinalIndexSynthesisOutput,
            language="zh",
        )
        return result
    except Exception as e:
        logger.warning("final_index_synthesis_failed topic=%s error=%s", topic[:50], str(e)[:100])
        return _rule_based_index_synthesis(topic, mode, sources, extracted_docs)


def _rule_based_index_synthesis(topic: str, mode: str, sources: list[SourceItem], extracted_docs: dict[str, ExtractedDocument] | None = None) -> "FinalIndexSynthesisOutput":
    """规则生成的研究综合分析（fallback）。"""
    from app.ai.schemas import (
        FinalIndexSynthesisOutput,
        SynthesisKeyPerson,
        SynthesisKeyPlace,
        SynthesisTimelineEvent,
    )

    total = len(sources)
    high_quality = len([s for s in sources if s.source_level.value in ("S", "A")])
    books = len([s for s in sources if s.source_type.value == "book"])

    overview = (
        f"本次研究围绕「{topic}」展开（模式：{mode}），共收集 {total} 条来源。"
        f"其中高质量来源（S/A 级）{high_quality} 条，图书资料 {books} 条。"
    )

    if extracted_docs:
        overview += f"\n\n已抓取并分析 {len(extracted_docs)} 篇正文。以下信息基于正文分析。"
    else:
        overview += f"\n\n建议优先阅读 S/A 级来源，提取正文后进行深度分析。"

    # 从来源标题和 extracted docs 推断关键人物
    key_people: list[SynthesisKeyPerson] = []
    key_places: list[SynthesisKeyPlace] = []
    key_concepts: list[str] = []

    # 简单规则：如果 mode 是 person，主题本身就是关键人物
    if mode == "person":
        entity_name = topic.split("童年")[0].split("的")[0].strip() if "童年" in topic or "的" in topic else topic
        key_people.append(SynthesisKeyPerson(
            name=entity_name,
            role="研究主体",
            importance="high",
        ))

    # 从 extracted docs 收集人物、地点、概念
    if extracted_docs:
        seen_people: set[str] = set()
        seen_places: set[str] = set()
        for doc in extracted_docs.values():
            for person in doc.people:
                if person and person not in seen_people:
                    seen_people.add(person)
                    if not any(p.name == person for p in key_people):
                        key_people.append(SynthesisKeyPerson(
                            name=person, role="相关人物", importance="medium",
                        ))
            for place in doc.places:
                if place and place not in seen_places:
                    seen_places.add(place)
                    key_places.append(SynthesisKeyPlace(name=place, significance="出现在正文中"))
            key_concepts.extend(c for c in doc.concepts if c not in key_concepts)

    return FinalIndexSynthesisOutput(
        overview=overview,
        key_people=key_people[:10],
        key_places=key_places[:10],
        key_concepts=key_concepts[:15],
        suggested_next_steps=["提取已保存来源的正文", "交叉验证关键事实", "扩展搜索更多一手资料"],
    )
