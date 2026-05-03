"""Minimal-edit generation routes (M1-3)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..deepseek_client import factor_llm_config
from ..minimal_edit_generator import generate_minimal_edits_for_seed, get_batch_for_user
from ..models import User

router = APIRouter(prefix="/api/v1/minimal_edits", tags=["minimal_edits"])


class TargetGap(BaseModel):
    metric: str = Field(..., min_length=1)
    current: float
    target: float
    constraint: str = Field("", max_length=4000)


class GenerateMinimalEditsRequest(BaseModel):
    seed_factor_id: str = Field(..., min_length=1)
    target_gap: TargetGap
    knowledge_base: dict | None = None


def _batch_summary(batch) -> dict:
    return {
        "batch_id": batch.id,
        "seed_factor_id": batch.seed_factor_id,
        "generation_status": batch.generation_status,
        "candidate_count": batch.candidate_count,
        "error_message": batch.error_message,
        "model": batch.model,
        "temperature": batch.temperature,
        "prompt_version": batch.prompt_version,
        "target_metric": batch.target_metric,
        "current_value": batch.current_value,
        "target_value": batch.target_value,
        "constraint_description": batch.constraint_description,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
    }


def _candidate_detail(c) -> dict:
    return {
        "id": c.id,
        "batch_id": c.batch_id,
        "seed_factor_id": c.seed_factor_id,
        "expression": c.expression,
        "edit_summary": c.edit_summary,
        "total_edits": c.total_edits,
        "edit_direction": c.edit_direction,
        "expected_sharpe_delta": c.expected_sharpe_delta,
        "expected_ic_delta": c.expected_ic_delta,
        "expected_turnover_delta": c.expected_turnover_delta,
        "impact_confidence": c.impact_confidence,
        "core_logic_preserved": c.core_logic_preserved,
        "deviation_explanation": c.deviation_explanation,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/generate", status_code=201)
async def generate_minimal_edits(
    payload: GenerateMinimalEditsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (factor_llm_config().get("api_key") or "").strip():
        raise HTTPException(status_code=503, detail="DEEPSEEK_API_KEY_NOT_SET")
    try:
        batch = await generate_minimal_edits_for_seed(
            db,
            user_id=user.id,
            seed_factor_id=payload.seed_factor_id,
            target_gap=payload.target_gap.model_dump(),
            knowledge_base=payload.knowledge_base,
        )
    except ValueError as e:
        if str(e) == "SEED_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Seed factor not found") from None
        raise
    return {"status": "success", "batch": _batch_summary(batch)}


@router.get("/batches/{batch_id}")
async def get_minimal_edit_batch(
    batch_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pair = await get_batch_for_user(db, user_id=user.id, batch_id=batch_id)
    if not pair:
        raise HTTPException(status_code=404, detail="Batch not found")
    batch, cands = pair
    ordered = sorted(cands, key=lambda c: (c.created_at is None, c.created_at or batch.created_at))
    return {
        "status": "success",
        "batch": _batch_summary(batch),
        "candidates": [_candidate_detail(c) for c in ordered],
    }
