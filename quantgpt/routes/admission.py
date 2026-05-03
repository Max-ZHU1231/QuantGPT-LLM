"""M1-6 — admission decisions + audit + optional rule profile / human review."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit_log import write_audit_event
from ..auth import get_current_user
from ..db import get_db
from ..factor_pipeline.admission_persist import admission_decision_detail, persist_admission_decision_for_run
from ..models import User
from ..seed_models import AdmissionDecision
from ..wq_pipeline import get_wq_simulation_owned

router = APIRouter(prefix="/api/v1/admission", tags=["admission"])


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


@router.post("/decide", status_code=201)
async def decide_admission(
    payload: DecideRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_wq_simulation_owned(db, user_id=user.id, run_id=payload.wq_simulation_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="WQ simulation run not found")

    try:
        row = await persist_admission_decision_for_run(
            db,
            user_id=user.id,
            run=run,
            edit_candidate_id=payload.edit_candidate_id,
            rule_profile_id=payload.rule_profile_id,
        )
    except ValueError as e:
        if str(e) == "RULE_PROFILE_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Rule profile not found") from None
        raise

    return {"status": "success", "decision": admission_decision_detail(row)}


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

    return {"status": "success", "decision": admission_decision_detail(row)}
