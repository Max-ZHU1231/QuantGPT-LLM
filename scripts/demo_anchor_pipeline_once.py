"""一次性跑通：随机锚因子 → WQ 门禁 → simulate → 入库评估（stdout JSON）。

默认调用 **真实 WorldQuant BRAIN API**（需 ``WQ_BRAIN_EMAIL`` / ``WQ_BRAIN_PASSWORD``）。
离线调试请加 ``--mock``。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

# 项目根 .env（与 python -m quantgpt 一致）
_root = Path(__file__).resolve().parent.parent
_env_file = _root / ".env"
if _env_file.is_file():
    from quantgpt.deepseek_client import normalize_secret_env

    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = normalize_secret_env(val.strip())
            os.environ.setdefault(key, val)


async def main(*, use_mock: bool, account: str) -> None:
    os.chdir(_root)

    from sqlalchemy import select

    import quantgpt.models  # noqa: F401 — 注册 Base.metadata
    from quantgpt.auth import _DEV_USER_ID
    from quantgpt.db import _get_session_factory, close_db, init_db
    from quantgpt.expression_gate import validate_wq_full
    from quantgpt.factor_pipeline.admission import evaluate_admission_from_sim_metrics
    from quantgpt.managers.seed_factor_manager import SeedFactorManager
    from quantgpt.seed_models import SeedFactor
    from quantgpt.wq_brain_client import is_configured
    from quantgpt.wq_pipeline import persist_wq_simulation, wq_simulate_metrics_sync

    if not use_mock and not is_configured(account):
        err = {
            "error": "WQ BRAIN not configured: set WQ_BRAIN_EMAIL and WQ_BRAIN_PASSWORD (or WQ_BRAIN_ALT_* for account=alt), or pass --mock",
            "error_zh": "WQ BRAIN 未配置：设置上述环境变量，或使用 --mock",
            "account": account,
        }
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(json.dumps(err, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)

    await init_db()
    factory = _get_session_factory()
    uid_str = str(_DEV_USER_ID)

    async with factory() as db:
        res = await db.execute(select(SeedFactor).where(SeedFactor.created_by == uid_str))
        rows = list(res.scalars().all())
        mgr = SeedFactorManager(db)

        if not rows:
            suffix = random.randint(1000, 9999)
            picked = await mgr.create(
                user_id=_DEV_USER_ID,
                name=f"demo_anchor_{suffix}",
                expression="rank(-ts_corr(close, volume, 20))",
                econ_rationale=(
                    "Demo anchor: short-term price-volume correlation reversal; "
                    "economic narrative padded for minimum length requirement."
                ),
                market="USA",
                universe="TOP3000",
                frequency="daily",
            )
            await db.commit()
            created_note = "created_demo_anchor"
        else:
            picked = random.choice(rows)
            created_note = "picked_existing"

        expr = picked.expression
        region = (picked.market or "USA").strip()
        universe = (picked.universe or "TOP3000").strip()

        out: dict = {
            "note": created_note,
            "simulate_mode": "mock" if use_mock else "wq_brain",
            "wq_account": account,
            "anchor": {
                "id": picked.id,
                "name": picked.name,
                "expression": expr,
                "market": picked.market,
                "universe": picked.universe,
                "version": picked.version,
            },
        }

        gate = validate_wq_full(expr)
        out["gate"] = {
            "valid": gate.get("valid"),
            "failure_categories": gate.get("failure_categories"),
            "complexity": gate.get("complexity"),
        }

        sim = wq_simulate_metrics_sync(
            expr,
            region=region,
            universe=universe,
            mock=use_mock,
            account=account,
        )
        row = await persist_wq_simulation(
            db,
            user_id=_DEV_USER_ID,
            expression=expr,
            sim=sim,
            seed_factor_id=picked.id,
            region=region,
            universe=universe,
        )
        await db.commit()

        out["wq_simulation_run"] = {
            "id": row.id,
            "ok": row.ok,
            "error_message": row.error_message,
            "alpha_id": row.alpha_id,
            "simulation_id": row.simulation_id,
            "is_metrics": row.is_metrics,
            "oos_metrics": row.oos_metrics,
            "mock": use_mock,
            "raw_keys": list(sim.keys()) if isinstance(sim, dict) else None,
        }

        is_m = row.is_metrics if isinstance(row.is_metrics, dict) else None
        oos_m = row.oos_metrics if isinstance(row.oos_metrics, dict) else None
        decision, reasons = evaluate_admission_from_sim_metrics(
            is_m,
            ok=row.ok,
            oos_metrics=oos_m,
            profile_rules_json=None,
        )
        out["admission"] = {"decision": decision, "reasons": reasons}

    await close_db()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Anchor factor → gate → WQ simulate → admission")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="合成 simulate（不调用 BRAIN；不受 WQ_SIMULATE_MOCK 环境变量影响）",
    )
    parser.add_argument(
        "--account",
        choices=("primary", "alt"),
        default="primary",
        help="BRAIN 凭证账号槽（primary / alt）",
    )
    args = parser.parse_args()
    asyncio.run(main(use_mock=args.mock, account=args.account))
    sys.exit(0)
