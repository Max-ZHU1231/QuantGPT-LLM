"""M1-6 — admission decisions + audit + optional rule profile / human review."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..admission_rules import RULE_ENGINE_VERSION, correlation_dedup_stub, evaluate_admission_from_sim_metrics
from ..audit_log import write_audit_event
from ..auth import get_current_user
from ..db import get_db
from ..managers.pipeline_rule_profile_manager import PipelineRuleProfileManager
from ..models import User
from ..seed_models import AdmissionDecision
from ..wq_pipeline import get_wq_simulation_owned

router = APIRouter(prefix="/api/v1/admission", tags=["admission"])


def _new_decision_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"adm_{day}_{uuid.uuid4().hex[:8]}"


def _compute_human_status(chain: list | None, min_levels: int) -> str:
    chain = list(chain or [])
    if any(c.get("approved") is False for c in chain):
        return "rejected"
    n_ok = sum(1 for c in chain if c.get("approved") is True)
    if n_ok >= max(1, int(min_levels)):
        return "approved"
    return "pending"


class DecideRequest(BaseModel):
    wq_simulation_run_id: str = Field(..., min_length=1)
    edit_candidate_id: str | None = None
    rule_profile_id: str | None = None


class HumanReviewBody(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = Field(None, max_length=4000)


def _decision_detail(d: AdmissionDecision) -> dict:
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


@router.post("/decide", status_code=201)
async def decide_admission(
    payload: DecideRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_wq_simulation_owned(db, user_id=user.id, run_id=payload.wq_simulation_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="WQ simulation run not found")

    profile_rules = None
    if payload.rule_profile_id:
        pm = PipelineRuleProfileManager(db)
        prof = await pm.get_owned(user_id=user.id, profile_id=payload.rule_profile_id)
        if not prof:
            raise HTTPException(status_code=404, detail="Rule profile not found")
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

    if profile_rules is not None and payload.rule_profile_id:
        reasons["rule_profile_id"] = payload.rule_profile_id

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
        created_by=str(user.id),
        edit_candidate_id=payload.edit_candidate_id or run.edit_candidate_id,
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
        user_id=user.id,
        event_type="decide",
        entity_type="admission_decision",
        entity_id=row.id,
        payload={"decision": decision, "wq_simulation_run_id": run.id},
    )

    return {"status": "success", "decision": _decision_detail(row)}


@router.post("/decisions/{decision_id}/human_review")
async def human_review_admission_decision(
    decision_id: str,
    payload: HumanReviewBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(AdmissionDecision).where(AdmissionDecision.id == decision_id))
    row = res.scalar_one_or_none()
    if not row or row.created_by != str(user.id):
        raise HTTPException(status_code=404, detail="Admission decision not found")

    if row.decision != "admitted":
        raise HTTPException(status_code=400, detail="human_review_only_for_admitted")

    if row.human_approval_status == "not_required":
        raise HTTPException(status_code=400, detail="human_review_not_required")

    if row.human_approval_status in ("approved", "rejected"):
        raise HTTPException(status_code=409, detail="human_review_already_finished")

    hints = (row.reasons or {}).get("workflow_hints") or {}
    min_lv = int(hints.get("min_approval_levels") or 1)

    chain = list(row.approval_chain or [])
    chain.append(
        {
            "approver_id": str(user.id),
            "approved": payload.action == "approve",
            "comment": payload.comment,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    row.approval_chain = chain

    new_status = _compute_human_status(chain, min_lv)
    row.human_approval_status = new_status
    row.human_approval_comment = payload.comment

    if new_status in ("approved", "rejected"):
        row.human_approved_at = datetime.now(timezone.utc)
        row.human_approved_by = str(user.id)
    else:
        row.human_approved_at = None
        row.human_approved_by = None

    await db.flush()

    await write_audit_event(
        db,
        user_id=user.id,
        event_type="human_review_admission",
        entity_type="admission_decision",
        entity_id=row.id,
        payload={"human_approval_status": new_status, "action": payload.action},
    )

    return {"status": "success", "decision": _decision_detail(row)}
