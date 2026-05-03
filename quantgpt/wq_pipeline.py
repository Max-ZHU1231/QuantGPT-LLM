"""M1-5 — candidate expression → WQBrainClient.simulate → persist metrics (no submit)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .seed_models import EditCandidate, GenerationBatch, SeedFactor, WQSimulationRun
from .wq_brain_client import get_client, is_configured


def _new_wsim_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"wsim_{day}_{uuid.uuid4().hex[:8]}"


def wq_simulate_metrics_sync(
    expression: str,
    *,
    region: str = "USA",
    universe: str = "TOP3000",
    delay: int = 1,
    decay: int = 0,
    neutralization: str = "SUBINDUSTRY",
    truncation: float = 0.08,
    account: str = "primary",
    progress_callback=None,
) -> dict:
    """Authenticate → simulate → close session. Mirrors WQBrainClient.simulate result dict."""
    if not is_configured(account):
        return {"ok": False, "error": f"WQ BRAIN not configured for account={account}"}
    client = get_client(account)
    if not client.authenticate():
        client.close()
        return {"ok": False, "error": "WQ BRAIN authentication failed"}
    try:
        return client.simulate(
            expression,
            region=region,
            universe=universe,
            delay=delay,
            decay=decay,
            neutralization=neutralization,
            truncation=truncation,
            progress_callback=progress_callback,
        )
    finally:
        client.close()


async def verify_edit_candidate_owned(
    db: AsyncSession,
    *,
    user_id: UUID,
    candidate_id: str,
) -> EditCandidate | None:
    q = (
        select(EditCandidate)
        .join(GenerationBatch, EditCandidate.batch_id == GenerationBatch.id)
        .join(SeedFactor, EditCandidate.seed_factor_id == SeedFactor.id)
        .where(
            EditCandidate.id == candidate_id,
            SeedFactor.created_by == str(user_id),
        )
    )
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def persist_wq_simulation(
    db: AsyncSession,
    *,
    user_id: UUID,
    expression: str,
    sim: dict,
    edit_candidate_id: str | None = None,
    seed_factor_id: str | None = None,
    region: str = "USA",
    universe: str = "TOP3000",
    delay: int = 1,
    decay: int = 0,
    neutralization: str = "SUBINDUSTRY",
    truncation: float = 0.08,
    account: str = "primary",
) -> WQSimulationRun:
    ok = bool(sim.get("ok"))
    row = WQSimulationRun(
        id=_new_wsim_id(),
        created_by=str(user_id),
        edit_candidate_id=edit_candidate_id,
        seed_factor_id=seed_factor_id,
        expression=expression.strip(),
        region=region,
        universe=universe,
        delay=delay,
        decay=decay,
        neutralization=neutralization,
        truncation=truncation,
        account=account,
        ok=ok,
        error_message=(None if ok else (sim.get("error") or "")[:4000]),
        alpha_id=(sim.get("alpha_id") if ok else None),
        simulation_id=(sim.get("simulation_id") if ok else None),
        is_metrics=(sim.get("is") if ok else None),
        oos_metrics=(sim.get("oos") if ok else None),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


async def get_wq_simulation_owned(
    db: AsyncSession,
    *,
    user_id: UUID,
    run_id: str,
) -> WQSimulationRun | None:
    res = await db.execute(select(WQSimulationRun).where(WQSimulationRun.id == run_id))
    row = res.scalar_one_or_none()
    if not row or row.created_by != str(user_id):
        return None
    return row
