"""可配置门槛占位（规则中心 MVP）：与模板 §7.2 / §11 对齐，后续可接 DB/API。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdmissionHardThresholds:
    """硬门槛 — 当前与 WQBrain SUBMIT_THRESHOLDS / MVP 规则引擎一致。"""

    sharpe_min: float = 1.25
    fitness_min: float = 1.0
    turnover_max: float = 0.7


DEFAULT_ADMISSION_THRESHOLDS = AdmissionHardThresholds()


@dataclass(frozen=True)
class LLMMinimalEditDefaults:
    """LLM 最小改动生成默认 — 与 ``factor_pipeline.minimal_edit_generator`` / ``GenerationBatch`` 字段对齐。"""

    prompt_version: str = "m1-3-v1"
    temperature: float = 0.3


DEFAULT_LLM_MINIMAL_EDIT = LLMMinimalEditDefaults()


@dataclass(frozen=True)
class ApplicabilityTemplate:
    """适用范围模板 §3 — 由部署方填写，不参与运行时校验（文档/配置占位）。"""

    markets: str = "[待填写，例如 US / China / Global]"
    universes: str = "[待填写，例如 TOP3000 / hs300]"
    frequencies: str = "[待填写，例如 Daily]"
    factor_families: str = "[待填写，例如 价量、波动、质量、行为]"


DEFAULT_APPLICABILITY = ApplicabilityTemplate()
