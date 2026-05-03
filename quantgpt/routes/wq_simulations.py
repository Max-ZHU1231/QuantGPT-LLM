"""M1-5 — WQ simulate → persist metrics (WQBrainClient.simulate only)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit_log import write_audit_event
from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..wq_pipeline import persist_wq_simulation, verify_edit_candidate_owned, wq_simulate_metrics_sync

router = APIRouter(prefix="/api/v1/wq_simulations", tags=["wq_simulations"])


class RunWQSimulateRequest(BaseModel):
    expression: str = Field(..., min_length=1)
    edit_candidate_id: str | None = None
    seed_factor_id: str | None = None
    region: str = Field(default="USA", max_length=20)
    universe: str = Field(default="TOP3000", max_length=40)
    delay: int = Field(default=1, ge=0, le=10)
    decay: int = Field(default=0, ge=0)
    neutralization: str = Field(default="SUBINDUSTRY", max_length=40)
    truncation: float = Field(default=0.08, ge=0.0, le=1.0)
    account: str = Field(default="primary", max_length=20)


def _run_summary(row) -> dict:
    return {
        "id": row.id,
        "expression": row.expression,
        "ok": row.ok,
        "error_message": row.error_message,
        "alpha_id": row.alpha_id,
        "simulation_id": row.simulation_id,
        "region": row.region,
        "universe": row.universe,
        "edit_candidate_id": row.edit_candidate_id,
        "seed_factor_id": row.seed_factor_id,
        "is_metrics": row.is_metrics,
        "oos_metrics": row.oos_metrics,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/run", status_code=201)
async def run_wq_simulation(
    payload: RunWQSimulateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.edit_candidate_id:
        cand = await verify_edit_candidate_owned(
            db, user_id=user.id, candidate_id=payload.edit_candidate_id
        )
        if not cand:
            raise HTTPException(status_code=404, detail="Edit candidate not found")

    sim = await asyncio.to_thread(
        wq_simulate_metrics_sync,
        payload.expression,
        region=payload.region,
        universe=payload.universe,
        delay=payload.delay,
        decay=payload.decay,
        neutralization=payload.neutralization,
        truncation=payload.truncation,
        account=payload.account,
    )

    seed_id = payload.seed_factor_id
    row = await persist_wq_simulation(
        db,
        user_id=user.id,
        expression=payload.expression,
        sim=sim,
        edit_candidate_id=payload.edit_candidate_id,
        seed_factor_id=seed_id,
        region=payload.region,
        universe=payload.universe,
        delay=payload.delay,
        decay=payload.decay,
        neutralization=payload.neutralization,
        truncation=payload.truncation,
        account=payload.account,
    )

    await write_audit_event(
        db,
        user_id=user.id,
        event_type="simulate",
        entity_type="wq_simulation_run",
        entity_id=row.id,
        payload={"ok": row.ok, "alpha_id": row.alpha_id},
    )

    return {"status": "success", "simulation": _run_summary(row), "raw": sim}
