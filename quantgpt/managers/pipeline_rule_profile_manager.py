"""Async PipelineRuleProfile persistence — scoped by created_by."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..seed_models import PipelineRuleProfile


def _new_profile_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"prp_{day}_{uuid.uuid4().hex[:8]}"


class PipelineRuleProfileManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: UUID,
        name: str,
        profile_kind: str = "formal",
        market: str | None = None,
        universe: str | None = None,
        frequency: str | None = None,
        rules_json: dict[str, Any] | None = None,
    ) -> PipelineRuleProfile:
        now = datetime.now(timezone.utc)
        entity = PipelineRuleProfile(
            id=_new_profile_id(),
            name=name.strip(),
            profile_kind=(profile_kind or "formal").strip(),
            market=market.strip() if market else None,
            universe=universe.strip() if universe else None,
            frequency=frequency.strip() if frequency else None,
            rules_json=dict(rules_json or {}),
            created_by=str(user_id),
            created_at=now,
            updated_at=now,
        )
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def get_owned(self, *, user_id: UUID, profile_id: str) -> PipelineRuleProfile | None:
        res = await self.db.execute(
            select(PipelineRuleProfile).where(
                PipelineRuleProfile.id == profile_id,
                PipelineRuleProfile.created_by == str(user_id),
            )
        )
        return res.scalar_one_or_none()

    async def list_owned(self, *, user_id: UUID, limit: int = 100) -> list[PipelineRuleProfile]:
        q = (
            select(PipelineRuleProfile)
            .where(PipelineRuleProfile.created_by == str(user_id))
            .order_by(PipelineRuleProfile.updated_at.desc())
            .limit(min(limit, 500))
        )
        res = await self.db.execute(q)
        return list(res.scalars().all())

    async def update_owned(
        self,
        *,
        user_id: UUID,
        profile_id: str,
        name: str | None = None,
        profile_kind: str | None = None,
        market: str | None = None,
        universe: str | None = None,
        frequency: str | None = None,
        rules_json: dict[str, Any] | None = None,
    ) -> PipelineRuleProfile | None:
        row = await self.get_owned(user_id=user_id, profile_id=profile_id)
        if not row:
            return None
        if name is not None:
            row.name = name.strip()
        if profile_kind is not None:
            row.profile_kind = profile_kind.strip()
        if market is not None:
            row.market = market.strip() if market else None
        if universe is not None:
            row.universe = universe.strip() if universe else None
        if frequency is not None:
            row.frequency = frequency.strip() if frequency else None
        if rules_json is not None:
            row.rules_json = dict(rules_json)
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return row
