"""合并 DB 规则画像与默认门槛（模板 §7.2）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config import DEFAULT_ADMISSION_THRESHOLDS

DEFAULT_RULE_BUNDLE: dict[str, Any] = {
    "admission": {
        "sharpe_min": DEFAULT_ADMISSION_THRESHOLDS.sharpe_min,
        "fitness_min": DEFAULT_ADMISSION_THRESHOLDS.fitness_min,
        "turnover_max": DEFAULT_ADMISSION_THRESHOLDS.turnover_max,
        "ir_min": None,
        "oos_sharpe_decay_ratio_max": None,
    },
    "scoring": {
        "w_sharpe": 0.35,
        "w_fitness": 0.35,
        "w_turnover_penalty": 0.2,
        "w_oos_decay_penalty": 0.1,
    },
    "workflow": {
        "requires_human_on_admit": False,
        "min_approval_levels": 1,
    },
}


def merge_rule_bundle(profile_rules_json: dict[str, Any] | None) -> dict[str, Any]:
    """浅合并 profile.rules_json 到 DEFAULT_RULE_BUNDLE。"""
    base = deepcopy(DEFAULT_RULE_BUNDLE)
    if not profile_rules_json:
        return base
    for key in ("admission", "scoring", "workflow"):
        if key in profile_rules_json and isinstance(profile_rules_json[key], dict):
            base.setdefault(key, {}).update(profile_rules_json[key])
    return base
