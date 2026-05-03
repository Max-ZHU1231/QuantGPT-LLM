"""M1-4 — WQ expression gate aligned with ExpressionParser(mode='wq').

Syntax: ``ExpressionParser(mode='wq').parse(expr)`` only (no guide fake AST).
Optional whitelist uses tokenizer-style identifiers + prefix rules for news/group fields.
"""

from __future__ import annotations

import re

from .expression_parser import (
    ExpressionParser,
    _WQ_GROUP_PREFIXES,
    _WQ_NEWS_PREFIXES,
    wq_allowlisted_plain_identifiers,
)

_TOKEN_RE = re.compile(r"\b[A-Za-z_][\w]*\b")
_LOGICAL_WORDS = frozenset(
    {"and", "or", "not", "if", "else", "true", "false", "nan", "inf"}
)


def extract_identifier_tokens(expression: str) -> list[str]:
    """Rough tokenizer for identifiers (not a full lexer)."""
    return _TOKEN_RE.findall(expression)


def _token_allowed_wq(tok: str) -> bool:
    low = tok.lower()
    if low in _LOGICAL_WORDS:
        return True
    if low.startswith("adv") and len(low) > 3 and low[3:].isdigit():
        return True
    if "." in low:
        return any(low.startswith(p) for p in _WQ_GROUP_PREFIXES)
    if any(low.startswith(p) for p in _WQ_NEWS_PREFIXES):
        return True
    allow = wq_allowlisted_plain_identifiers()
    return low in allow


def whitelist_violations(expression: str) -> list[str]:
    """Return unknown identifier tokens under heuristic WQ allowlist."""
    seen: set[str] = set()
    bad: list[str] = []
    for tok in extract_identifier_tokens(expression):
        low = tok.lower()
        if low in seen:
            continue
        seen.add(low)
        if not _token_allowed_wq(tok):
            bad.append(tok)
    return bad


def validate_wq_parse(expression: str) -> tuple[bool, str | None]:
    """Run ``ExpressionParser(mode='wq').parse(expr)``. Returns (ok, error_message)."""
    try:
        ExpressionParser(mode="wq").parse(expression.strip())
        return True, None
    except Exception as e:
        return False, str(e)


def validate_wq(expression: str, *, strict_whitelist: bool = False) -> dict:
    """Full M1-4 gate: parser validation + optional identifier whitelist."""
    expr = (expression or "").strip()
    ok_parse, err = validate_wq_parse(expr)
    out: dict = {
        "valid": ok_parse,
        "parse_error": err,
        "whitelist_checked": strict_whitelist,
        "whitelist_violations": [],
    }
    if not ok_parse:
        out["valid"] = False
        return out
    if strict_whitelist:
        violations = whitelist_violations(expr)
        out["whitelist_violations"] = violations
        if violations:
            out["valid"] = False
            out["whitelist_error"] = "identifiers_not_allowlisted"
    return out


FAILURE_PARSER = "parser_error"
FAILURE_WHITELIST = "whitelist_violation"
FAILURE_COMPLEXITY = "complexity_threshold"
FAILURE_LENGTH = "expression_length"


def _paren_max_depth(s: str) -> int:
    d = 0
    m = 0
    for ch in s:
        if ch == "(":
            d += 1
            m = max(m, d)
        elif ch == ")":
            d = max(0, d - 1)
    return m


def complexity_heuristic(expression: str) -> dict:
    """启发式复杂度指标（非 AST 节点统计；模板 §7.4）。"""
    expr = expression.strip()
    ids = extract_identifier_tokens(expr)
    return {
        "length": len(expr),
        "paren_max_depth": _paren_max_depth(expr),
        "identifier_token_count": len(set(i.lower() for i in ids)),
        "comma_count": expr.count(","),
    }


def validate_wq_full(
    expression: str,
    *,
    strict_whitelist: bool = False,
    max_length: int | None = None,
    max_paren_depth: int | None = None,
) -> dict:
    """门禁详情：分类失败原因 + 复杂度 + 修复建议占位。"""
    from .expression_parser import ExpressionParser

    max_len = max_length if max_length is not None else ExpressionParser.MAX_EXPRESSION_LENGTH
    max_paren = max_paren_depth if max_paren_depth is not None else ExpressionParser.MAX_DEPTH

    expr = (expression or "").strip()
    categories: list[str] = []
    repair_hints: list[str] = []

    out = validate_wq(expression, strict_whitelist=strict_whitelist)
    comp = complexity_heuristic(expr)
    out["complexity"] = comp
    out["failure_categories"] = []
    out["repair_hints"] = repair_hints

    if len(expr) > max_len:
        out["valid"] = False
        categories.append(FAILURE_LENGTH)
        repair_hints.append(f"缩短表达式至不超过 {max_len} 字符")

    if comp["paren_max_depth"] > max_paren:
        out["valid"] = False
        categories.append(FAILURE_COMPLEXITY)
        repair_hints.append(f"降低嵌套深度（当前括号深度峰值 {comp['paren_max_depth']}，上限 {max_paren}）")

    if not out.get("valid"):
        if out.get("parse_error"):
            categories.append(FAILURE_PARSER)
            repair_hints.append("根据 Parser 报错检查函数名、括号与逗号")
        if out.get("whitelist_violations"):
            categories.append(FAILURE_WHITELIST)
            repair_hints.append("将未知标识符替换为 WQ 允许的字段/算子或合规前缀")

    # de-dup preserve order
    seen = set()
    fc = []
    for c in categories:
        if c not in seen:
            seen.add(c)
            fc.append(c)
    out["failure_categories"] = fc
    return out
