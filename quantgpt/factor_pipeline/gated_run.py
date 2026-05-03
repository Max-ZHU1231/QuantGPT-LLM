"""路线图 P0 — gate → simulate → persist WQ run（PipelineRunJob）；供 REST gated 与一键编排复用。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..audit_log import write_audit_event
from ..expression_gate import validate_wq_full
from ..managers.seed_factor_manager import SeedFactorManager
from ..seed_models import PipelineRunJob
from ..wq_pipeline import (
    persist_wq_simulation,
    verify_edit_candidate_owned,
    wq_mock_simulate_enabled,
    wq_simulate_metrics_sync,
)
from .pipeline_dto import pipeline_job_dict, wq_run_summary_dict


def new_pipeline_run_job_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"prun_{day}_{uuid.uuid4().hex[:8]}"


async def run_gated_wq_pipeline(
    db: AsyncSession,
    *,
    user_id: UUID,
    expression: str,
    seed_factor_id: str | None,
    edit_candidate_id: str | None,
    strict_whitelist: bool,
    max_expression_length: int | None,
    max_paren_depth: int | None,
    region: str,
    universe: str,
    delay: int,
    decay: int,
    neutralization: str,
    truncation: float,
    account: str,
    mock: bool,
) -> dict[str, Any]:
    """创建 PipelineRunJob，执行门禁与 simulate；返回 REST 形状字典。"""
    expr = expression.strip()
    if seed_factor_id:
        sm = SeedFactorManager(db)
        sf = await sm.get_owned(user_id=user_id, seed_factor_id=seed_factor_id)
        if not sf:
            return {"error": "seed_factor_not_found", "status_code": 404}

    if edit_candidate_id:
        cand = await verify_edit_candidate_owned(db, user_id=user_id, candidate_id=edit_candidate_id)
        if not cand:
            return {"error": "edit_candidate_not_found", "status_code": 404}

    now = datetime.now(timezone.utc)
    job = PipelineRunJob(
        id=new_pipeline_run_job_id(),
        created_by=str(user_id),
        seed_factor_id=seed_factor_id,
        edit_candidate_id=edit_candidate_id,
        expression=expr,
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
        expr,
        strict_whitelist=strict_whitelist,
        max_length=max_expression_length,
        max_paren_depth=max_paren_depth,
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
            user_id=user_id,
            event_type="pipeline_gated_simulate",
            entity_type="pipeline_run_job",
            entity_id=job.id,
            payload={"phase": "gate", "passed": False},
        )
        return {
            "status": "success",
            "job": pipeline_job_dict(job),
            "gate": gate,
            "simulation": None,
            "raw_simulation": None,
        }

    job.gate_passed = True
    job.gate_report = gate
    job.status = "running"
    await db.flush()

    use_mock = mock or wq_mock_simulate_enabled()
    job.mock_used = use_mock
    await db.flush()

    try:
        sim = await asyncio.to_thread(
            lambda: wq_simulate_metrics_sync(
                expr,
                region=region,
                universe=universe,
                delay=delay,
                decay=decay,
                neutralization=neutralization,
                truncation=truncation,
                account=account,
                mock=use_mock,
            ),
        )
        row = await persist_wq_simulation(
            db,
            user_id=user_id,
            expression=expr,
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
        job.wq_simulation_run_id = row.id
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await write_audit_event(
            db,
            user_id=user_id,
            event_type="pipeline_gated_simulate",
            entity_type="pipeline_run_job",
            entity_id=job.id,
            payload={"phase": "simulate", "wq_simulation_run_id": row.id, "mock": use_mock},
        )
        return {
            "status": "success",
            "job": pipeline_job_dict(job),
            "gate": gate,
            "simulation": wq_run_summary_dict(row),
            "wq_simulation_run": row,
            "raw_simulation": sim,
        }
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)[:4000]
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await write_audit_event(
            db,
            user_id=user_id,
            event_type="pipeline_gated_simulate",
            entity_type="pipeline_run_job",
            entity_id=job.id,
            payload={"phase": "simulate", "error": job.error_message},
        )
        return {
            "status": "simulate_failed",
            "job": pipeline_job_dict(job),
            "gate": gate,
            "simulation": None,
            "wq_simulation_run": None,
            "raw_simulation": None,
            "error": job.error_message,
        }
