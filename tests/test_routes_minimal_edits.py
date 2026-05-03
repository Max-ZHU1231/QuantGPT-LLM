"""Integration tests for minimal_edits routes (M1-3)."""

import json
import uuid

import pytest
from httpx import AsyncClient

from quantgpt.auth import create_access_token, hash_password
from quantgpt.models import User

pytestmark = pytest.mark.asyncio

RATIONALE_50 = "测" * 50


def _seed_payload(name: str = "最小改动种子", expression: str = "rank(close/ts_mean(close,20))"):
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


def _fake_llm_ok():
    return json.dumps(
        {
            "candidates": [
                {
                    "expression": "rank(close/ts_mean(close,30))",
                    "edit_summary": {
                        "edit_direction": "conservative",
                        "edits": [{"type": "param_tuning", "detail": "window 20→30"}],
                    },
                    "expected_impact": {"sharpe_delta": "+0.05", "confidence": "medium"},
                    "core_logic_preserved": True,
                    "deviation_explanation": None,
                }
            ]
        },
        ensure_ascii=False,
    )


@pytest.fixture
def deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key-for-ci")


@pytest.fixture
def mock_deepseek_chat(monkeypatch):
    import quantgpt.factor_pipeline.minimal_edit_generator as mig

    monkeypatch.setattr(mig, "_deepseek_chat", lambda _messages: _fake_llm_ok())


class TestMinimalEditsAuth:
    async def test_generate_without_token_returns_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/minimal_edits/generate",
            json={
                "seed_factor_id": "sf_x",
                "target_gap": {"metric": "sharpe", "current": 1.0, "target": 1.5, "constraint": ""},
            },
        )
        assert resp.status_code == 401


class TestMinimalEditsGenerate:
    async def test_generate_success_and_get_batch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        deepseek_key,
        mock_deepseek_chat,
    ):
        cr = await client.post("/api/v1/seed_factors", json=_seed_payload(), headers=auth_headers)
        assert cr.status_code == 201
        sf_id = cr.json()["seed_factor_id"]

        gen = await client.post(
            "/api/v1/minimal_edits/generate",
            headers=auth_headers,
            json={
                "seed_factor_id": sf_id,
                "target_gap": {
                    "metric": "sharpe",
                    "current": 1.2,
                    "target": 1.6,
                    "constraint": "keep turnover under 0.4",
                },
                "knowledge_base": {"verified_rules": [], "failed_paths": []},
            },
        )
        assert gen.status_code == 201
        body = gen.json()
        assert body["status"] == "success"
        batch = body["batch"]
        assert batch["generation_status"] == "completed"
        assert batch["candidate_count"] == 1
        assert batch["seed_factor_id"] == sf_id
        bid = batch["batch_id"]

        got = await client.get(f"/api/v1/minimal_edits/batches/{bid}", headers=auth_headers)
        assert got.status_code == 200
        gbody = got.json()
        assert gbody["batch"]["batch_id"] == bid
        assert len(gbody["candidates"]) == 1
        assert "rank(close/ts_mean(close,30))" in gbody["candidates"][0]["expression"]

    async def test_generate_seed_not_found_404(self, client: AsyncClient, auth_headers: dict, deepseek_key):
        resp = await client.post(
            "/api/v1/minimal_edits/generate",
            headers=auth_headers,
            json={
                "seed_factor_id": "sf_does_not_exist",
                "target_gap": {"metric": "sharpe", "current": 1.0, "target": 2.0, "constraint": ""},
            },
        )
        assert resp.status_code == 404

    async def test_generate_without_api_key_503(self, client: AsyncClient, auth_headers: dict, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        cr = await client.post("/api/v1/seed_factors", json=_seed_payload(name="K503"), headers=auth_headers)
        sf_id = cr.json()["seed_factor_id"]
        resp = await client.post(
            "/api/v1/minimal_edits/generate",
            headers=auth_headers,
            json={
                "seed_factor_id": sf_id,
                "target_gap": {"metric": "sharpe", "current": 1.0, "target": 2.0, "constraint": ""},
            },
        )
        assert resp.status_code == 503

    async def test_failed_generation_persists_batch(
        self,
        client: AsyncClient,
        auth_headers: dict,
        deepseek_key,
        monkeypatch,
    ):
        import quantgpt.factor_pipeline.minimal_edit_generator as mig

        monkeypatch.setattr(mig, "_deepseek_chat", lambda _messages: "not json")

        cr = await client.post("/api/v1/seed_factors", json=_seed_payload(name="失败批次"), headers=auth_headers)
        sf_id = cr.json()["seed_factor_id"]
        gen = await client.post(
            "/api/v1/minimal_edits/generate",
            headers=auth_headers,
            json={
                "seed_factor_id": sf_id,
                "target_gap": {"metric": "sharpe", "current": 1.0, "target": 2.0, "constraint": ""},
            },
        )
        assert gen.status_code == 201
        batch = gen.json()["batch"]
        assert batch["generation_status"] == "failed"
        assert batch["error_message"]

        got = await client.get(f"/api/v1/minimal_edits/batches/{batch['batch_id']}", headers=auth_headers)
        assert got.status_code == 200
        assert got.json()["candidates"] == []


class TestMinimalEditsIsolation:
    async def test_other_user_cannot_read_batch(self, engine, monkeypatch):
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        import quantgpt.factor_pipeline.minimal_edit_generator as mig
        from quantgpt.api_server import app
        from quantgpt.db import get_db

        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-isolation")
        monkeypatch.setattr(mig, "_deepseek_chat", lambda _messages: _fake_llm_ok())

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        u1_id, u2_id = uuid.uuid4(), uuid.uuid4()
        async with factory() as session:
            session.add_all([
                User(id=u1_id, email="me_batch@test.com", password_hash=hash_password("pw"), is_active=True),
                User(id=u2_id, email="other_batch@test.com", password_hash=hash_password("pw"), is_active=True),
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
        transport = ASGITransport(app=app)
        headers1 = {"Authorization": f"Bearer {create_access_token(u1_id, 'me_batch@test.com')}"}
        headers2 = {"Authorization": f"Bearer {create_access_token(u2_id, 'other_batch@test.com')}"}

        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                cr = await ac.post("/api/v1/seed_factors", json=_seed_payload(name="隔离批次"), headers=headers1)
                sf_id = cr.json()["seed_factor_id"]
                gen = await ac.post(
                    "/api/v1/minimal_edits/generate",
                    headers=headers1,
                    json={
                        "seed_factor_id": sf_id,
                        "target_gap": {"metric": "sharpe", "current": 1.0, "target": 2.0, "constraint": ""},
                    },
                )
                assert gen.status_code == 201
                bid = gen.json()["batch"]["batch_id"]

                deny = await ac.get(f"/api/v1/minimal_edits/batches/{bid}", headers=headers2)
                assert deny.status_code == 404
        finally:
            app.dependency_overrides.clear()
