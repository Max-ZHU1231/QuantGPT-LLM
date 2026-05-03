"""路线图 P1 — 轻量语义/经济启发式（非 AST，不替代 Parser）。"""

from __future__ import annotations

import re
from typing import Any


# 常见「明显泄漏」口头模式（启发式；WQ 合法表达式也可能误报）
_FORWARD_LOOKING_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\breturn\b", re.I), "keyword_return"),
    (re.compile(r"\bfuture\b", re.I), "keyword_future"),
    (re.compile(r"\bnext_?(?:day|bar|period)\b", re.I), "possible_forward_horizon"),
)

# 经济学备注：过度空洞的组合（仅提示）
_VAGUE_STACK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"rank\s*\(\s*rank\s*\(", re.I), "nested_rank_only"),
    (re.compile(r"scale\s*\(\s*scale\s*\(", re.I), "nested_scale_only"),
)


def semantic_economic_heuristics(expression: str) -> dict[str, Any]:
    """返回 flags / warnings；不改变门禁 valid（由调用方决定是否升格为 hard fail）。"""
    expr = (expression or "").strip()
    warnings: list[dict[str, str]] = []

    for rx, code in _FORWARD_LOOKING_PATTERNS:
        if rx.search(expr):
            warnings.append({"code": code, "severity": "warn", "hint": "核对是否为前视或非标字段用法"})

    for rx, code in _VAGUE_STACK_PATTERNS:
        if rx.search(expr):
            warnings.append({"code": code, "severity": "info", "hint": "多层单调变换可能稀释经济含义"})

    if len(expr) > 0 and expr.count("ts_") >= 6:
        warnings.append(
            {
                "code": "many_ts_ops",
                "severity": "info",
                "hint": "时间序列算子较多，关注过拟合与可解释性",
            }
        )

    worst = "ok"
    for w in warnings:
        if w["severity"] == "warn":
            worst = "warn"
            break
        worst = "info"

    return {"economic_semantic_mvp": True, "warnings": warnings, "summary_severity": worst}
