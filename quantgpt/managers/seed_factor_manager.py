"""Async SeedFactor persistence — no HTTP layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..seed_models import SeedFactor, SeedFactorRevision


def _new_seed_factor_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"sf_{day}_{uuid.uuid4().hex[:8]}"


def _new_revision_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"sfr_{day}_{uuid.uuid4().hex[:8]}"


def _seed_snapshot(f: SeedFactor) -> dict:
    return {
        "name": f.name,
        "expression": f.expression,
        "econ_rationale": f.econ_rationale,
        "market": f.market,
        "universe": f.universe,
        "frequency": f.frequency,
        "factor_type": f.factor_type,
        "blacklist_operators": f.blacklist_operators or [],
        "blacklist_fields": f.blacklist_fields or [],
        "attachment_urls": f.attachment_urls or [],
        "reference_backtest": f.reference_backtest,
        "status": f.status,
        "version": f.version,
    }


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
        reference_backtest: dict | list | None = None,
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
            reference_backtest=reference_backtest,
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

    async def update_owned_partial(
        self,
        *,
        user_id: UUID,
        seed_factor_id: str,
        name: str | None = None,
        expression: str | None = None,
        econ_rationale: str | None = None,
        market: str | None = None,
        universe: str | None = None,
        frequency: str | None = None,
        factor_type: str | None = None,
        blacklist_operators: list[str] | None = None,
        blacklist_fields: list[str] | None = None,
        attachment_urls: list[str] | None = None,
        reference_backtest: dict | list | None = None,
        status: str | None = None,
    ) -> SeedFactor | None:
        factor = await self.get_owned(user_id=user_id, seed_factor_id=seed_factor_id)
        if not factor:
            return None

        patch_fields = (
            name,
            expression,
            econ_rationale,
            market,
            universe,
            frequency,
            factor_type,
            blacklist_operators,
            blacklist_fields,
            attachment_urls,
            reference_backtest,
            status,
        )
        if not any(v is not None for v in patch_fields):
            return factor

        if name is not None:
            factor.name = name.strip()
        if expression is not None:
            factor.expression = expression.strip()
        if econ_rationale is not None:
            factor.econ_rationale = econ_rationale.strip()
        if market is not None:
            factor.market = market.strip()
        if universe is not None:
            factor.universe = universe.strip()
        if frequency is not None:
            factor.frequency = frequency.strip()
        if factor_type is not None:
            factor.factor_type = factor_type.strip() if factor_type else None
        if blacklist_operators is not None:
            factor.blacklist_operators = blacklist_operators
        if blacklist_fields is not None:
            factor.blacklist_fields = blacklist_fields
        if attachment_urls is not None:
            factor.attachment_urls = attachment_urls
        if reference_backtest is not None:
            factor.reference_backtest = reference_backtest
        if status is not None:
            factor.status = status.strip()

        factor.version = int(factor.version or 1) + 1
        factor.updated_at = datetime.now(timezone.utc)

        rev = SeedFactorRevision(
            id=_new_revision_id(),
            seed_factor_id=factor.id,
            version_after=factor.version,
            snapshot=_seed_snapshot(factor),
            edited_by=str(user_id),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(rev)
        await self.db.flush()
        return factor
