"""Unit tests for M1-6 admission rules."""

from quantgpt.admission_rules import evaluate_admission_from_sim_metrics


def test_admit_when_sharpe_and_fitness_high():
    d, r = evaluate_admission_from_sim_metrics({"sharpe": 1.5, "fitness": 1.2, "turnover": 0.3}, ok=True)
    assert d == "admitted"
    assert r.get("gate") == "passed_thresholds"


def test_reject_when_turnover_too_high():
    d, r = evaluate_admission_from_sim_metrics({"sharpe": 2.0, "fitness": 1.5, "turnover": 0.71}, ok=True)
    assert d == "rejected"
    assert r.get("gate") == "turnover_too_high"


def test_pending_when_metrics_missing():
    d, r = evaluate_admission_from_sim_metrics(None, ok=True)
    assert d == "pending"


def test_reject_when_sim_failed():
    d, r = evaluate_admission_from_sim_metrics({"sharpe": 3}, ok=False)
    assert d == "rejected"
