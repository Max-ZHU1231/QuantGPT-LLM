"""流水线门面 — 映射模板 §6 步骤到现有 quantgpt 服务（不重复业务实现）。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class FactorResearchPipeline:
    """LLM 因子研发改造 MVP 门面（M1–M7 能力聚合）。

    各 Step 调用既有模块；未实现部分在 ``status.IMPLEMENTATION_MATRIX`` 标注为 planned/partial。
    """

    # --- Step 1 锚因子（REST / SeedFactorManager）---
    # 建议使用 routes.seed_factors；此处仅文档化。

    @staticmethod
    async def step3_llm_minimal_edit(
        db: AsyncSession,
        *,
        user_id: UUID,
        seed_factor_id: str,
        target_gap: dict[str, Any],
        knowledge_base: dict[str, Any] | None = None,
    ):
        """§6.3 → ``minimal_edit_generator.generate_minimal_edits_for_seed``."""
        from quantgpt.minimal_edit_generator import generate_minimal_edits_for_seed

        return await generate_minimal_edits_for_seed(
            db,
            user_id=user_id,
            seed_factor_id=seed_factor_id,
            target_gap=target_gap,
            knowledge_base=knowledge_base,
        )

    @staticmethod
    def step4_expression_gate_wq(expression: str, *, strict_whitelist: bool = False) -> dict[str, Any]:
        """§6.4 → Parser(mode=wq) + 可选标识符白名单。"""
        from quantgpt.expression_gate import validate_wq

        return validate_wq(expression, strict_whitelist=strict_whitelist)

    @staticmethod
    def step5_wq_simulate_sync(
        expression: str,
        *,
        mock: bool = False,
        region: str = "USA",
        universe: str = "TOP3000",
        delay: int = 1,
        decay: int = 0,
        neutralization: str = "SUBINDUSTRY",
        truncation: float = 0.08,
        account: str = "primary",
    ) -> dict[str, Any]:
        """§6.5 → ``wq_pipeline.wq_simulate_metrics_sync``（不落库；落库走 REST）。"""
        from quantgpt.wq_pipeline import wq_simulate_metrics_sync

        return wq_simulate_metrics_sync(
            expression,
            region=region,
            universe=universe,
            delay=delay,
            decay=decay,
            neutralization=neutralization,
            truncation=truncation,
            account=account,
            mock=mock,
        )

    @staticmethod
    async def step5_persist_simulation(
        db: AsyncSession,
        *,
        user_id: UUID,
        expression: str,
        sim: dict[str, Any],
        edit_candidate_id: str | None = None,
        seed_factor_id: str | None = None,
        region: str = "USA",
        universe: str = "TOP3000",
        delay: int = 1,
        decay: int = 0,
        neutralization: str = "SUBINDUSTRY",
        truncation: float = 0.08,
        account: str = "primary",
    ):
        """§6.5 落库 → ``wq_pipeline.persist_wq_simulation``。"""
        from quantgpt.wq_pipeline import persist_wq_simulation

        return await persist_wq_simulation(
            db,
            user_id=user_id,
            expression=expression,
            sim=sim,
            edit_candidate_id=edit_candidate_id,
            seed_factor_id=seed_factor_id,
            region=region,
            universe=universe,
            delay=delay,
            decay=decay,
            neutralization=neutralization,
            truncation=truncation,
            account=account,
        )

    @staticmethod
    def step6_evaluate_admission(is_metrics: dict | None, *, simulation_ok: bool):
        """§6.6 → ``factor_pipeline.admission.evaluate_admission_from_sim_metrics``。"""
        from .admission import evaluate_admission_from_sim_metrics

        return evaluate_admission_from_sim_metrics(is_metrics, ok=simulation_ok)

    @staticmethod
    async def step7_audit(
        db: AsyncSession,
        *,
        user_id: UUID | None,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
    ):
        """§6.7 → ``audit_log.write_audit_event``。"""
        from quantgpt.audit_log import write_audit_event

        return await write_audit_event(
            db,
            user_id=user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
