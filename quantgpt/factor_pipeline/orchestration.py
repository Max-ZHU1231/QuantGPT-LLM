"""路线图 P0 — gate → simulate → decide 编排；路线图 P1 — 可选结构化审计快照。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..audit_log import write_audit_event
from .admission_persist import admission_decision_detail, persist_admission_decision_for_run
from .gated_run import run_gated_wq_pipeline
from .pipeline_dto import wq_run_summary_dict


async def run_gate_simulate_decide(
    db: AsyncSession,
    *,
    user_id: UUID,
    expression: str,
    seed_factor_id: str | None = None,
    edit_candidate_id: str | None = None,
    rule_profile_id: str | None = None,
    strict_whitelist: bool = False,
    max_expression_length: int | None = None,
    max_paren_depth: int | None = None,
    region: str = "USA",
    universe: str = "TOP3000",
    delay: int = 1,
    decay: int = 0,
    neutralization: str = "SUBINDUSTRY",
    truncation: float = 0.08,
    account: str = "primary",
    mock: bool = False,
    write_validation_audit: bool = True,
) -> dict[str, Any]:
    """一键流水线：复用 gated simulate + 入库决策。"""
    gated = await run_gated_wq_pipeline(
        db,
        user_id=user_id,
        expression=expression,
        seed_factor_id=seed_factor_id,
        edit_candidate_id=edit_candidate_id,
        strict_whitelist=strict_whitelist,
        max_expression_length=max_expression_length,
        max_paren_depth=max_paren_depth,
        region=region,
        universe=universe,
        delay=delay,
        decay=decay,
        neutralization=neutralization,
        truncation=truncation,
        account=account,
        mock=mock,
    )

    err = gated.get("error")
    if err == "seed_factor_not_found":
        return {"flow_status": "client_error", "http_status": 404, "detail": "Seed factor not found"}
    if err == "edit_candidate_not_found":
        return {"flow_status": "client_error", "http_status": 404, "detail": "Edit candidate not found"}

    gate = gated["gate"]
    job = gated["job"]

    if not gate.get("valid"):
        return {
            "flow_status": "gate_failed",
            "http_status": 200,
            "job": job,
            "gate": gate,
            "simulation": None,
            "decision": None,
            "raw_simulation": None,
        }

    if gated.get("status") == "simulate_failed":
        return {
            "flow_status": "simulate_failed",
            "http_status": 200,
            "job": job,
            "gate": gate,
            "simulation": None,
            "decision": None,
            "raw_simulation": None,
            "error": gated.get("error"),
        }

    row = gated.get("wq_simulation_run")
    if row is None:
        return {
            "flow_status": "simulate_missing",
            "http_status": 500,
            "job": job,
            "gate": gate,
            "simulation": None,
            "decision": None,
            "raw_simulation": None,
        }

    try:
        decision_row = await persist_admission_decision_for_run(
            db,
            user_id=user_id,
            run=row,
            edit_candidate_id=edit_candidate_id,
            rule_profile_id=rule_profile_id,
        )
    except ValueError as e:
        if str(e) == "RULE_PROFILE_NOT_FOUND":
            return {
                "flow_status": "client_error",
                "http_status": 404,
                "detail": "Rule profile not found",
                "job": job,
                "gate": gate,
                "simulation": wq_run_summary_dict(row),
            }
        raise

    if write_validation_audit:
        await write_audit_event(
            db,
            user_id=user_id,
            event_type="pipeline_validation_bundle",
            entity_type="wq_simulation_run",
            entity_id=row.id,
            payload={
                "gate_failure_categories": gate.get("failure_categories"),
                "complexity": gate.get("complexity"),
                "semantic_mvp": gate.get("semantic_mvp"),
                "pipeline_job_id": job.get("id"),
            },
        )

    await write_audit_event(
        db,
        user_id=user_id,
        event_type="pipeline_one_click_complete",
        entity_type="pipeline_run_job",
        entity_id=job["id"],
        payload={
            "wq_simulation_run_id": row.id,
            "admission_decision_id": decision_row.id,
        },
    )

    return {
        "flow_status": "success",
        "http_status": 201,
        "job": job,
        "gate": gate,
        "simulation": wq_run_summary_dict(row),
        "decision": admission_decision_detail(decision_row),
        "raw_simulation": gated.get("raw_simulation"),
    }
