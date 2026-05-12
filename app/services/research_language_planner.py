"""研究语言规划服务 - 根据 topic 决定语言策略。

职责：
- 判断用户输入语言
- 判断研究工作语言 working_language
- 识别 canonical_topic 和 main_entity_canonical
- 决定 search_strategy
- LLM 不可用时使用规则 fallback

设计原则：
- 独立 service，不侵入 search/extraction/gateway
- LLM 失败不向上抛异常，降级到规则版
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.ai.schemas import TopicUnderstandingOutput
from models.enums import LanguageCode, SearchStrategy, TaskMode
from models.schemas import ResearchLanguagePlan

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway

logger = logging.getLogger(__name__)

# ============================================================
# 已知实体映射表
# ============================================================

# 欧美/国际科技实体：中文关键词 → (canonical_en, entity_type)
_WESTERN_ENTITIES: dict[str, tuple[str, str]] = {
    "库克": ("Tim Cook", "person"),
    "蒂姆库克": ("Tim Cook", "person"),
    "蒂姆·库克": ("Tim Cook", "person"),
    "黄仁勋": ("Jensen Huang", "person"),
    "英伟达": ("NVIDIA", "company"),
    "奥特曼": ("Sam Altman", "person"),
    "山姆奥特曼": ("Sam Altman", "person"),
    "山姆·奥特曼": ("Sam Altman", "person"),
    "马斯克": ("Elon Musk", "person"),
    "埃隆马斯克": ("Elon Musk", "person"),
    "特斯拉": ("Tesla", "company"),
    "贝索斯": ("Jeff Bezos", "person"),
    "贝佐斯": ("Jeff Bezos", "person"),
    "杰夫贝索斯": ("Jeff Bezos", "person"),
    "扎克伯格": ("Mark Zuckerberg", "person"),
    "纳德拉": ("Satya Nadella", "person"),
    "苹果": ("Apple", "company"),
    "亚马逊": ("Amazon", "company"),
    "谷歌": ("Google", "company"),
    "微软": ("Microsoft", "company"),
    "脸书": ("Meta (Facebook)", "company"),
}

# 英文关键词直接识别为欧美实体
_WESTERN_ENGLISH_KEYWORDS: set[str] = {
    "OpenAI", "Transformer", "NVIDIA", "Apple", "Google", "Microsoft",
    "Amazon", "Tesla", "SolarCity", "SpaceX", "Meta", "Facebook",
    "Netflix", "Uber", "Airbnb", "Twitter",
}

# 中国本土实体：中文关键词 → (canonical, entity_type)
_CHINESE_ENTITIES: dict[str, tuple[str, str]] = {
    "小米": ("小米", "company"),
    "雷军": ("雷军", "person"),
    "字节跳动": ("字节跳动", "company"),
    "腾讯": ("腾讯", "company"),
    "阿里": ("阿里巴巴", "company"),
    "阿里巴巴": ("阿里巴巴", "company"),
    "华为": ("华为", "company"),
    "百度": ("百度", "company"),
    "美团": ("美团", "company"),
    "拼多多": ("拼多多", "company"),
    "京东": ("京东", "company"),
    "马云": ("马云", "person"),
    "马化腾": ("马化腾", "person"),
    "任正非": ("任正非", "person"),
    "李彦宏": ("李彦宏", "person"),
    "张一鸣": ("张一鸣", "person"),
    "王兴": ("王兴", "person"),
    "刘强东": ("刘强东", "person"),
}

# CJK 字符检测
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_LATIN_RE = re.compile(r"[a-zA-Z]")


class ResearchLanguagePlannerService:
    """研究语言规划服务。"""

    def __init__(self, ai_gateway: "AIGateway | None" = None) -> None:
        self._ai_gateway = ai_gateway

    async def plan(
        self,
        topic: str,
        mode: TaskMode | None = None,
    ) -> ResearchLanguagePlan:
        """根据 topic 生成语言规划。

        Args:
            topic: 用户输入的研究主题（不能为空）
            mode: 可选的研究模式提示

        Returns:
            ResearchLanguagePlan

        Raises:
            ValueError: topic 为空时
        """
        if not topic or not topic.strip():
            raise ValueError("topic 不能为空")

        topic = topic.strip()

        # 尝试 LLM 路径
        llm_plan = await self._try_llm(topic, mode)
        if llm_plan is not None:
            return llm_plan

        # 规则 fallback
        return self._rule_based_plan(topic)

    # ============================================================
    # LLM 路径
    # ============================================================

    async def _try_llm(
        self,
        topic: str,
        mode: TaskMode | None,
    ) -> ResearchLanguagePlan | None:
        """尝试通过 LLM 获取主题理解，再转换为语言规划。"""
        if self._ai_gateway is None:
            return None

        try:
            result: TopicUnderstandingOutput = await self._ai_gateway.run_json(
                task_name="topic_understanding",
                payload={"topic": topic},
                output_schema=TopicUnderstandingOutput,
                language="zh",
            )
            return self._convert_llm_output(topic, result)
        except Exception as e:
            logger.warning(
                "language_planner_llm_failed topic=%r error=%s",
                topic, str(e),
            )
            return None

    def _convert_llm_output(
        self,
        topic: str,
        output: TopicUnderstandingOutput,
    ) -> ResearchLanguagePlan:
        """将 TopicUnderstandingOutput 转换为 ResearchLanguagePlan。"""
        user_lang = self._detect_language(topic)

        # 尝试从 LLM 输出中识别 canonical entity
        main_entity = output.main_entity or ""
        canonical = self._find_canonical(main_entity) or main_entity

        # 判断是否欧美实体
        is_western = self._is_western_topic(topic, main_entity)
        is_chinese = self._is_chinese_topic(topic, main_entity)

        if is_western:
            working_lang = LanguageCode.EN
            strategy = SearchStrategy.ENGLISH_FIRST
            search_langs = [LanguageCode.EN, LanguageCode.ZH]
        elif is_chinese:
            working_lang = LanguageCode.ZH
            strategy = SearchStrategy.CHINESE_FIRST
            search_langs = [LanguageCode.ZH, LanguageCode.EN]
        else:
            working_lang = LanguageCode.MIXED
            strategy = SearchStrategy.BILINGUAL
            search_langs = [LanguageCode.EN, LanguageCode.ZH]

        output_lang = self._decide_output_language(user_lang, topic)

        return ResearchLanguagePlan(
            user_language=user_lang,
            working_language=working_lang,
            output_language=output_lang,
            original_topic=topic,
            canonical_topic=output.normalized_topic or canonical or topic,
            main_entity_original=main_entity or None,
            main_entity_canonical=canonical or None,
            aliases=output.aliases,
            search_languages=search_langs,
            search_strategy=strategy,
            translation_notes=None,
            confidence=0.8,
        )

    # ============================================================
    # 规则 Fallback
    # ============================================================

    def _rule_based_plan(self, topic: str) -> ResearchLanguagePlan:
        """纯规则版语言规划。"""
        user_lang = self._detect_language(topic)

        # 检测欧美实体
        western_match = self._match_western_entity(topic)
        chinese_match = self._match_chinese_entity(topic)

        if western_match:
            canonical_en, _ = western_match
            working_lang = LanguageCode.EN
            strategy = SearchStrategy.ENGLISH_FIRST
            search_langs = [LanguageCode.EN, LanguageCode.ZH]
            canonical_topic = self._build_canonical_topic(topic, canonical_en)
            confidence = 0.7
        elif chinese_match:
            canonical_zh, _ = chinese_match
            working_lang = LanguageCode.ZH
            strategy = SearchStrategy.CHINESE_FIRST
            search_langs = [LanguageCode.ZH, LanguageCode.EN]
            canonical_topic = topic
            canonical_en = None
            confidence = 0.6
        else:
            # 无法判断
            working_lang = LanguageCode.MIXED
            strategy = SearchStrategy.BILINGUAL
            search_langs = [LanguageCode.EN, LanguageCode.ZH]
            canonical_topic = topic
            canonical_en = None
            confidence = 0.3

        output_lang = self._decide_output_language(user_lang, topic)

        # 提取 original entity（中文关键词）
        main_entity_original: str | None = None
        if western_match:
            # 找到匹配的中文关键词
            for key in _WESTERN_ENTITIES:
                if key in topic:
                    main_entity_original = key
                    break

        return ResearchLanguagePlan(
            user_language=user_lang,
            working_language=working_lang,
            output_language=output_lang,
            original_topic=topic,
            canonical_topic=canonical_topic,
            main_entity_original=main_entity_original,
            main_entity_canonical=canonical_en if western_match else None,
            aliases=[],
            search_languages=search_langs,
            search_strategy=strategy,
            translation_notes=None,
            confidence=confidence,
        )

    # ============================================================
    # 辅助方法
    # ============================================================

    def _detect_language(self, text: str) -> LanguageCode:
        """检测文本主要语言。

        CJK 字符每个字承载更多语义，所以按 1 CJK = 2 latin 加权。
        """
        cjk_count = len(_CJK_RE.findall(text))
        latin_chars = _LATIN_RE.findall(text)
        latin_count = len(latin_chars)

        if cjk_count == 0 and latin_count == 0:
            return LanguageCode.UNKNOWN

        if cjk_count > 0 and latin_count == 0:
            return LanguageCode.ZH

        if cjk_count == 0 and latin_count > 0:
            return LanguageCode.EN

        # 混合：CJK 每字权重 2（一个汉字 ≈ 一个英文单词）
        weighted_cjk = cjk_count * 2
        total = weighted_cjk + latin_count
        cjk_ratio = weighted_cjk / total

        if cjk_ratio > 0.6:
            return LanguageCode.ZH
        elif cjk_ratio < 0.2:
            return LanguageCode.EN
        else:
            return LanguageCode.MIXED

    def _match_western_entity(self, topic: str) -> tuple[str, str] | None:
        """从 topic 中匹配欧美实体，返回 (canonical_en, entity_type) 或 None。"""
        # 先匹配中文关键词（按长度降序，优先匹配更具体的）
        for key in sorted(_WESTERN_ENTITIES.keys(), key=len, reverse=True):
            if key in topic:
                return _WESTERN_ENTITIES[key]

        # 再匹配英文关键词（大小写不敏感）
        topic_upper = topic.upper()
        for keyword in _WESTERN_ENGLISH_KEYWORDS:
            if keyword.upper() in topic_upper:
                return (keyword, "unknown")

        return None

    def _match_chinese_entity(self, topic: str) -> tuple[str, str] | None:
        """从 topic 中匹配中国本土实体。"""
        for key in sorted(_CHINESE_ENTITIES.keys(), key=len, reverse=True):
            if key in topic:
                return _CHINESE_ENTITIES[key]
        return None

    def _is_western_topic(self, topic: str, main_entity: str) -> bool:
        """判断是否为欧美/国际实体主题。"""
        if self._match_western_entity(topic):
            return True
        if main_entity and self._match_western_entity(main_entity):
            return True
        return False

    def _is_chinese_topic(self, topic: str, main_entity: str) -> bool:
        """判断是否为中国本土实体主题。"""
        # 如果同时匹配了欧美实体，欧美优先
        if self._is_western_topic(topic, main_entity):
            return False
        if self._match_chinese_entity(topic):
            return True
        if main_entity and self._match_chinese_entity(main_entity):
            return True
        return False

    def _find_canonical(self, entity: str) -> str | None:
        """尝试找到实体的 canonical English name。"""
        if not entity:
            return None
        # 查中文表
        if entity in _WESTERN_ENTITIES:
            return _WESTERN_ENTITIES[entity][0]
        # 查英文关键词
        entity_upper = entity.upper()
        for keyword in _WESTERN_ENGLISH_KEYWORDS:
            if keyword.upper() == entity_upper:
                return keyword
        return None

    def _build_canonical_topic(self, topic: str, canonical_entity: str) -> str:
        """构建 canonical_topic：用英文实体名替换中文实体名。"""
        # 找到匹配的中文关键词并替换
        result = topic
        for key in sorted(_WESTERN_ENTITIES.keys(), key=len, reverse=True):
            if key in result:
                result = result.replace(key, canonical_entity, 1)
                break
        # 如果是英文关键词匹配，topic 本身可能已经包含英文
        return result

    def _decide_output_language(self, user_lang: LanguageCode, topic: str) -> LanguageCode:
        """决定输出语言。

        原则：有中文字符出现 → 用户大概率是中文用户 → 输出中文。
        只有纯英文输入才输出英文。
        """
        if user_lang == LanguageCode.ZH:
            return LanguageCode.ZH
        if user_lang == LanguageCode.EN:
            return LanguageCode.EN
        # mixed / unknown → 只要有 CJK 就输出中文
        cjk_count = len(_CJK_RE.findall(topic))
        if cjk_count > 0:
            return LanguageCode.ZH
        return LanguageCode.EN
