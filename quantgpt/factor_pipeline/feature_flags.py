"""路线图 P0 — 特性开关（环境变量，默认关闭）。"""

from __future__ import annotations

import os


def _truthy(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def pipeline_one_click_enabled() -> bool:
    """一键 gate → simulate → decide（REST / 门面）。"""
    return _truthy("FACTOR_PIPELINE_ONE_CLICK")


def pipeline_llm_audit_enabled() -> bool:
    """批次完成后将 prompt_hash / LLM 响应摘要写入审计（脱敏由调用方截断）。"""
    return _truthy("FACTOR_PIPELINE_LLM_AUDIT")


def pipeline_semantic_mvp_enabled() -> bool:
    """路线图 P1 — validate_wq_full 附带经济/语义启发式（非 AST）。"""
    return _truthy("FACTOR_PIPELINE_SEMANTIC_MVP")
