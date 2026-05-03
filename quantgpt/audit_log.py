"""M1-6 — minimal audit trail for seed / generate / validate / simulate / decide."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .seed_models import AuditTrail


def _new_audit_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"aud_{day}_{uuid.uuid4().hex[:10]}"


async def write_audit_event(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict | None = None,
) -> AuditTrail:
    row = AuditTrail(
        id=_new_audit_id(),
        user_id=str(user_id) if user_id else None,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row
