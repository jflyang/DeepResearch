"""内容归一化服务 - 将已抓取正文清洗、结构化为标准化事实条目。

职责：
- 只处理已成功抓取的正文（有 content 的 ExtractedDocument）
- 通过 LLM 将非结构化正文转化为结构化事实条目（NormalizedFact）
- 每条事实必须追溯 source_id / document_id / url
- LLM 不得编造来源中没有的信息
- LLM 失败时 fallback 到规则提取，不阻断流程
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)


# === 数据模型 ===


class NormalizedFact(BaseModel):
    """归一化后的单条事实。"""

    fact_id: str = ""
    claim: str = ""  # 事实陈述
    category: str = "general"  # person_bio / event / concept / opinion / timeline / quote
    confidence: str = "medium"  # high / medium / low / unverified
    source_id: str = ""  # SourceItem.id
    document_id: str = ""  # ExtractedDocument.id
    source_url: str = ""
    source_title: str = ""
    original_text: str = ""  # 原文片段（用于溯源）
    entities: list[str] = Field(default_factory=list)
    date_hint: str = ""  # 时间线提示 (YYYY 或 YYYY-MM-DD)
    is_quote: bool = False  # 是否为直接引用


class NormalizationResult(BaseModel):
    """单篇文档归一化结果。"""

    document_id: str = ""
    source_id: str = ""
    facts: list[NormalizedFact] = Field(default_factory=list)
    skipped_reason: str = ""  # 如果跳过，说明原因


class ContentNormalizationLLMOutput(BaseModel):
    """LLM 输出 schema - 从正文提取结构化事实。"""

    facts: list[LLMExtractedFact] = Field(default_factory=list)


class LLMExtractedFact(BaseModel):
    """LLM 提取的单条事实（不含 source 元数据，由服务层补充）。"""

    claim: str = ""
    category: str = "general"
    confidence: str = "medium"
    original_text: str = ""
    entities: list[str] = Field(default_factory=list)
    date_hint: str = ""
    is_quote: bool = False


# Fix forward reference
ContentNormalizationLLMOutput.model_rebuild()


# === 服务 ===


class ContentNormalizationService:
    """将已抓取正文归一化为结构化事实条目。"""

    # 最小正文长度（太短的正文没有归一化价值）
    MIN_CONTENT_LENGTH = 100

    def __init__(self, ai_gateway: AIGateway | None = None) -> None:
        self._ai_gateway = ai_gateway

    async def normalize_document(
        self,
        document_id: str,
        source_id: str,
        source_url: str,
        source_title: str,
        content: str,
        topic: str = "",
    ) -> NormalizationResult:
        """归一化单篇已抓取文档。

        Args:
            document_id: ExtractedDocument.id
            source_id: SourceItem.id
            source_url: 来源 URL
            source_title: 来源标题
            content: 已抓取的正文
            topic: 研究主题（帮助 LLM 聚焦）

        Returns:
            NormalizationResult，包含提取的事实列表
        """
        # 前置检查：正文必须存在且有足够长度
        if not content or len(content.strip()) < self.MIN_CONTENT_LENGTH:
            return NormalizationResult(
                document_id=document_id,
                source_id=source_id,
                skipped_reason=f"正文过短或为空 (len={len(content.strip()) if content else 0})",
            )

        # 尝试 LLM 归一化
        facts = await self._try_llm_normalize(content, topic)

        # LLM 失败时 fallback 到规则提取
        if facts is None:
            logger.info(
                "llm_normalization_fallback document_id=%s using rule-based extraction",
                document_id,
            )
            facts = self._rule_based_normalize(content, topic)

        # 补充 source 元数据
        enriched_facts: list[NormalizedFact] = []
        for i, fact in enumerate(facts):
            fact_id = self._generate_fact_id(document_id, i, fact.claim)
            enriched_facts.append(
                NormalizedFact(
                    fact_id=fact_id,
                    claim=fact.claim,
                    category=fact.category,
                    confidence=fact.confidence,
                    source_id=source_id,
                    document_id=document_id,
                    source_url=source_url,
                    source_title=source_title,
                    original_text=fact.original_text,
                    entities=fact.entities,
                    date_hint=fact.date_hint,
                    is_quote=fact.is_quote,
                )
            )

        logger.info(
            "content_normalized document_id=%s facts_count=%d",
            document_id,
            len(enriched_facts),
        )

        return NormalizationResult(
            document_id=document_id,
            source_id=source_id,
            facts=enriched_facts,
        )

    async def normalize_batch(
        self,
        documents: list[dict],
        topic: str = "",
    ) -> list[NormalizationResult]:
        """批量归一化多篇文档。

        Args:
            documents: 文档列表，每项需包含:
                - document_id, source_id, source_url, source_title, content
            topic: 研究主题

        Returns:
            NormalizationResult 列表
        """
        results: list[NormalizationResult] = []
        for doc in documents:
            result = await self.normalize_document(
                document_id=doc.get("document_id", ""),
                source_id=doc.get("source_id", ""),
                source_url=doc.get("source_url", ""),
                source_title=doc.get("source_title", ""),
                content=doc.get("content", ""),
                topic=topic,
            )
            results.append(result)
        return results

    # === LLM 归一化 ===

    async def _try_llm_normalize(
        self, content: str, topic: str
    ) -> list[LLMExtractedFact] | None:
        """尝试 LLM 归一化，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        try:
            result = await self._ai_gateway.run_json(
                task_name="content_normalization",
                payload={
                    "topic": topic,
                    "content": content,
                },
                output_schema=ContentNormalizationLLMOutput,
                language="zh",
            )
            return result.facts
        except Exception as e:
            logger.warning("llm_content_normalization_failed error=%s", str(e))
            return None

    # === 规则 Fallback ===

    def _rule_based_normalize(self, content: str, topic: str) -> list[LLMExtractedFact]:
        """规则提取：按段落切分，提取含实体或数字的句子作为事实。"""
        facts: list[LLMExtractedFact] = []
        sentences = self._split_sentences(content)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
            # 只保留含有数字、日期、专有名词的句子
            if not self._has_factual_signal(sentence):
                continue

            category = self._guess_category(sentence)
            date_hint = self._extract_date_hint(sentence)
            is_quote = self._is_likely_quote(sentence)

            facts.append(
                LLMExtractedFact(
                    claim=sentence[:500],
                    category=category,
                    confidence="low",  # 规则提取置信度低
                    original_text=sentence[:300],
                    entities=self._extract_simple_entities(sentence),
                    date_hint=date_hint,
                    is_quote=is_quote,
                )
            )

            # 规则提取限制数量
            if len(facts) >= 30:
                break

        return facts

    # === 工具方法 ===

    @staticmethod
    def _generate_fact_id(document_id: str, index: int, claim: str) -> str:
        """生成事实 ID。"""
        raw = f"{document_id}:{index}:{claim[:50]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """中英文混合分句。"""
        # 按中文句号、英文句号+空格、换行分割
        parts = re.split(r'(?<=[。！？.!?])\s*|\n+', text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _has_factual_signal(sentence: str) -> bool:
        """判断句子是否含有事实信号（数字、日期、专有名词等）。"""
        # 含数字
        if re.search(r'\d{2,}', sentence):
            return True
        # 含年份
        if re.search(r'(19|20)\d{2}', sentence):
            return True
        # 含引号（可能是引用）
        if re.search(r'[""「」『』]', sentence):
            return True
        # 含大写英文词（可能是专有名词）
        if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', sentence):
            return True
        # 含百分比
        if re.search(r'\d+%', sentence):
            return True
        return False

    @staticmethod
    def _guess_category(sentence: str) -> str:
        """根据内容猜测事实类别。"""
        if re.search(r'(19|20)\d{2}年?.*[，,]', sentence):
            return "timeline"
        if re.search(r'[""「」『』].*[""」』]', sentence):
            return "quote"
        if re.search(r'认为|表示|指出|声称|据.*报道', sentence):
            return "opinion"
        return "general"

    @staticmethod
    def _extract_date_hint(sentence: str) -> str:
        """提取日期提示。"""
        match = re.search(r'((?:19|20)\d{2})(?:[-/年](\d{1,2}))?', sentence)
        if match:
            year = match.group(1)
            month = match.group(2)
            if month:
                return f"{year}-{month.zfill(2)}"
            return year
        return ""

    @staticmethod
    def _is_likely_quote(sentence: str) -> bool:
        """判断是否为直接引用。"""
        return bool(re.search(r'^[""「]|[""」]$', sentence.strip()))

    @staticmethod
    def _extract_simple_entities(sentence: str) -> list[str]:
        """简单实体提取（大写英文词组）。"""
        entities = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', sentence)
        return entities[:5]
