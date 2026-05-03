"""Integration tests for seed_factors routes."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from quantgpt.auth import create_access_token, hash_password
from quantgpt.models import User

pytestmark = pytest.mark.asyncio

# pydantic min_length=50 counts Unicode code points
RATIONALE_50 = "测" * 50


def _payload(name: str = "锚因子测试A", expression: str = "rank(close/ts_mean(close,20))"):
    return {
        "name": name,
        "expression": expression,
        "econ_rationale": RATIONALE_50,
        "market": "China",
        "universe": "hs300",
        "frequency": "daily",
        "factor_type": "momentum",
        "blacklist_operators": [],
        "blacklist_fields": [],
        "attachment_urls": [],
    }


class TestSeedFactorsAuth:
    async def test_create_without_token_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/seed_factors", json=_payload())
        assert resp.status_code == 401


class TestSeedFactorsCrud:
    async def test_create_list_get(self, client: AsyncClient, auth_headers: dict, test_user: User):
        resp = await client.post("/api/v1/seed_factors", json=_payload(), headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert data["seed_factor_id"].startswith("sf_")
        sf_id = data["seed_factor_id"]
        assert data["factor"]["created_by"] == str(test_user.id)

        lst = await client.get("/api/v1/seed_factors", headers=auth_headers)
        assert lst.status_code == 200
        body = lst.json()
        assert body["total"] >= 1
        ids = {f["id"] for f in body["factors"]}
        assert sf_id in ids

        one = await client.get(f"/api/v1/seed_factors/{sf_id}", headers=auth_headers)
        assert one.status_code == 200
        assert one.json()["id"] == sf_id
        assert one.json()["expression"] == "rank(close/ts_mean(close,20))"

    async def test_short_rationale_422(self, client: AsyncClient, auth_headers: dict):
        pl = _payload()
        pl["econ_rationale"] = "太短"
        resp = await client.post("/api/v1/seed_factors", json=pl, headers=auth_headers)
        assert resp.status_code == 422

    async def test_duplicate_name_409(self, client: AsyncClient, auth_headers: dict):
        name = "唯一名称因子X"
        r1 = await client.post("/api/v1/seed_factors", json=_payload(name=name), headers=auth_headers)
        assert r1.status_code == 201
        r2 = await client.post("/api/v1/seed_factors", json=_payload(name=name), headers=auth_headers)
        assert r2.status_code == 409

    async def test_other_user_cannot_read(self, client: AsyncClient, engine):
        """Same DB engine as client — isolation by created_by."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from quantgpt.api_server import app
        from quantgpt.db import get_db

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        u1_id, u2_id = uuid.uuid4(), uuid.uuid4()
        email1, email2 = "seed_a@test.com", "seed_b@test.com"
        async with factory() as session:
            session.add_all([
                User(id=u1_id, email=email1, password_hash=hash_password("pw"), is_active=True),
                User(id=u2_id, email=email2, password_hash=hash_password("pw"), is_active=True),
            ])
            await session.commit()

        async def _override_get_db():
            async with factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_get_db
        try:
            h1 = {"Authorization": f"Bearer {create_access_token(u1_id, email1)}"}
            h2 = {"Authorization": f"Bearer {create_access_token(u2_id, email2)}"}
            r = await client.post("/api/v1/seed_factors", json=_payload(name="仅用户一可见"), headers=h1)
            assert r.status_code == 201
            sf_id = r.json()["seed_factor_id"]

            r404 = await client.get(f"/api/v1/seed_factors/{sf_id}", headers=h2)
            assert r404.status_code == 404
        finally:
            app.dependency_overrides.clear()
