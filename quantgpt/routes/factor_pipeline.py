"""因子流水线 — 门禁编排、规则画像、溯源聚合、轻量运维指标（模板 §7）。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit_log import write_audit_event
from ..auth import get_current_user
from ..db import get_db
from ..expression_gate import validate_wq_full
from ..managers.pipeline_rule_profile_manager import PipelineRuleProfileManager
from ..managers.seed_factor_manager import SeedFactorManager
from ..models import User
from ..seed_models import (
    AdmissionDecision,
    AuditTrail,
    GenerationBatch,
    PipelineRunJob,
    PipelineRuleProfile,
    SeedFactorRevision,
    WQSimulationRun,
)
from ..wq_pipeline import (
    persist_wq_simulation,
    verify_edit_candidate_owned,
    wq_mock_simulate_enabled,
    wq_simulate_metrics_sync,
)

router = APIRouter(prefix="/api/v1/factor_pipeline", tags=["factor_pipeline"])


def _new_job_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"prun_{day}_{uuid.uuid4().hex[:8]}"


def _wq_run_summary(row: WQSimulationRun) -> dict:
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


def _profile_dict(p: PipelineRuleProfile) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "profile_kind": p.profile_kind,
        "market": p.market,
        "universe": p.universe,
        "frequency": p.frequency,
        "rules_json": p.rules_json or {},
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _job_dict(j: PipelineRunJob) -> dict[str, Any]:
    return {
        "id": j.id,
        "status": j.status,
        "expression": j.expression,
        "gate_passed": j.gate_passed,
        "gate_report": j.gate_report,
        "wq_simulation_run_id": j.wq_simulation_run_id,
        "seed_factor_id": j.seed_factor_id,
        "edit_candidate_id": j.edit_candidate_id,
        "error_message": j.error_message,
        "mock_used": j.mock_used,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
    }


class GatedSimulateRequest(BaseModel):
    expression: str = Field(..., min_length=1)
    seed_factor_id: str | None = None
    edit_candidate_id: str | None = None
    region: str = Field(default="USA", max_length=20)
    universe: str = Field(default="TOP3000", max_length=40)
    delay: int = Field(default=1, ge=0, le=10)
    decay: int = Field(default=0, ge=0)
    neutralization: str = Field(default="SUBINDUSTRY", max_length=40)
    truncation: float = Field(default=0.08, ge=0.0, le=1.0)
    account: str = Field(default="primary", max_length=20)
    mock: bool = Field(default=False)
    strict_whitelist: bool = False
    max_expression_length: int | None = None
    max_paren_depth: int | None = None


@router.post("/simulate/gated", status_code=201)
async def gated_simulate(
    payload: GatedSimulateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.seed_factor_id:
        sm = SeedFactorManager(db)
        sf = await sm.get_owned(user_id=user.id, seed_factor_id=payload.seed_factor_id)
        if not sf:
            raise HTTPException(status_code=404, detail="Seed factor not found")
    if payload.edit_candidate_id:
        cand = await verify_edit_candidate_owned(
            db, user_id=user.id, candidate_id=payload.edit_candidate_id
        )
        if not cand:
            raise HTTPException(status_code=404, detail="Edit candidate not found")

    now = datetime.now(timezone.utc)
    job = PipelineRunJob(
        id=_new_job_id(),
        created_by=str(user.id),
        seed_factor_id=payload.seed_factor_id,
        edit_candidate_id=payload.edit_candidate_id,
        expression=payload.expression.strip(),
        gate_passed=False,
        gate_report=None,
        wq_simulation_run_id=None,
        status="queued",
        error_message=None,
        mock_used=False,
        created_at=now,
        completed_at=None,
    )
    db.add(job)
    await db.flush()

    gate = validate_wq_full(
        payload.expression,
        strict_whitelist=payload.strict_whitelist,
        max_length=payload.max_expression_length,
        max_paren_depth=payload.max_paren_depth,
    )

    if not gate.get("valid"):
        job.status = "failed"
        job.gate_passed = False
        job.gate_report = gate
        job.error_message = "expression_gate_failed"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await write_audit_event(
            db,
            user_id=user.id,
            event_type="pipeline_gated_simulate",
            entity_type="pipeline_run_job",
            entity_id=job.id,
            payload={"phase": "gate", "passed": False},
        )
        return {"status": "success", "job": _job_dict(job), "gate": gate, "simulation": None}

    job.gate_passed = True
    job.gate_report = gate
    job.status = "running"
    await db.flush()

    use_mock = payload.mock or wq_mock_simulate_enabled()
    job.mock_used = use_mock
    await db.flush()

    try:
        sim = await asyncio.to_thread(
            lambda: wq_simulate_metrics_sync(
                payload.expression,
                region=payload.region,
                universe=payload.universe,
                delay=payload.delay,
                decay=payload.decay,
                neutralization=payload.neutralization,
                truncation=payload.truncation,
                account=payload.account,
                mock=use_mock,
            ),
        )
        row = await persist_wq_simulation(
            db,
            user_id=user.id,
            expression=payload.expression,
            sim=sim,
            edit_candidate_id=payload.edit_candidate_id,
            seed_factor_id=payload.seed_factor_id,
            region=payload.region,
            universe=payload.universe,
            delay=payload.delay,
            decay=payload.decay,
            neutralization=payload.neutralization,
            truncation=payload.truncation,
            account=payload.account,
        )
        job.wq_simulation_run_id = row.id
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await write_audit_event(
            db,
            user_id=user.id,
            event_type="pipeline_gated_simulate",
            entity_type="pipeline_run_job",
            entity_id=job.id,
            payload={"phase": "simulate", "wq_simulation_run_id": row.id, "mock": use_mock},
        )
        return {
            "status": "success",
            "job": _job_dict(job),
            "gate": gate,
            "simulation": _wq_run_summary(row),
            "raw": sim,
        }
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)[:4000]
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await write_audit_event(
            db,
            user_id=user.id,
            event_type="pipeline_gated_simulate",
            entity_type="pipeline_run_job",
            entity_id=job.id,
            payload={"phase": "simulate", "error": job.error_message},
        )
        return {
            "status": "simulate_failed",
            "job": _job_dict(job),
            "gate": gate,
            "simulation": None,
            "error": job.error_message,
        }


@router.get("/trace/{seed_factor_id}")
async def trace_seed_factor(
    seed_factor_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sm = SeedFactorManager(db)
    seed = await sm.get_owned(user_id=user.id, seed_factor_id=seed_factor_id)
    if not seed:
        raise HTTPException(status_code=404, detail="Seed factor not found")

    uid = str(user.id)

    rev_res = await db.execute(
        select(SeedFactorRevision)
        .where(SeedFactorRevision.seed_factor_id == seed_factor_id)
        .order_by(SeedFactorRevision.created_at.desc())
        .limit(200)
    )
    revisions = list(rev_res.scalars().all())

    batch_res = await db.execute(
        select(GenerationBatch)
        .where(GenerationBatch.seed_factor_id == seed_factor_id)
        .order_by(GenerationBatch.created_at.desc())
        .limit(100)
    )
    batches = list(batch_res.scalars().all())

    run_res = await db.execute(
        select(WQSimulationRun)
        .where(
            WQSimulationRun.seed_factor_id == seed_factor_id,
            WQSimulationRun.created_by == uid,
        )
        .order_by(WQSimulationRun.created_at.desc())
        .limit(80)
    )
    runs = list(run_res.scalars().all())
    run_ids = [r.id for r in runs]

    decisions: list[AdmissionDecision] = []
    if run_ids:
        dec_res = await db.execute(
            select(AdmissionDecision)
            .where(
                AdmissionDecision.wq_simulation_run_id.in_(run_ids),
                AdmissionDecision.created_by == uid,
            )
            .order_by(AdmissionDecision.created_at.desc())
        )
        decisions = list(dec_res.scalars().all())

    batch_ids = [b.id for b in batches]
    decision_ids = [d.id for d in decisions]

    conds = [
        and_(AuditTrail.entity_type == "seed_factor", AuditTrail.entity_id == seed_factor_id),
    ]
    if batch_ids:
        conds.append(
            and_(AuditTrail.entity_type == "generation_batch", AuditTrail.entity_id.in_(batch_ids))
        )
    if run_ids:
        conds.append(
            and_(AuditTrail.entity_type == "wq_simulation_run", AuditTrail.entity_id.in_(run_ids))
        )
    if decision_ids:
        conds.append(
            and_(AuditTrail.entity_type == "admission_decision", AuditTrail.entity_id.in_(decision_ids))
        )

    audit_res = await db.execute(
        select(AuditTrail)
        .where(AuditTrail.user_id == uid, or_(*conds))
        .order_by(AuditTrail.created_at.desc())
        .limit(400)
    )
    audits = list(audit_res.scalars().all())

    def rev_dict(r: SeedFactorRevision) -> dict[str, Any]:
        return {
            "id": r.id,
            "seed_factor_id": r.seed_factor_id,
            "version_after": r.version_after,
            "snapshot": r.snapshot,
            "edited_by": r.edited_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    def batch_summary(b: GenerationBatch) -> dict[str, Any]:
        return {
            "id": b.id,
            "generation_status": b.generation_status,
            "candidate_count": b.candidate_count,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }

    def decision_summary(d: AdmissionDecision) -> dict[str, Any]:
        return {
            "id": d.id,
            "decision": d.decision,
            "wq_simulation_run_id": d.wq_simulation_run_id,
            "composite_score": d.composite_score,
            "human_approval_status": d.human_approval_status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }

    return {
        "status": "success",
        "seed_factor_id": seed_factor_id,
        "revisions": [rev_dict(r) for r in revisions],
        "generation_batches": [batch_summary(b) for b in batches],
        "wq_simulation_runs": [_wq_run_summary(r) for r in runs],
        "admission_decisions": [decision_summary(d) for d in decisions],
        "audit_trails": [
            {
                "id": a.id,
                "event_type": a.event_type,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "payload": a.payload,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in audits
        ],
    }


@router.get("/metrics/summary")
async def pipeline_metrics_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = 7,
):
    days = min(max(days, 1), 90)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    uid = str(user.id)

    jobs_total = await db.scalar(
        select(func.count()).select_from(PipelineRunJob).where(
            PipelineRunJob.created_by == uid,
            PipelineRunJob.created_at >= since,
        )
    )
    jobs_completed = await db.scalar(
        select(func.count()).select_from(PipelineRunJob).where(
            PipelineRunJob.created_by == uid,
            PipelineRunJob.created_at >= since,
            PipelineRunJob.status == "completed",
        )
    )
    gate_failed = await db.scalar(
        select(func.count()).select_from(PipelineRunJob).where(
            PipelineRunJob.created_by == uid,
            PipelineRunJob.created_at >= since,
            PipelineRunJob.gate_passed == False,  # noqa: E712
            PipelineRunJob.status == "failed",
        )
    )

    sim_total = await db.scalar(
        select(func.count()).select_from(WQSimulationRun).where(
            WQSimulationRun.created_by == uid,
            WQSimulationRun.created_at >= since,
        )
    )

    validate_events = await db.scalar(
        select(func.count()).select_from(AuditTrail).where(
            AuditTrail.user_id == uid,
            AuditTrail.created_at >= since,
            AuditTrail.event_type == "validate",
        )
    )

    return {
        "status": "success",
        "window_days": days,
        "pipeline_run_jobs_total": int(jobs_total or 0),
        "pipeline_run_jobs_completed": int(jobs_completed or 0),
        "pipeline_gate_failed_jobs": int(gate_failed or 0),
        "wq_simulation_runs_total": int(sim_total or 0),
        "audit_validate_events": int(validate_events or 0),
    }


class RuleProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    profile_kind: str = Field(default="formal", max_length=32)
    market: str | None = Field(None, max_length=50)
    universe: str | None = Field(None, max_length=50)
    frequency: str | None = Field(None, max_length=20)
    rules_json: dict[str, Any] = Field(default_factory=dict)


class RuleProfilePatch(BaseModel):
    name: str | None = Field(None, max_length=128)
    profile_kind: str | None = Field(None, max_length=32)
    market: str | None = Field(None, max_length=50)
    universe: str | None = Field(None, max_length=50)
    frequency: str | None = Field(None, max_length=20)
    rules_json: dict[str, Any] | None = None


@router.get("/rules/profiles")
async def list_rule_profiles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
):
    mgr = PipelineRuleProfileManager(db)
    rows = await mgr.list_owned(user_id=user.id, limit=limit)
    return {"status": "success", "total": len(rows), "profiles": [_profile_dict(p) for p in rows]}


@router.post("/rules/profiles", status_code=201)
async def create_rule_profile(
    payload: RuleProfileCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mgr = PipelineRuleProfileManager(db)
    try:
        row = await mgr.create(
            user_id=user.id,
            name=payload.name,
            profile_kind=payload.profile_kind,
            market=payload.market,
            universe=payload.universe,
            frequency=payload.frequency,
            rules_json=payload.rules_json,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="rule_profile_name_conflict") from None
    await write_audit_event(
        db,
        user_id=user.id,
        event_type="create_rule_profile",
        entity_type="pipeline_rule_profile",
        entity_id=row.id,
        payload={"name": row.name},
    )
    return {"status": "success", "profile": _profile_dict(row)}


@router.get("/rules/profiles/{profile_id}")
async def get_rule_profile(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mgr = PipelineRuleProfileManager(db)
    row = await mgr.get_owned(user_id=user.id, profile_id=profile_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rule profile not found")
    return {"status": "success", "profile": _profile_dict(row)}


@router.patch("/rules/profiles/{profile_id}")
async def patch_rule_profile(
    profile_id: str,
    payload: RuleProfilePatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mgr = PipelineRuleProfileManager(db)
    try:
        row = await mgr.update_owned(
            user_id=user.id,
            profile_id=profile_id,
            name=payload.name,
            profile_kind=payload.profile_kind,
            market=payload.market,
            universe=payload.universe,
            frequency=payload.frequency,
            rules_json=payload.rules_json,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="rule_profile_name_conflict") from None
    if not row:
        raise HTTPException(status_code=404, detail="Rule profile not found")
    await write_audit_event(
        db,
        user_id=user.id,
        event_type="update_rule_profile",
        entity_type="pipeline_rule_profile",
        entity_id=row.id,
        payload={"name": row.name},
    )
    return {"status": "success", "profile": _profile_dict(row)}
