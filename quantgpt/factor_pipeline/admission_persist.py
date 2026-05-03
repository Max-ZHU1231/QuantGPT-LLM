"""入库决策落库 — REST / 一键编排共用。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..admission_rules import RULE_ENGINE_VERSION, correlation_dedup_stub, evaluate_admission_from_sim_metrics
from ..audit_log import write_audit_event
from ..managers.pipeline_rule_profile_manager import PipelineRuleProfileManager
from ..seed_models import AdmissionDecision, WQSimulationRun


def _new_decision_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"adm_{day}_{uuid.uuid4().hex[:8]}"


def admission_decision_detail(d: AdmissionDecision) -> dict[str, Any]:
    return {
        "id": d.id,
        "decision": d.decision,
        "reasons": d.reasons,
        "wq_simulation_run_id": d.wq_simulation_run_id,
        "edit_candidate_id": d.edit_candidate_id,
        "expression_snapshot": d.expression_snapshot,
        "rule_engine_version": d.rule_engine_version,
        "composite_score": d.composite_score,
        "human_approval_status": d.human_approval_status,
        "human_approval_comment": d.human_approval_comment,
        "human_approved_by": d.human_approved_by,
        "human_approved_at": d.human_approved_at.isoformat() if d.human_approved_at else None,
        "approval_chain": d.approval_chain or [],
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


async def persist_admission_decision_for_run(
    db: AsyncSession,
    *,
    user_id: UUID,
    run: WQSimulationRun,
    edit_candidate_id: str | None,
    rule_profile_id: str | None,
) -> AdmissionDecision:
    """对已归属用户的 simulation run 计算规则并入库 AdmissionDecision。"""
    profile_rules = None
    if rule_profile_id:
        pm = PipelineRuleProfileManager(db)
        prof = await pm.get_owned(user_id=user_id, profile_id=rule_profile_id)
        if not prof:
            raise ValueError("RULE_PROFILE_NOT_FOUND")

        profile_rules = prof.rules_json if isinstance(prof.rules_json, dict) else {}

    is_metrics = run.is_metrics if isinstance(run.is_metrics, dict) else None
    oos_metrics = run.oos_metrics if isinstance(run.oos_metrics, dict) else None

    decision, reasons = evaluate_admission_from_sim_metrics(
        is_metrics,
        ok=run.ok,
        oos_metrics=oos_metrics,
        profile_rules_json=profile_rules,
    )
    reasons["correlation_dedup_stub"] = correlation_dedup_stub(run.expression)

    if profile_rules is not None and rule_profile_id:
        reasons["rule_profile_id"] = rule_profile_id

    composite_score = reasons.get("composite_score")
    if composite_score is not None:
        try:
            composite_score = float(composite_score)
        except (TypeError, ValueError):
            composite_score = None

    requires_human = bool(reasons.get("requires_human_review"))
    if decision == "admitted" and requires_human:
        human_status = "pending"
    else:
        human_status = "not_required"

    row = AdmissionDecision(
        id=_new_decision_id(),
        created_by=str(user_id),
        edit_candidate_id=edit_candidate_id or run.edit_candidate_id,
        wq_simulation_run_id=run.id,
        expression_snapshot=run.expression,
        decision=decision,
        reasons=reasons,
        rule_engine_version=RULE_ENGINE_VERSION,
        composite_score=composite_score,
        human_approval_status=human_status,
        human_approval_comment=None,
        human_approved_by=None,
        human_approved_at=None,
        approval_chain=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()

    await write_audit_event(
        db,
        user_id=user_id,
        event_type="decide",
        entity_type="admission_decision",
        entity_id=row.id,
        payload={"decision": decision, "wq_simulation_run_id": run.id},
    )
    return row
