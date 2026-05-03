"""M1-6 — simplified rule engine + correlation stub."""

from __future__ import annotations

from typing import Any

RULE_ENGINE_VERSION = "m1-6-v1"


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def evaluate_admission_from_sim_metrics(is_metrics: dict | None, *, ok: bool) -> tuple[str, dict]:
    """Return (decision, reasons) where decision is admitted | rejected | pending."""
    reasons: dict[str, Any] = {"rule_engine_version": RULE_ENGINE_VERSION}
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

    if sharpe is not None and sharpe >= 1.25 and fitness is not None and fitness >= 1.0:
        if turnover is not None and turnover > 0.7:
            reasons["gate"] = "turnover_too_high"
            return "rejected", reasons
        reasons["gate"] = "passed_thresholds"
        return "admitted", reasons

    reasons["gate"] = "below_sharpe_or_fitness"
    return "rejected", reasons


def correlation_dedup_stub(_expression: str, _existing: list[str] | None = None) -> bool:
    """Placeholder for future correlation-based dedup against submitted alphas."""
    return False
