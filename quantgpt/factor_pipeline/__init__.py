"""QuantGPT — LLM 因子研发改造流水线（锚因子 → 最小改动 → WQ 门禁 → simulate → 入库 → 审计）。

本包聚合 M1–M7 MVP 能力并与《LLM 因子开发改造方案（模板版）》对齐说明见 ``FRAMEWORK.md``；
程序化对照矩阵见 ``status.IMPLEMENTATION_MATRIX``。

运行时 ORM 表仍定义于 ``quantgpt.seed_models``（由 ``quantgpt.models`` 导入 ``SeedFactor`` 注册元数据）。
"""

from __future__ import annotations

PIPELINE_VERSION = "1.0.0-mvp"

from .config import (
    DEFAULT_ADMISSION_THRESHOLDS,
    DEFAULT_APPLICABILITY,
    DEFAULT_LLM_MINIMAL_EDIT,
    AdmissionHardThresholds,
    ApplicabilityTemplate,
    LLMMinimalEditDefaults,
)
from .status import IMPLEMENTATION_MATRIX, summarize_completion

__all__ = [
    "PIPELINE_VERSION",
    "AdmissionHardThresholds",
    "ApplicabilityTemplate",
    "LLMMinimalEditDefaults",
    "DEFAULT_ADMISSION_THRESHOLDS",
    "DEFAULT_LLM_MINIMAL_EDIT",
    "DEFAULT_APPLICABILITY",
    "IMPLEMENTATION_MATRIX",
    "summarize_completion",
    "FactorResearchPipeline",
]


def __getattr__(name: str):
    if name == "FactorResearchPipeline":
        from .facade import FactorResearchPipeline

        return FactorResearchPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
