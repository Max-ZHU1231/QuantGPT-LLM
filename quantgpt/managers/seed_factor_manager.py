"""Async SeedFactor persistence — no HTTP layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..seed_models import SeedFactor


def _new_seed_factor_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"sf_{day}_{uuid.uuid4().hex[:8]}"


class SeedFactorManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: UUID,
        name: str,
        expression: str,
        econ_rationale: str,
        market: str,
        universe: str,
        frequency: str,
        factor_type: str | None = None,
        blacklist_operators: list[str] | None = None,
        blacklist_fields: list[str] | None = None,
        attachment_urls: list[str] | None = None,
    ) -> SeedFactor:
        now = datetime.now(timezone.utc)
        entity = SeedFactor(
            id=_new_seed_factor_id(),
            name=name.strip(),
            expression=expression.strip(),
            econ_rationale=econ_rationale.strip(),
            market=market.strip(),
            universe=universe.strip(),
            frequency=frequency.strip(),
            factor_type=(factor_type.strip() if factor_type else None),
            blacklist_operators=blacklist_operators if blacklist_operators is not None else [],
            blacklist_fields=blacklist_fields if blacklist_fields is not None else [],
            attachment_urls=attachment_urls if attachment_urls is not None else [],
            version=1,
            created_by=str(user_id),
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def get_owned(self, *, user_id: UUID, seed_factor_id: str) -> SeedFactor | None:
        result = await self.db.execute(
            select(SeedFactor).where(
                SeedFactor.id == seed_factor_id,
                SeedFactor.created_by == str(user_id),
            )
        )
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        *,
        user_id: UUID,
        market: str | None = None,
        universe: str | None = None,
        status: str | None = "active",
    ) -> list[SeedFactor]:
        q = select(SeedFactor).where(SeedFactor.created_by == str(user_id))
        if market:
            q = q.where(SeedFactor.market == market)
        if universe:
            q = q.where(SeedFactor.universe == universe)
        if status:
            q = q.where(SeedFactor.status == status)
        q = q.order_by(SeedFactor.created_at.desc())
        result = await self.db.execute(q)
        return list(result.scalars().all())
