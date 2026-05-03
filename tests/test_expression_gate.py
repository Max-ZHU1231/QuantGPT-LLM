"""Unit tests for M1-4 expression gate."""

from quantgpt.expression_gate import validate_wq, whitelist_violations


def test_wq_parse_rank_mean_ok():
    r = validate_wq("rank(close/ts_mean(close,20))")
    assert r["valid"] is True
    assert r["parse_error"] is None


def test_wq_parse_rejects_local_only_operator():
    r = validate_wq("tanh(close)")
    assert r["valid"] is False
    assert r["parse_error"]


def test_strict_whitelist_flags_unknown_identifier():
    expr = "rank(close)+unknown_wq_token_xyz"
    r = validate_wq(expr, strict_whitelist=True)
    assert r["valid"] is False
    assert "unknown_wq_token_xyz" in (r.get("whitelist_violations") or [])


def test_whitelist_violations_helpers():
    bad = whitelist_violations("rank(close)+foo_bar_unknown")
    assert "foo_bar_unknown" in bad
