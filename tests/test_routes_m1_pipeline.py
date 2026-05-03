"""Route tests for M1-4/M1-5/M1-6 REST additions."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from quantgpt.models import User
from quantgpt.seed_models import WQSimulationRun

pytestmark = pytest.mark.asyncio


async def test_validate_wq_requires_auth(client: AsyncClient):
    r = await client.post("/api/v1/expressions/validate_wq", json={"expression": "rank(close)"})
    assert r.status_code == 401


async def test_validate_wq_ok(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/api/v1/expressions/validate_wq",
        headers=auth_headers,
        json={"expression": "rank(close/ts_mean(close,20))", "strict_whitelist": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["validation"]["valid"] is True


@patch("quantgpt.routes.wq_simulations.wq_simulate_metrics_sync")
async def test_wq_simulation_run_persists(mock_sim, client: AsyncClient, auth_headers: dict):
    mock_sim.return_value = {
        "ok": True,
        "alpha_id": "ABC123",
        "simulation_id": "sim_x",
        "is": {"sharpe": 1.1, "fitness": 0.9, "turnover": 0.2},
        "oos": {},
    }
    r = await client.post(
        "/api/v1/wq_simulations/run",
        headers=auth_headers,
        json={"expression": "rank(close)"},
    )
    assert r.status_code == 201
    sim = r.json()["simulation"]
    assert sim["ok"] is True
    assert sim["alpha_id"] == "ABC123"


async def test_admission_decide(client: AsyncClient, auth_headers: dict, test_user: User, engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(
            WQSimulationRun(
                id="wsim_test_adm_1",
                created_by=str(test_user.id),
                edit_candidate_id=None,
                seed_factor_id=None,
                expression="rank(close)",
                region="USA",
                universe="TOP3000",
                delay=1,
                decay=0,
                neutralization="SUBINDUSTRY",
                truncation=0.08,
                account="primary",
                ok=True,
                error_message=None,
                alpha_id="X",
                simulation_id="Y",
                is_metrics={"sharpe": 1.5, "fitness": 1.2, "turnover": 0.05},
                oos_metrics={},
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    r = await client.post(
        "/api/v1/admission/decide",
        headers=auth_headers,
        json={"wq_simulation_run_id": "wsim_test_adm_1"},
    )
    assert r.status_code == 201
    assert r.json()["decision"]["decision"] == "admitted"
