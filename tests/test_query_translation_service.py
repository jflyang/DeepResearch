"""测试 QueryTranslationService。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.query_translation_service import (
    QueryTranslationLLMOutput,
    QueryTranslationResult,
    QueryTranslationService,
    LLMTranslationItem,
    TranslatedQuery,
)


# === Tests ===


class TestChineseToEnglishTranslation:
    """中文查询翻译为英文。"""

    @pytest.mark.asyncio
    async def test_known_entity_translated(self):
        """已知实体正确翻译。"""
        service = QueryTranslationService()
        result = await service.translate_single("库克的童年故事")
        assert "Tim Cook" in result.translated
        assert result.method == "rule"
        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_company_translated(self):
        """公司名翻译。"""
        service = QueryTranslationService()
        result = await service.translate_single("英伟达发展史")
        assert "NVIDIA" in result.translated

    @pytest.mark.asyncio
    async def test_multiple_entities(self):
        """多个实体同时翻译。"""
        service = QueryTranslationService()
        result = await service.translate_single("马斯克和特斯拉")
        assert "Elon Musk" in result.translated
        assert "Tesla" in result.translated

    @pytest.mark.asyncio
    async def test_suffix_translated(self):
        """常见后缀翻译。"""
        service = QueryTranslationService()
        result = await service.translate_single("苹果的故事")
        assert "Apple" in result.translated
        assert "story" in result.translated


class TestEnglishPassthrough:
    """英文查询直接 passthrough。"""

    @pytest.mark.asyncio
    async def test_english_not_translated(self):
        """纯英文查询不翻译。"""
        service = QueryTranslationService()
        result = await service.translate_single("Tim Cook biography")
        assert result.translated == "Tim Cook biography"
        assert result.method == "passthrough"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_english_query_in_batch(self):
        """批量中英文混合，英文不翻译。"""
        service = QueryTranslationService()
        result = await service.translate_queries([
            "Tim Cook early life",
            "库克的童年",
        ])
        assert result.queries[0].method == "passthrough"
        assert result.queries[1].method == "rule"
        assert result.passthrough_count == 1
        assert result.translated_count == 1


class TestForceChinese:
    """用户明确选择中文搜索时保留原文。"""

    @pytest.mark.asyncio
    async def test_force_chinese_preserves_original(self):
        """force_chinese=True 时所有查询保留原文。"""
        service = QueryTranslationService()
        result = await service.translate_queries(
            ["库克的童年故事", "苹果公司发展史"],
            force_chinese=True,
        )
        assert all(q.translated == q.original for q in result.queries)
        assert all(q.method == "passthrough" for q in result.queries)
        assert all(q.language == "zh" for q in result.queries)
        assert result.translated_count == 0
        assert result.passthrough_count == 2

    @pytest.mark.asyncio
    async def test_force_chinese_english_also_preserved(self):
        """force_chinese=True 时英文查询也保留。"""
        service = QueryTranslationService()
        result = await service.translate_single("Apple history", force_chinese=True)
        assert result.translated == "Apple history"
        assert result.method == "passthrough"


class TestLLMTranslation:
    """LLM 翻译。"""

    @pytest.mark.asyncio
    async def test_llm_used_when_available(self):
        """LLM 可用时使用 LLM 翻译。"""
        llm_output = QueryTranslationLLMOutput(
            translations=[
                LLMTranslationItem(original="黄仁勋早期创业", translated="Jensen Huang early entrepreneurship", confidence=0.95),
            ]
        )
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(return_value=llm_output)

        service = QueryTranslationService(ai_gateway=gateway)
        result = await service.translate_single("黄仁勋早期创业")

        assert result.translated == "Jensen Huang early entrepreneurship"
        assert result.method == "llm"
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_to_rule(self):
        """LLM 失败时 fallback 到规则翻译。"""
        gateway = AsyncMock()
        gateway.run_json = AsyncMock(side_effect=RuntimeError("timeout"))

        service = QueryTranslationService(ai_gateway=gateway)
        result = await service.translate_single("库克的童年故事")

        # 不抛异常，fallback 到规则
        assert "Tim Cook" in result.translated
        assert result.method == "rule"

    @pytest.mark.asyncio
    async def test_no_gateway_uses_rules(self):
        """ai_gateway=None 时使用规则。"""
        service = QueryTranslationService(ai_gateway=None)
        result = await service.translate_single("马斯克")
        assert "Elon Musk" in result.translated
        assert result.method == "rule"


class TestBatchTranslation:
    """批量翻译。"""

    @pytest.mark.asyncio
    async def test_batch_mixed_queries(self):
        """批量翻译中英文混合查询。"""
        service = QueryTranslationService()
        result = await service.translate_queries([
            "库克的童年故事",
            "Apple founding story",
            "黄仁勋 NVIDIA",
        ])
        assert len(result.queries) == 3
        assert result.queries[0].language == "en"  # 翻译后
        assert result.queries[1].method == "passthrough"  # 英文直接通过
        assert "Jensen Huang" in result.queries[2].translated

    @pytest.mark.asyncio
    async def test_empty_queries(self):
        """空列表返回空结果。"""
        service = QueryTranslationService()
        result = await service.translate_queries([])
        assert result.queries == []
        assert result.translated_count == 0


class TestUnknownChinese:
    """无法翻译的中文查询。"""

    @pytest.mark.asyncio
    async def test_unknown_chinese_preserved(self):
        """无法匹配实体的纯中文查询保留原文。"""
        service = QueryTranslationService()
        result = await service.translate_single("某个完全未知的中文主题")
        # 无法翻译时保留原文
        assert result.original == "某个完全未知的中文主题"
        assert result.confidence < 0.5

    @pytest.mark.asyncio
    async def test_partial_translation(self):
        """部分可翻译的查询。"""
        service = QueryTranslationService()
        result = await service.translate_single("苹果 CEO")
        assert "Apple" in result.translated
        assert "CEO" in result.translated
