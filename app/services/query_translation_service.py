"""搜索关键词翻译服务 - 搜索前将中文关键词翻译为英文。

职责：
- 在 crawlers/search 执行搜索之前，将中文查询翻译为英文
- 默认行为：所有中文查询翻译为英文后搜索
- 用户明确勾选"使用中文搜索"时，保留中文原文
- LLM 可用时使用 LLM 翻译（更准确）
- LLM 不可用时使用规则 fallback（实体映射表 + 简单转写）
- 不修改原始查询对象，返回新的翻译后查询列表
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# CJK 字符检测
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


# === 数据模型 ===


class TranslatedQuery(BaseModel):
    """翻译后的查询。"""

    original: str
    translated: str
    language: str = "en"  # 翻译目标语言
    method: str = "rule"  # rule / llm / passthrough
    confidence: float = 0.5


class QueryTranslationResult(BaseModel):
    """批量翻译结果。"""

    queries: list[TranslatedQuery] = Field(default_factory=list)
    translated_count: int = 0
    passthrough_count: int = 0
    used_llm: bool = False


class QueryTranslationLLMOutput(BaseModel):
    """LLM 翻译输出。"""

    translations: list[LLMTranslationItem] = Field(default_factory=list)


class LLMTranslationItem(BaseModel):
    """LLM 单条翻译。"""

    original: str = ""
    translated: str = ""
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


# Fix forward reference
QueryTranslationLLMOutput.model_rebuild()


# === 已知实体翻译表 ===

_ENTITY_TRANSLATIONS: dict[str, str] = {
    # 人物
    "库克": "Tim Cook",
    "蒂姆库克": "Tim Cook",
    "蒂姆·库克": "Tim Cook",
    "黄仁勋": "Jensen Huang",
    "奥特曼": "Sam Altman",
    "山姆奥特曼": "Sam Altman",
    "山姆·奥特曼": "Sam Altman",
    "马斯克": "Elon Musk",
    "埃隆马斯克": "Elon Musk",
    "贝索斯": "Jeff Bezos",
    "贝佐斯": "Jeff Bezos",
    "扎克伯格": "Mark Zuckerberg",
    "纳德拉": "Satya Nadella",
    "乔布斯": "Steve Jobs",
    "比尔盖茨": "Bill Gates",
    "比尔·盖茨": "Bill Gates",
    # 公司
    "苹果": "Apple",
    "英伟达": "NVIDIA",
    "特斯拉": "Tesla",
    "亚马逊": "Amazon",
    "谷歌": "Google",
    "微软": "Microsoft",
    "脸书": "Meta",
    # 常见研究关键词
    "童年": "childhood",
    "早期": "early life",
    "创业": "founding story",
    "传记": "biography",
    "采访": "interview",
    "演讲": "speech",
    "争议": "controversy",
    "丑闻": "scandal",
    "收购": "acquisition",
    "融资": "funding",
    "上市": "IPO",
    "破产": "bankruptcy",
    "诉讼": "lawsuit",
    "辞职": "resignation",
    "发展史": "history",
    "商业模式": "business model",
    "管理风格": "management style",
    "企业文化": "corporate culture",
    "产品": "product",
    "技术": "technology",
    "人工智能": "artificial intelligence",
    "机器学习": "machine learning",
    "深度学习": "deep learning",
    "大模型": "large language model",
    "芯片": "chip",
    "半导体": "semiconductor",
    "供应链": "supply chain",
    "财报": "earnings report",
    "市值": "market cap",
    "股价": "stock price",
}

# 常见搜索后缀翻译
_SUFFIX_TRANSLATIONS: dict[str, str] = {
    "的故事": "story",
    "的经历": "experience",
    "的背景": "background",
    "的成就": "achievements",
    "的失败": "failures",
    "的秘密": "secrets",
    "怎么样": "",
    "是谁": "who is",
    "是什么": "what is",
}


# === 服务 ===


class QueryTranslationService:
    """搜索关键词翻译服务。

    默认将中文查询翻译为英文。用户明确选择中文搜索时跳过翻译。
    """

    def __init__(self, ai_gateway: "AIGateway | None" = None) -> None:
        self._ai_gateway = ai_gateway

    async def translate_queries(
        self,
        queries: list[str],
        force_chinese: bool = False,
        target_language: str = "en",
    ) -> QueryTranslationResult:
        """翻译查询列表。

        Args:
            queries: 原始查询列表
            force_chinese: 用户是否明确要求使用中文搜索
            target_language: 目标语言（默认英文）

        Returns:
            QueryTranslationResult
        """
        if not queries:
            return QueryTranslationResult()

        # 用户明确选择中文搜索 → 全部 passthrough
        if force_chinese:
            result_queries = [
                TranslatedQuery(
                    original=q,
                    translated=q,
                    language="zh",
                    method="passthrough",
                    confidence=1.0,
                )
                for q in queries
            ]
            return QueryTranslationResult(
                queries=result_queries,
                translated_count=0,
                passthrough_count=len(queries),
                used_llm=False,
            )

        # 分离：已经是英文的 → passthrough，含中文的 → 需要翻译
        to_translate: list[tuple[int, str]] = []
        results: list[TranslatedQuery | None] = [None] * len(queries)

        for i, query in enumerate(queries):
            if self._is_chinese(query):
                to_translate.append((i, query))
            else:
                # 已经是英文，直接 passthrough
                results[i] = TranslatedQuery(
                    original=query,
                    translated=query,
                    language="en",
                    method="passthrough",
                    confidence=1.0,
                )

        passthrough_count = len(queries) - len(to_translate)

        # 翻译中文查询
        if to_translate:
            chinese_queries = [q for _, q in to_translate]
            translations = await self._translate_batch(chinese_queries)

            for (idx, original), translated in zip(to_translate, translations):
                results[idx] = translated

        # 确保没有 None
        final_queries = [r for r in results if r is not None]
        translated_count = sum(1 for q in final_queries if q.method != "passthrough")

        return QueryTranslationResult(
            queries=final_queries,
            translated_count=translated_count,
            passthrough_count=passthrough_count,
            used_llm=any(q.method == "llm" for q in final_queries),
        )

    async def translate_single(
        self,
        query: str,
        force_chinese: bool = False,
    ) -> TranslatedQuery:
        """翻译单条查询。"""
        result = await self.translate_queries([query], force_chinese=force_chinese)
        if result.queries:
            return result.queries[0]
        return TranslatedQuery(original=query, translated=query, method="passthrough")

    # === 翻译逻辑 ===

    async def _translate_batch(self, queries: list[str]) -> list[TranslatedQuery]:
        """批量翻译中文查询。先尝试 LLM，失败用规则。"""
        # 尝试 LLM
        llm_results = await self._try_llm_translate(queries)
        if llm_results is not None:
            return llm_results

        # 规则 fallback
        return [self._rule_translate(q) for q in queries]

    async def _try_llm_translate(
        self, queries: list[str]
    ) -> list[TranslatedQuery] | None:
        """尝试 LLM 翻译，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        try:
            result = await self._ai_gateway.run_json(
                task_name="query_translation",
                payload={
                    "queries": queries,
                    "target_language": "en",
                },
                output_schema=QueryTranslationLLMOutput,
                language="zh",
            )

            # 将 LLM 输出映射回 TranslatedQuery
            translations: list[TranslatedQuery] = []
            for i, query in enumerate(queries):
                if i < len(result.translations):
                    item = result.translations[i]
                    translated = item.translated.strip()
                    if not translated:
                        # LLM 返回空翻译，fallback 到规则
                        translations.append(self._rule_translate(query))
                    else:
                        translations.append(TranslatedQuery(
                            original=query,
                            translated=translated,
                            language="en",
                            method="llm",
                            confidence=item.confidence,
                        ))
                else:
                    # LLM 返回数量不足，fallback
                    translations.append(self._rule_translate(query))

            return translations

        except Exception as e:
            logger.warning("llm_query_translation_failed error=%s", str(e))
            return None

    def _rule_translate(self, query: str) -> TranslatedQuery:
        """规则翻译：实体映射 + 关键词替换。"""
        translated = query
        replaced_any = False

        # 1. 替换已知实体（按长度降序，优先匹配更长的）
        for zh, en in sorted(_ENTITY_TRANSLATIONS.items(), key=lambda x: len(x[0]), reverse=True):
            if zh in translated:
                translated = translated.replace(zh, en)
                replaced_any = True

        # 2. 替换常见后缀
        for zh_suffix, en_suffix in _SUFFIX_TRANSLATIONS.items():
            if translated.endswith(zh_suffix):
                translated = translated[: -len(zh_suffix)].strip()
                if en_suffix:
                    translated = f"{translated} {en_suffix}"
                replaced_any = True
                break

        # 3. 清理：去除残留的中文字符和标点
        translated = re.sub(r'[，。、；：""''（）【】《》？！]', ' ', translated)
        # 去除残留的中文连接词（的、和、与、在、了、是）
        translated = re.sub(r'[的和与在了是]', ' ', translated)
        translated = re.sub(r'\s+', ' ', translated).strip()

        # 4. 判断翻译质量
        remaining_cjk = len(_CJK_RE.findall(translated))
        total_chars = len(translated)

        if remaining_cjk == 0 and replaced_any:
            # 完全翻译成功
            return TranslatedQuery(
                original=query,
                translated=translated,
                language="en",
                method="rule",
                confidence=0.7,
            )
        elif replaced_any and remaining_cjk < total_chars * 0.3:
            # 部分翻译（大部分已转为英文）
            # 去除残留中文字符
            translated = _CJK_RE.sub('', translated)
            translated = re.sub(r'\s+', ' ', translated).strip()
            return TranslatedQuery(
                original=query,
                translated=translated,
                language="en",
                method="rule",
                confidence=0.5,
            )
        elif not replaced_any:
            # 完全无法翻译，保留原文
            return TranslatedQuery(
                original=query,
                translated=query,
                language="zh",
                method="rule",
                confidence=0.2,
            )
        else:
            # 有部分替换但残留中文较多，仍然返回翻译结果
            translated = _CJK_RE.sub('', translated)
            translated = re.sub(r'\s+', ' ', translated).strip()
            if translated:
                return TranslatedQuery(
                    original=query,
                    translated=translated,
                    language="en",
                    method="rule",
                    confidence=0.4,
                )
            return TranslatedQuery(
                original=query,
                translated=query,
                language="zh",
                method="rule",
                confidence=0.2,
            )

    # === 工具方法 ===

    @staticmethod
    def _is_chinese(text: str) -> bool:
        """判断文本是否包含中文字符。"""
        return bool(_CJK_RE.search(text))
