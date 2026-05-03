"""Audit trail query (模板 §6.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..seed_models import AuditTrail

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _trail_row(t: AuditTrail) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "event_type": t.event_type,
        "entity_type": t.entity_type,
        "entity_id": t.entity_id,
        "payload": t.payload,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/trails")
async def list_audit_trails(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
):
    limit = min(max(limit, 1), 500)
    q = select(AuditTrail).where(AuditTrail.user_id == str(user.id))
    if entity_type:
        q = q.where(AuditTrail.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditTrail.entity_id == entity_id)
    q = q.order_by(AuditTrail.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = list(res.scalars().all())
    return {"status": "success", "total": len(rows), "trails": [_trail_row(t) for t in rows]}
