"""流水线 REST / 编排共用 — ORM 行 → 简要 dict（避免 routes 与编排重复）。"""

from __future__ import annotations

from typing import Any

from ..seed_models import PipelineRunJob, WQSimulationRun


def wq_run_summary_dict(row: WQSimulationRun) -> dict[str, Any]:
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


def pipeline_job_dict(j: PipelineRunJob) -> dict[str, Any]:
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
