"""路线图 P2 — Prometheus / Histogram 占位钩子（未启用时为 no-op）。"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def prometheus_registry_ready() -> bool:
    return os.getenv("FACTOR_PIPELINE_PROMETHEUS", "").strip().lower() in ("1", "true", "yes", "on")


def observe_one_click_seconds(seconds: float, *, outcome: str) -> None:
    """完整流水线耗时直方图占位；接入 prometheus_client 时在此注册。"""
    if not prometheus_registry_ready():
        return
    logger.debug("pipeline.observe_one_click_seconds skipped (histogram not wired): %s %s", outcome, seconds)


def observe_gate_latency_seconds(seconds: float, *, phase: str) -> None:
    if not prometheus_registry_ready():
        return
    logger.debug("pipeline.observe_gate_latency_seconds skipped: %s %s", phase, seconds)


def metrics_extra_labels() -> dict[str, Any]:
    """部署时可注入静态标签（版本、环境）。"""
    return {"pipeline_version": os.getenv("FACTOR_PIPELINE_VERSION_LABEL", "")}
