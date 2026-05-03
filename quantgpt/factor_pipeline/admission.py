"""入库决策 — 硬门槛 + 综合分 + 工作流提示（模板 §6.6 / §11）。"""

from __future__ import annotations

from typing import Any

from .rule_merge import merge_rule_bundle
from .scoring import compute_composite_score, oos_sharpe_decay_ratio

RULE_ENGINE_VERSION = "factor-pipeline-2.0"


def _sf(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_ir(is_metrics: dict | None) -> float | None:
    if not is_metrics:
        return None
    for key in ("ir", "IR", "investability", "investibility"):
        v = _sf(is_metrics.get(key))
        if v is not None:
            return v
    return None


def evaluate_admission_from_sim_metrics(
    is_metrics: dict | None,
    *,
    ok: bool,
    oos_metrics: dict | None = None,
    profile_rules_json: dict[str, Any] | None = None,
) -> tuple[str, dict]:
    """评估入库：合并规则画像、硬门槛、综合分；返回 (decision, reasons)。"""
    bundle = merge_rule_bundle(profile_rules_json)
    adm = bundle["admission"]
    scoring_w = bundle["scoring"]
    workflow = bundle["workflow"]

    reasons: dict[str, Any] = {
        "rule_engine_version": RULE_ENGINE_VERSION,
        "thresholds": adm,
        "workflow_hints": workflow,
    }

    score = compute_composite_score(is_metrics, oos_metrics, scoring_weights=scoring_w)
    reasons["composite_score"] = score

    if not ok:
        reasons["gate"] = "simulation_not_ok"
        reasons["failure_category"] = "wq_simulation"
        return "rejected", reasons

    if not is_metrics:
        reasons["gate"] = "missing_is_metrics"
        reasons["failure_category"] = "missing_metrics"
        return "pending", reasons

    sharpe = _sf(is_metrics.get("sharpe"))
    fitness = _sf(is_metrics.get("fitness"))
    turnover = _sf(is_metrics.get("turnover"))
    ir = _extract_ir(is_metrics)

    reasons["metrics"] = {"sharpe": sharpe, "fitness": fitness, "turnover": turnover, "ir": ir}

    decay_ratio = oos_sharpe_decay_ratio(is_metrics, oos_metrics)
    reasons["oos_sharpe_decay_ratio"] = decay_ratio

    ir_min = adm.get("ir_min")
    if ir_min is not None and ir is not None and ir < float(ir_min):
        reasons["gate"] = "below_ir"
        reasons["failure_category"] = "ir"
        return "rejected", reasons

    max_decay = adm.get("oos_sharpe_decay_ratio_max")
    if max_decay is not None and decay_ratio is not None and decay_ratio > float(max_decay):
        reasons["gate"] = "oos_decay_exceeded"
        reasons["failure_category"] = "robustness"
        return "rejected", reasons

    sh_min = float(adm.get("sharpe_min", 1.25))
    fit_min = float(adm.get("fitness_min", 1.0))
    t_max = float(adm.get("turnover_max", 0.7))

    if sharpe is None or fitness is None:
        reasons["gate"] = "missing_core_metrics"
        reasons["failure_category"] = "incomplete_metrics"
        return "pending", reasons

    if sharpe < sh_min or fitness < fit_min:
        reasons["gate"] = "below_sharpe_or_fitness"
        reasons["failure_category"] = "performance"
        return "rejected", reasons

    if turnover is not None and turnover > t_max:
        reasons["gate"] = "turnover_too_high"
        reasons["failure_category"] = "trading"
        return "rejected", reasons

    reasons["gate"] = "passed_thresholds"
    reasons["failure_category"] = None
    reasons["requires_human_review"] = bool(workflow.get("requires_human_on_admit"))
    return "admitted", reasons


def correlation_dedup_stub(
    expression: str,
    existing_expressions: list[str] | None = None,
    *,
    similarity_threshold: float = 0.92,
) -> dict[str, Any]:
    """占位相关性去重：返回是否疑似重复及说明（模板 §11.1）。"""
    if not existing_expressions:
        return {"is_duplicate": False, "note": "no_peer_expressions", "similarity_threshold": similarity_threshold}
    norm = expression.strip().lower().replace(" ", "")
    for ex in existing_expressions:
        if not ex:
            continue
        other = ex.strip().lower().replace(" ", "")
        if norm == other:
            return {"is_duplicate": True, "reason": "exact_normalized_match", "similarity_threshold": similarity_threshold}
    return {"is_duplicate": False, "note": "no_exact_match_stub", "similarity_threshold": similarity_threshold}
