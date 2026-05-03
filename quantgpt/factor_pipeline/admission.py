"""入库决策规则引擎（M1-6）— 属于 factor_pipeline 核心实现。"""

from __future__ import annotations

from typing import Any

from .config import DEFAULT_ADMISSION_THRESHOLDS

RULE_ENGINE_VERSION = "factor-pipeline-1.0"


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def evaluate_admission_from_sim_metrics(is_metrics: dict | None, *, ok: bool) -> tuple[str, dict]:
    """Return (decision, reasons); decision ∈ admitted | rejected | pending."""
    th = DEFAULT_ADMISSION_THRESHOLDS
    reasons: dict[str, Any] = {"rule_engine_version": RULE_ENGINE_VERSION, "thresholds": th.__dict__}
    if not ok:
        reasons["gate"] = "simulation_not_ok"
        return "rejected", reasons

    if not is_metrics:
        reasons["gate"] = "missing_is_metrics"
        return "pending", reasons

    sharpe = _safe_float(is_metrics.get("sharpe"))
    fitness = _safe_float(is_metrics.get("fitness"))
    turnover = _safe_float(is_metrics.get("turnover"))

    reasons["metrics"] = {"sharpe": sharpe, "fitness": fitness, "turnover": turnover}

    if sharpe is not None and sharpe >= th.sharpe_min and fitness is not None and fitness >= th.fitness_min:
        if turnover is not None and turnover > th.turnover_max:
            reasons["gate"] = "turnover_too_high"
            return "rejected", reasons
        reasons["gate"] = "passed_thresholds"
        return "admitted", reasons

    reasons["gate"] = "below_sharpe_or_fitness"
    return "rejected", reasons


def correlation_dedup_stub(_expression: str, _existing: list[str] | None = None) -> bool:
    """占位：与库内因子相关性去重（模板 §6 Step 6 / §11.1）。"""
    return False
