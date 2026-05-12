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

    content = template.render(
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
        summary=summary,
        reason_to_read=source_item.reason_to_read,
        key_quotes=extracted.key_quotes,
        people_list=extracted.people,
        places_list=extracted.places,
        concepts=extracted.concepts,
        story_points=story_points,
        content=extracted.content,
    )

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
