"""综合评分（模板 §11.2）— 启发式线性加权。"""

from __future__ import annotations

from typing import Any


def _sf(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def oos_sharpe_decay_ratio(is_metrics: dict | None, oos_metrics: dict | None) -> float | None:
    """相对样本外 Sharpe 衰减比例 (IS-OOS)/max(|IS|,eps)；None 若缺失。"""
    if not is_metrics or not oos_metrics:
        return None
    is_s = _sf(is_metrics.get("sharpe"))
    oos_s = _sf(oos_metrics.get("sharpe"))
    if is_s is None or oos_s is None:
        return None
    denom = max(abs(is_s), 1e-6)
    return max(0.0, (is_s - oos_s) / denom)


def compute_composite_score(
    is_metrics: dict | None,
    oos_metrics: dict | None,
    *,
    scoring_weights: dict[str, float],
) -> float | None:
    """Score = w_s * norm(sharpe) + w_f * norm(fitness) - w_t * turnover_penalty - w_d * decay_penalty"""
    if not is_metrics:
        return None
    sh = _sf(is_metrics.get("sharpe"))
    fit = _sf(is_metrics.get("fitness"))
    turn = _sf(is_metrics.get("turnover"))
    if sh is None or fit is None:
        return None

    w_s = float(scoring_weights.get("w_sharpe", 0.35))
    w_f = float(scoring_weights.get("w_fitness", 0.35))
    w_t = float(scoring_weights.get("w_turnover_penalty", 0.2))
    w_d = float(scoring_weights.get("w_oos_decay_penalty", 0.1))

    norm_sh = max(min(sh / 3.0, 1.5), -0.5)
    norm_fit = max(min(fit / 2.0, 1.5), -0.5)
    turn_pen = max(0.0, (turn or 0.0) - 0.35)

    decay = oos_sharpe_decay_ratio(is_metrics, oos_metrics)
    decay_pen = decay if decay is not None else 0.0

    score = w_s * norm_sh + w_f * norm_fit - w_t * turn_pen - w_d * decay_pen
    return round(score, 6)
