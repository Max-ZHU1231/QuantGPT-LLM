#!/usr/bin/env python3
"""随机种子因子 + WQ simulate 落库演示。

加载 `.env.example` 再 `.env`。不要求 DEEPSEEK_API_KEY。

用法:
  python scripts/demo_random_seed_wq_sim.py          # 需 WQ_BRAIN 凭证
  python scripts/demo_random_seed_wq_sim.py --mock   # 假指标，仅测落库（不需 WQ 账号）
  # 或在 .env 设 WQ_SIMULATE_MOCK=true，请求将默认走 mock（仍可用 --mock 显式开启）
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv_file(path: Path, *, override: bool) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if override:
            os.environ[key] = val
        else:
            os.environ.setdefault(key, val)


_load_dotenv_file(_ROOT / ".env.example", override=True)
_load_dotenv_file(_ROOT / ".env", override=True)

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("JWT_SECRET_KEY", "demo-seed-wq-local-secret")
os.environ.setdefault("AUTH_DISABLED", "false")
os.environ.setdefault("QUANTGPT_TASK_BACKEND", "thread")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

RATIONALE_50 = "测" * 50

EXPR_POOL = [
    "rank(close/ts_mean(close,20))",
    "rank(volume/ts_mean(volume,15))",
    "ts_rank(close,10)-ts_rank(volume,10)",
    "rank(ts_delta(close,5)/ts_std(close,20))",
    "rank(high/low)-rank(close/ts_mean(close,60))",
    "ts_mean(rank(close),5)",
]


async def _run(*, use_mock: bool) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from quantgpt.api_server import app
    from quantgpt.auth import create_access_token, hash_password
    from quantgpt.db import get_db
    from quantgpt.models import Base, User
    from quantgpt.wq_brain_client import is_configured
    from quantgpt.wq_pipeline import wq_mock_simulate_enabled

    effective_mock = use_mock or wq_mock_simulate_enabled()
    if not effective_mock and not is_configured("primary"):
        print(
            "错误：未配置 WQ BRAIN 账号。请在 .env 中设置 WQ_BRAIN_EMAIL 与 WQ_BRAIN_PASSWORD，\n"
            "或使用 --mock / WQ_SIMULATE_MOCK=true 仅测落库。",
            flush=True,
        )
        sys.exit(1)

    expr = random.choice(EXPR_POOL)
    name = f"随机WQ种子_{random.randint(1000, 9999)}"

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    user_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            User(
                id=user_id,
                email="demo_seed_wq@local.test",
                password_hash=hash_password("demo"),
                is_active=True,
            )
        )
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
    token = create_access_token(user_id, "demo_seed_wq@local.test")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://demo", timeout=600.0) as client:
            print("=== 随机种子 + WQ 模拟 ===\n", flush=True)
            print(f"模式: {'MOCK（假数据落库）' if effective_mock else 'WQ BRAIN 真实 simulate'}\n", flush=True)
            print(f"表达式: {expr}\n名称: {name}\n", flush=True)

            cr = await client.post(
                "/api/v1/seed_factors",
                headers=headers,
                json={
                    "name": name,
                    "expression": expr,
                    "econ_rationale": RATIONALE_50,
                    "market": "USA",
                    "universe": "TOP3000",
                    "frequency": "daily",
                    "factor_type": "demo_wq",
                    "blacklist_operators": [],
                    "blacklist_fields": [],
                    "attachment_urls": [],
                },
            )
            if cr.status_code != 201:
                print(f"创建种子失败 HTTP {cr.status_code}: {cr.text}", flush=True)
                sys.exit(1)
            sf_id = cr.json()["seed_factor_id"]
            print(f"[OK] SeedFactor id={sf_id}\n", flush=True)

            print(
                "正在写入模拟结果（mock 为瞬时完成）...\n"
                if effective_mock
                else "正在调用 WQ BRAIN simulate（可能需数分钟）...\n",
                flush=True,
            )
            sr = await client.post(
                "/api/v1/wq_simulations/run",
                headers=headers,
                json={
                    "expression": expr,
                    "seed_factor_id": sf_id,
                    "region": "USA",
                    "universe": "TOP3000",
                    "delay": 1,
                    "decay": 0,
                    "neutralization": "SUBINDUSTRY",
                    "truncation": 0.08,
                    "account": "primary",
                    "mock": effective_mock,
                },
            )
            if sr.status_code != 201:
                print(f"WQ 模拟失败 HTTP {sr.status_code}: {sr.text}", flush=True)
                sys.exit(1)
            body = sr.json()
            sim = body.get("simulation") or {}
            print("[OK] 模拟已结束并写入 wq_simulation_runs\n", flush=True)
            print(f"  run_id={sim.get('id')} ok={sim.get('ok')} alpha_id={sim.get('alpha_id')}", flush=True)
            if sim.get("error_message"):
                print(f"  error_message={sim.get('error_message')}", flush=True)
            is_m = sim.get("is_metrics") or {}
            if isinstance(is_m, dict) and is_m:
                print(
                    f"  IS sharpe={is_m.get('sharpe')} fitness={is_m.get('fitness')} turnover={is_m.get('turnover')}",
                    flush=True,
                )
            print("\n完成。", flush=True)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="随机种子 + WQ simulate 落库演示")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="使用合成指标写入 wq_simulation_runs（不需 WQ 账号）",
    )
    args = parser.parse_args()
    asyncio.run(_run(use_mock=args.mock))


if __name__ == "__main__":
    main()
