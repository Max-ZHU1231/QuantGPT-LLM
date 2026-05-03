#!/usr/bin/env python3
"""端到端演示 M1-2 / M1-3：随机表达式创建 SeedFactor → 调用最小改动生成（真实 DeepSeek）。

加载 `.env.example` 再 `.env`（后者覆盖）。请勿将密钥写入日志输出。

用法:
  python scripts/demo_m1_seed_and_edits.py
"""

from __future__ import annotations

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

os.environ.setdefault("JWT_SECRET_KEY", "demo-m1-local-secret-do-not-use-in-prod")
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


async def _run() -> None:
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

    expr = random.choice(EXPR_POOL)
    name = f"随机演示_{random.randint(1000, 9999)}"

    from quantgpt.deepseek_client import factor_llm_config

    if not factor_llm_config().get("api_key"):
        print("错误：未配置 DEEPSEEK_API_KEY（请在 .env 中设置）", flush=True)
        sys.exit(1)

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    user_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            User(
                id=user_id,
                email="demo_m1@local.test",
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
    token = create_access_token(user_id, "demo_m1@local.test")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://demo") as client:
            print("=== M1 端到端演示 ===\n", flush=True)
            print(f"随机表达式: {expr}\n种子名称: {name}\n", flush=True)

            cr = await client.post(
                "/api/v1/seed_factors",
                headers=headers,
                json={
                    "name": name,
                    "expression": expr,
                    "econ_rationale": RATIONALE_50,
                    "market": "China",
                    "universe": "hs300",
                    "frequency": "daily",
                    "factor_type": "demo",
                    "blacklist_operators": [],
                    "blacklist_fields": [],
                    "attachment_urls": [],
                },
            )
            if cr.status_code != 201:
                print(f"创建种子失败 HTTP {cr.status_code}: {cr.text}", flush=True)
                sys.exit(1)
            sf_id = cr.json()["seed_factor_id"]
            print(f"[OK] SeedFactor created id={sf_id}\n", flush=True)

            gen = await client.post(
                "/api/v1/minimal_edits/generate",
                headers=headers,
                json={
                    "seed_factor_id": sf_id,
                    "target_gap": {
                        "metric": "sharpe",
                        "current": 1.1,
                        "target": 1.45,
                        "constraint": "单次演示：控制换手，不大改核心 rank/mean 结构",
                    },
                    "knowledge_base": {"verified_rules": [], "failed_paths": []},
                },
            )
            if gen.status_code != 201:
                print(f"最小改动生成失败 HTTP {gen.status_code}: {gen.text}", flush=True)
                sys.exit(1)
            payload = gen.json()
            batch = payload["batch"]
            print(
                f"[OK] batch_id={batch['batch_id']} "
                f"status={batch['generation_status']} "
                f"candidates={batch['candidate_count']}",
                flush=True,
            )
            if batch.get("error_message"):
                print(f"  error_message: {batch['error_message'][:500]}", flush=True)

            bid = batch["batch_id"]
            got = await client.get(f"/api/v1/minimal_edits/batches/{bid}", headers=headers)
            if got.status_code != 200:
                print(f"读取批次失败 HTTP {got.status_code}: {got.text}", flush=True)
                sys.exit(1)

            body = got.json()
            print(f"\n--- GET batch（共 {len(body['candidates'])} 条候选）---\n", flush=True)
            for i, c in enumerate(body["candidates"], 1):
                print(f"{i}. {c['expression']}", flush=True)
                es = c.get("edit_summary") or {}
                direction = es.get("edit_direction", "")
                print(f"   direction: {direction}", flush=True)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    print("\n完成。", flush=True)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
