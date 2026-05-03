"""M1-6 — admission decisions + audit."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..admission_rules import RULE_ENGINE_VERSION, correlation_dedup_stub, evaluate_admission_from_sim_metrics
from ..audit_log import write_audit_event
from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..seed_models import AdmissionDecision
from ..wq_pipeline import get_wq_simulation_owned

router = APIRouter(prefix="/api/v1/admission", tags=["admission"])


def _new_decision_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"adm_{day}_{uuid.uuid4().hex[:8]}"


class DecideRequest(BaseModel):
    wq_simulation_run_id: str = Field(..., min_length=1)
    edit_candidate_id: str | None = None


def _decision_detail(d: AdmissionDecision) -> dict:
    return {
        "id": d.id,
        "decision": d.decision,
        "reasons": d.reasons,
        "wq_simulation_run_id": d.wq_simulation_run_id,
        "edit_candidate_id": d.edit_candidate_id,
        "expression_snapshot": d.expression_snapshot,
        "rule_engine_version": d.rule_engine_version,
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

    is_metrics = run.is_metrics if isinstance(run.is_metrics, dict) else {}
    decision, reasons = evaluate_admission_from_sim_metrics(is_metrics, ok=run.ok)
    reasons["correlation_dedup_stub"] = correlation_dedup_stub(run.expression)

    row = AdmissionDecision(
        id=_new_decision_id(),
        created_by=str(user.id),
        edit_candidate_id=payload.edit_candidate_id or run.edit_candidate_id,
        wq_simulation_run_id=run.id,
        expression_snapshot=run.expression,
        decision=decision,
        reasons=reasons,
        rule_engine_version=RULE_ENGINE_VERSION,
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
