"""跨来源去重服务 - 合并多篇资料中的重复信息。

职责：
- 输入多个 NormalizedDocumentAnalysis，输出 DeduplicatedClaimGroup 列表
- 相同含义的 claim 合并，保留所有 supporting_sources
- 来源冲突标记 conflicting_sources
- LLM 失败时 fallback 到规则去重
- 不生成研究文章、不写 Obsidian、不调用搜索/抓取
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

from app.ai.schemas import CrossSourceDeduplicationOutput, DeduplicationGroupLLMItem
from app.tracing.models import TracePhase
from models.enums import ClaimConfidence
from models.schemas import (
    DeduplicatedClaimGroup,
    NormalizedContentUnit,
    NormalizedDocumentAnalysis,
)

if TYPE_CHECKING:
    from app.ai.gateway import AIGateway
    from app.tracing.recorder import TraceRecorder

logger = logging.getLogger(__name__)


class CrossSourceDeduplicationService:
    """跨来源事实去重与冲突检测。"""

    def __init__(
        self,
        ai_gateway: "AIGateway | None" = None,
        trace_recorder: "TraceRecorder | None" = None,
    ) -> None:
        self._ai_gateway = ai_gateway
        self._trace = trace_recorder

    async def deduplicate(
        self,
        task_id: str,
        analyses: list[NormalizedDocumentAnalysis],
    ) -> list[DeduplicatedClaimGroup]:
        """对多篇归一化文档进行跨来源去重。

        Args:
            task_id: 研究任务 ID（用于 trace）
            analyses: 多篇 NormalizedDocumentAnalysis

        Returns:
            去重合并后的 DeduplicatedClaimGroup 列表
        """
        start_time = time.perf_counter()
        self._trace_started(task_id)

        # 1. 收集所有 claims
        all_claims = self._collect_all_claims(analyses)
        before_count = len(all_claims)

        if not all_claims:
            self._trace_finished(
                task_id,
                before_claim_count=0,
                after_group_count=0,
                duplicate_removed_count=0,
                conflict_count=0,
                used_llm=False,
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
            return []

        # 2. 规则去重
        rule_groups = self._rule_based_deduplicate(all_claims)

        # 3. 可选 LLM 去重
        used_llm = False
        final_groups: list[DeduplicatedClaimGroup]

        llm_groups = await self._try_llm_deduplicate(task_id, all_claims)
        if llm_groups is not None:
            final_groups = llm_groups
            used_llm = True
        else:
            final_groups = rule_groups

        # 4. 丢弃没有 supporting_sources 的 group
        final_groups = [g for g in final_groups if g.supporting_sources]

        # 5. Trace
        after_count = len(final_groups)
        duplicate_removed = before_count - after_count
        conflict_count = sum(1 for g in final_groups if g.conflicting_sources)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        self._trace_finished(
            task_id,
            before_claim_count=before_count,
            after_group_count=after_count,
            duplicate_removed_count=duplicate_removed,
            conflict_count=conflict_count,
            used_llm=used_llm,
            duration_ms=duration_ms,
        )

        logger.info(
            "cross_source_deduplication_done task_id=%s before=%d after=%d removed=%d conflicts=%d llm=%s",
            task_id, before_count, after_count, duplicate_removed, conflict_count, used_llm,
        )

        return final_groups

    # === 收集 Claims ===

    @staticmethod
    def _collect_all_claims(
        analyses: list[NormalizedDocumentAnalysis],
    ) -> list[NormalizedContentUnit]:
        """从所有 analyses 中收集全部 claims。"""
        all_claims: list[NormalizedContentUnit] = []
        for analysis in analyses:
            all_claims.extend(analysis.main_claims)
            all_claims.extend(analysis.timeline_events)
            all_claims.extend(analysis.story_points)
            all_claims.extend(analysis.quotes)
            all_claims.extend(analysis.verification_needed)
        return all_claims

    # === 规则去重 ===

    def _rule_based_deduplicate(
        self, claims: list[NormalizedContentUnit]
    ) -> list[DeduplicatedClaimGroup]:
        """规则去重：按 normalized_claim 和实体特征合并。"""
        # 分组：key → list of claim indices
        groups: dict[str, list[int]] = {}

        for i, claim in enumerate(claims):
            key = self._compute_dedup_key(claim)
            if key in groups:
                groups[key].append(i)
            else:
                groups[key] = [i]

        # 构建 DeduplicatedClaimGroup
        result: list[DeduplicatedClaimGroup] = []
        for key, indices in groups.items():
            group_claims = [claims[i] for i in indices]
            group = self._merge_claims_to_group(group_claims)
            result.append(group)

        # 按 importance 降序排列
        result.sort(key=lambda g: g.importance, reverse=True)
        return result

    def _compute_dedup_key(self, claim: NormalizedContentUnit) -> str:
        """计算去重 key。

        规则：
        1. normalized_claim lower/strip 后相同 → 同 key
        2. 相同 people + dates + places 且 claim_type 相同 → 同 key（如果实体非空）
        """
        # 主 key: normalized_claim 标准化
        primary = claim.normalized_claim.lower().strip()
        if primary:
            return f"claim:{primary}"

        # 备选 key: 实体组合（仅当有实体时）
        if claim.people or claim.dates or claim.places:
            entity_parts = sorted(claim.people) + sorted(claim.dates) + sorted(claim.places)
            entity_key = "|".join(p.lower().strip() for p in entity_parts)
            return f"entity:{claim.claim_type.value}:{entity_key}"

        # 无法去重，使用唯一 key
        raw = f"{claim.source_id}:{claim.claim[:80]}"
        return f"unique:{hashlib.md5(raw.encode()).hexdigest()[:12]}"

    def _merge_claims_to_group(
        self, claims: list[NormalizedContentUnit]
    ) -> DeduplicatedClaimGroup:
        """将一组相同含义的 claims 合并为 DeduplicatedClaimGroup。"""
        # 选最佳表述（最长的 merged_claim）
        best_claim = max(claims, key=lambda c: len(c.claim))
        normalized = best_claim.normalized_claim or best_claim.claim

        # 收集 supporting_sources（按 source_id 去重）
        supporting_sources: list[dict] = []
        seen_source_ids: set[str] = set()
        for claim in claims:
            if claim.source_id and claim.source_id not in seen_source_ids:
                supporting_sources.append({
                    "source_id": claim.source_id,
                    "document_id": claim.document_id,
                    "title": claim.source_title,
                    "url": claim.source_url or "",
                    "evidence_text": claim.evidence_text or "",
                })
                seen_source_ids.add(claim.source_id)

        # 收集 evidence_texts
        evidence_texts = [
            c.evidence_text for c in claims
            if c.evidence_text and c.evidence_text.strip()
        ]

        # 合并实体
        all_people: set[str] = set()
        all_places: set[str] = set()
        all_dates: set[str] = set()
        all_concepts: set[str] = set()
        for claim in claims:
            all_people.update(claim.people)
            all_places.update(claim.places)
            all_dates.update(claim.dates)
            all_concepts.update(claim.concepts)

        # importance: 取最高
        importance = max(c.importance for c in claims)

        # confidence: 根据来源数量计算
        confidence = self._compute_merged_confidence(claims, len(supporting_sources))

        # needs_verification: 任一来源需要核验则保留
        needs_verification = any(c.needs_verification for c in claims)

        # claim_type: 取第一个非 UNKNOWN 的
        claim_type = "fact"
        for c in claims:
            if c.claim_type.value != "unknown":
                claim_type = c.claim_type.value
                break

        # group_id
        group_id = hashlib.md5(normalized.encode()).hexdigest()[:12]

        return DeduplicatedClaimGroup(
            group_id=group_id,
            normalized_claim=normalized,
            claim_type=claim_type,
            merged_claim=best_claim.claim,
            supporting_sources=supporting_sources,
            conflicting_sources=[],
            evidence_texts=evidence_texts,
            people=sorted(all_people),
            places=sorted(all_places),
            dates=sorted(all_dates),
            concepts=sorted(all_concepts),
            confidence=confidence,
            importance=importance,
            needs_verification=needs_verification,
        )

    @staticmethod
    def _compute_merged_confidence(
        claims: list[NormalizedContentUnit],
        source_count: int,
    ) -> ClaimConfidence:
        """根据来源数量和原始 confidence 计算合并后的 confidence。

        规则：
        - 3+ 独立来源确认 → high
        - 2 源确认 → medium（除非原始都是 high）
        - 单源 → 保持原 confidence
        - 有 conflicting → conflicting
        """
        # 检查是否有 conflicting
        if any(c.confidence == ClaimConfidence.CONFLICTING for c in claims):
            return ClaimConfidence.CONFLICTING

        if source_count >= 3:
            return ClaimConfidence.HIGH
        elif source_count == 2:
            # 如果两个来源都是 high，合并后也是 high
            if all(c.confidence == ClaimConfidence.HIGH for c in claims):
                return ClaimConfidence.HIGH
            return ClaimConfidence.MEDIUM
        else:
            # 单源：保持原 confidence
            return claims[0].confidence

    # === LLM 去重 ===

    async def _try_llm_deduplicate(
        self,
        task_id: str,
        claims: list[NormalizedContentUnit],
    ) -> list[DeduplicatedClaimGroup] | None:
        """尝试 LLM 去重，失败返回 None。"""
        if self._ai_gateway is None:
            return None

        # 获取 max_input_chars
        max_input_chars = self._get_max_input_chars()

        # 构建 LLM 输入：只发送 importance 高的 claims（如果太多）
        claims_for_llm = self._prepare_claims_for_llm(claims, max_input_chars)

        try:
            result = await self._ai_gateway.run_json(
                task_name="cross_source_deduplication",
                payload={
                    "topic": "",  # topic 由 prompt template 的上下文提供
                    "claims": claims_for_llm,
                },
                output_schema=CrossSourceDeduplicationOutput,
                language="zh",
            )
            return self._apply_llm_output(claims, result)
        except Exception as e:
            logger.warning("llm_deduplication_failed error=%s", str(e))
            self._trace_failed(task_id, str(e), 0)
            return None

    def _prepare_claims_for_llm(
        self,
        claims: list[NormalizedContentUnit],
        max_chars: int,
    ) -> list[dict[str, Any]]:
        """准备 LLM 输入，限制总字符数。"""
        # 按 importance 降序排列
        indexed_claims = sorted(
            enumerate(claims),
            key=lambda x: x[1].importance,
            reverse=True,
        )

        result: list[dict[str, Any]] = []
        total_chars = 0

        for original_index, claim in indexed_claims:
            entry = {
                "index": original_index,
                "claim": claim.claim[:200],
                "normalized_claim": claim.normalized_claim[:200],
                "claim_type": claim.claim_type.value,
                "confidence": claim.confidence.value,
                "evidence_text": (claim.evidence_text or "")[:100],
                "source_id": claim.source_id,
                "document_id": claim.document_id,
                "source_title": claim.source_title[:50],
                "source_url": claim.source_url or "",
            }
            entry_chars = sum(len(str(v)) for v in entry.values())
            if total_chars + entry_chars > max_chars:
                break
            result.append(entry)
            total_chars += entry_chars

        return result

    def _apply_llm_output(
        self,
        claims: list[NormalizedContentUnit],
        llm_output: CrossSourceDeduplicationOutput,
    ) -> list[DeduplicatedClaimGroup]:
        """将 LLM 输出应用到 claims，构建 DeduplicatedClaimGroup 列表。"""
        result: list[DeduplicatedClaimGroup] = []
        grouped_indices: set[int] = set()

        # 处理 LLM 分组
        for group in llm_output.groups:
            valid_indices = [i for i in group.claim_indices if 0 <= i < len(claims)]
            if not valid_indices:
                continue

            group_claims = [claims[i] for i in valid_indices]
            merged = self._merge_claims_to_group(group_claims)

            # 使用 LLM 提供的 merged_claim（如果有）
            if group.merged_claim:
                merged.merged_claim = group.merged_claim
            if group.canonical_claim:
                merged.normalized_claim = group.canonical_claim

            # confidence boost
            if group.confidence_boost and len(set(c.source_id for c in group_claims)) >= 2:
                merged.confidence = ClaimConfidence.HIGH
                # 重新构建以通过 validator（high 需要 sources）
                if not merged.supporting_sources:
                    merged.confidence = ClaimConfidence.MEDIUM

            result.append(merged)
            grouped_indices.update(valid_indices)

        # 处理 LLM 冲突
        for conflict in llm_output.conflicts:
            valid_indices = [i for i in conflict.conflicting_indices if 0 <= i < len(claims)]
            if len(valid_indices) < 2:
                continue

            conflict_claims = [claims[i] for i in valid_indices]

            # 第一个作为 supporting，其余作为 conflicting
            primary = conflict_claims[0]
            conflicting_sources = []
            for c in conflict_claims[1:]:
                conflicting_sources.append({
                    "source_id": c.source_id,
                    "document_id": c.document_id,
                    "title": c.source_title,
                    "url": c.source_url or "",
                    "evidence_text": c.evidence_text or "",
                    "claim": c.claim,
                })

            group = DeduplicatedClaimGroup(
                group_id=hashlib.md5(conflict.topic_claim.encode()).hexdigest()[:12],
                normalized_claim=conflict.topic_claim or primary.normalized_claim,
                claim_type=primary.claim_type.value,
                merged_claim=conflict.explanation or primary.claim,
                supporting_sources=[{
                    "source_id": primary.source_id,
                    "document_id": primary.document_id,
                    "title": primary.source_title,
                    "url": primary.source_url or "",
                    "evidence_text": primary.evidence_text or "",
                }],
                conflicting_sources=conflicting_sources,
                confidence=ClaimConfidence.CONFLICTING,
                importance=max(c.importance for c in conflict_claims),
                needs_verification=True,
            )
            result.append(group)
            grouped_indices.update(valid_indices)

        # 未被分组的 claims 作为独立 group
        for i, claim in enumerate(claims):
            if i in grouped_indices:
                continue
            group = self._merge_claims_to_group([claim])
            result.append(group)

        # 按 importance 降序
        result.sort(key=lambda g: g.importance, reverse=True)
        return result

    @staticmethod
    def _get_max_input_chars() -> int:
        """获取 max_input_chars 配置。"""
        try:
            from app.ai.tasks import load_llm_task_config
            config = load_llm_task_config("cross_source_deduplication")
            return config.max_input_chars
        except Exception:
            return 12000

    # === Trace ===

    def _trace_started(self, task_id: str) -> None:
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="cross_source_deduplication_started",
            phase=TracePhase.PROCESSING,
            service="cross_source_deduplication",
        )

    def _trace_finished(
        self,
        task_id: str,
        before_claim_count: int,
        after_group_count: int,
        duplicate_removed_count: int,
        conflict_count: int,
        used_llm: bool,
        duration_ms: int,
    ) -> None:
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="cross_source_deduplication_finished",
            phase=TracePhase.PROCESSING,
            service="cross_source_deduplication",
            metrics={
                "before_claim_count": before_claim_count,
                "after_group_count": after_group_count,
                "duplicate_removed_count": duplicate_removed_count,
                "conflict_count": conflict_count,
                "used_llm": used_llm,
            },
            duration_ms=duration_ms,
        )

    def _trace_failed(self, task_id: str, error: str, duration_ms: int) -> None:
        if self._trace is None:
            return
        self._trace.record(
            task_id=task_id,
            step="cross_source_deduplication_failed",
            phase=TracePhase.PROCESSING,
            level="warning",
            service="cross_source_deduplication",
            error_message=error[:200],
            duration_ms=duration_ms,
        )
