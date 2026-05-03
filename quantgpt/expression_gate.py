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
