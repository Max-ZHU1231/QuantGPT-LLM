"""Smoke tests for factor_pipeline package exports."""

from quantgpt.factor_pipeline import (
    DEFAULT_ADMISSION_THRESHOLDS,
    IMPLEMENTATION_MATRIX,
    PIPELINE_VERSION,
    summarize_completion,
)


def test_pipeline_version():
    assert PIPELINE_VERSION


def test_implementation_matrix_nonempty():
    assert len(IMPLEMENTATION_MATRIX) >= 5
    counts = summarize_completion()
    assert sum(counts.values()) == len(IMPLEMENTATION_MATRIX)


def test_thresholds_defaults():
    assert DEFAULT_ADMISSION_THRESHOLDS.sharpe_min == 1.25


def test_lazy_facade():
    from quantgpt.factor_pipeline import FactorResearchPipeline

    assert FactorResearchPipeline.step4_expression_gate_wq("rank(close)")["valid"]
