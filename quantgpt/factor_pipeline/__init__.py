"""QuantGPT — LLM 因子研发改造流水线（锚因子 → 最小改动 → WQ 门禁 → simulate → 入库 → 审计）。

本包聚合 M1–M7 MVP 能力并与《LLM 因子开发改造方案（模板版）》对齐说明见 ``FRAMEWORK.md``；
程序化对照矩阵见 ``status.IMPLEMENTATION_MATRIX``。

运行时 ORM 表仍定义于 ``quantgpt.seed_models``（由 ``quantgpt.models`` 导入 ``SeedFactor`` 注册元数据）。
"""

from __future__ import annotations

PIPELINE_VERSION = "1.3.0-mvp"

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
    "generate_minimal_edits_for_seed",
    "get_batch_for_user",
]


def __getattr__(name: str):
    if name == "FactorResearchPipeline":
        from .facade import FactorResearchPipeline

        return FactorResearchPipeline
    if name == "generate_minimal_edits_for_seed":
        from .minimal_edit_generator import generate_minimal_edits_for_seed

        return generate_minimal_edits_for_seed
    if name == "get_batch_for_user":
        from .minimal_edit_generator import get_batch_for_user

        return get_batch_for_user
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
