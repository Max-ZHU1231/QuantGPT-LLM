"""M1-4 — WQ expression gate REST."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit_log import write_audit_event
from ..auth import get_current_user
from ..db import get_db
from ..expression_gate import validate_wq, validate_wq_full
from ..models import User

router = APIRouter(prefix="/api/v1/expressions", tags=["expressions"])


class ValidateWQRequest(BaseModel):
    expression: str = Field(..., min_length=1)
    strict_whitelist: bool = False


class ValidateWQFullRequest(BaseModel):
    expression: str = Field(..., min_length=1)
    strict_whitelist: bool = False
    max_expression_length: int | None = None
    max_paren_depth: int | None = None


@router.post("/validate_wq")
async def validate_wq_expression(
    payload: ValidateWQRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = validate_wq(payload.expression, strict_whitelist=payload.strict_whitelist)
    await write_audit_event(
        db,
        user_id=user.id,
        event_type="validate",
        entity_type="expression",
        entity_id="wq_gate",
        payload={
            "valid": result.get("valid"),
            "strict_whitelist": payload.strict_whitelist,
            "parse_error": result.get("parse_error"),
            "whitelist_violations": result.get("whitelist_violations"),
        },
    )
    return {"status": "success", "validation": result}


@router.post("/validate_wq_full")
async def validate_wq_expression_full(
    payload: ValidateWQFullRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = validate_wq_full(
        payload.expression,
        strict_whitelist=payload.strict_whitelist,
        max_length=payload.max_expression_length,
        max_paren_depth=payload.max_paren_depth,
    )
    await write_audit_event(
        db,
        user_id=user.id,
        event_type="validate",
        entity_type="expression",
        entity_id="wq_gate_full",
        payload={
            "valid": result.get("valid"),
            "failure_categories": result.get("failure_categories"),
            "complexity": result.get("complexity"),
            "strict_whitelist": payload.strict_whitelist,
        },
    )
    return {"status": "success", "validation": result}
