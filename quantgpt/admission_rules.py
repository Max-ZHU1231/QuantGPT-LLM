"""Backward-compat shim — 入库规则实现已迁至 ``quantgpt.factor_pipeline.admission``。"""

from __future__ import annotations

from .factor_pipeline.admission import (
    RULE_ENGINE_VERSION,
    correlation_dedup_stub,
    evaluate_admission_from_sim_metrics,
)

__all__ = [
    "RULE_ENGINE_VERSION",
    "correlation_dedup_stub",
    "evaluate_admission_from_sim_metrics",
]
