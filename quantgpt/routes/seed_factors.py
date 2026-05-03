"""Seed factor routes — anchor-factor intake (M1-2)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..managers.seed_factor_manager import SeedFactorManager
from ..models import User
from ..seed_models import SeedFactor

router = APIRouter(prefix="/api/v1/seed_factors", tags=["seed_factors"])


class SeedFactorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    expression: str = Field(..., min_length=1)
    econ_rationale: str = Field(..., min_length=50)
    market: str = Field(..., min_length=1, max_length=50)
    universe: str = Field(..., min_length=1, max_length=50)
    frequency: str = Field(..., min_length=1, max_length=20)
    factor_type: str | None = Field(None, max_length=100)
    blacklist_operators: list[str] = Field(default_factory=list)
    blacklist_fields: list[str] = Field(default_factory=list)
    attachment_urls: list[str] = Field(default_factory=list)


def _to_detail(f: SeedFactor) -> dict:
    return {
        "id": f.id,
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
        "version": f.version,
        "created_by": f.created_by,
        "status": f.status,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _to_summary(f: SeedFactor) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "expression": f.expression,
        "market": f.market,
        "universe": f.universe,
        "frequency": f.frequency,
        "status": f.status,
        "version": f.version,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.post("", status_code=201)
async def create_seed_factor(
    payload: SeedFactorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mgr = SeedFactorManager(db)
    try:
        factor = await mgr.create(
            user_id=user.id,
            name=payload.name,
            expression=payload.expression,
            econ_rationale=payload.econ_rationale,
            market=payload.market,
            universe=payload.universe,
            frequency=payload.frequency,
            factor_type=payload.factor_type,
            blacklist_operators=payload.blacklist_operators,
            blacklist_fields=payload.blacklist_fields,
            attachment_urls=payload.attachment_urls,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="因子名称已存在") from None
    await db.refresh(factor)
    return {"status": "success", "seed_factor_id": factor.id, "factor": _to_detail(factor)}


@router.get("/{seed_factor_id}")
async def get_seed_factor(
    seed_factor_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mgr = SeedFactorManager(db)
    factor = await mgr.get_owned(user_id=user.id, seed_factor_id=seed_factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="Seed factor not found")
    return _to_detail(factor)


@router.get("")
async def list_seed_factors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    market: str | None = None,
    universe: str | None = None,
    status: str | None = "active",
):
    mgr = SeedFactorManager(db)
    factors = await mgr.list_owned(
        user_id=user.id,
        market=market,
        universe=universe,
        status=status,
    )
    return {
        "status": "success",
        "total": len(factors),
        "factors": [_to_summary(f) for f in factors],
    }
