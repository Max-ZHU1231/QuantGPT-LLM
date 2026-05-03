"""Seed-factor intake models (M1). Tables only — no business logic here."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, _utcnow


class SeedFactor(Base):
    """锚定 / 种子因子：后续 GenerationBatch、EditCandidate 将外键引用此表。"""

    __tablename__ = "seed_factors"
    __table_args__ = (
        UniqueConstraint("name", name="uq_seed_factors_name"),
        Index("ix_seed_factors_market_universe_status", "market", "universe", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    econ_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    universe: Mapped[str] = mapped_column(String(50), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    factor_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    blacklist_operators: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    blacklist_fields: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    attachment_urls: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    reference_backtest: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GenerationBatch(Base):
    """LLM 最小改动生成批次（DeepSeek）。"""

    __tablename__ = "generation_batches"
    __table_args__ = (
        Index("ix_generation_batches_seed_factor_id", "seed_factor_id"),
        Index("ix_generation_batches_status", "generation_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seed_factor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("seed_factors.id", ondelete="CASCADE"), nullable=False
    )

    model: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False, default="m1-3-v1")

    target_metric: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    constraint_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_base_snapshot: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EditCandidate(Base):
    """单次批次下的表达式候选。"""

    __tablename__ = "edit_candidates"
    __table_args__ = (
        Index("ix_edit_candidates_batch_id", "batch_id"),
        Index("ix_edit_candidates_seed_factor_id", "seed_factor_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_batches.id", ondelete="CASCADE"), nullable=False
    )
    seed_factor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("seed_factors.id", ondelete="CASCADE"), nullable=False
    )

    expression: Mapped[str] = mapped_column(Text, nullable=False)
    edit_summary: Mapped[Any] = mapped_column(JSON, nullable=False)

    total_edits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edit_direction: Mapped[str | None] = mapped_column(String(50), nullable=True)

    expected_sharpe_delta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expected_ic_delta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expected_turnover_delta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    impact_confidence: Mapped[str | None] = mapped_column(String(50), nullable=True)

    core_logic_preserved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deviation_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class WQSimulationRun(Base):
    """WQ BRAIN simulate-only run (M1-5); metrics persisted (no formal submit in this path)."""

    __tablename__ = "wq_simulation_runs"
    __table_args__ = (
        Index("ix_wq_simulation_runs_created_by", "created_by"),
        Index("ix_wq_simulation_runs_edit_candidate_id", "edit_candidate_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    edit_candidate_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("edit_candidates.id", ondelete="SET NULL"), nullable=True
    )
    seed_factor_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("seed_factors.id", ondelete="SET NULL"), nullable=True
    )

    expression: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(String(20), nullable=False, default="USA")
    universe: Mapped[str] = mapped_column(String(40), nullable=False, default="TOP3000")
    delay: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    decay: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutralization: Mapped[str] = mapped_column(String(40), nullable=False, default="SUBINDUSTRY")
    truncation: Mapped[float] = mapped_column(Float, nullable=False, default=0.08)
    account: Mapped[str] = mapped_column(String(20), nullable=False, default="primary")

    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    alpha_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    simulation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_metrics: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    oos_metrics: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class AdmissionDecision(Base):
    """Rule-engine admission outcome (M1-6)."""

    __tablename__ = "admission_decisions"
    __table_args__ = (
        Index("ix_admission_decisions_created_by", "created_by"),
        Index("ix_admission_decisions_wq_run", "wq_simulation_run_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    edit_candidate_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("edit_candidates.id", ondelete="SET NULL"), nullable=True
    )
    wq_simulation_run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("wq_simulation_runs.id", ondelete="SET NULL"), nullable=True
    )
    expression_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    rule_engine_version: Mapped[str] = mapped_column(String(32), nullable=False, default="m1-6-v1")

    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    human_approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_required")
    human_approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    human_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_chain: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SeedFactorRevision(Base):
    """锚因子修订快照（模板 §7.1 版本化）。"""

    __tablename__ = "seed_factor_revisions"
    __table_args__ = (Index("ix_seed_factor_revisions_seed_id", "seed_factor_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seed_factor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("seed_factors.id", ondelete="CASCADE"), nullable=False
    )
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[Any] = mapped_column(JSON, nullable=False)
    edited_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PipelineRuleProfile(Base):
    """可配置规则画像（正式 / 灰度）（模板 §7.2）。"""

    __tablename__ = "pipeline_rule_profiles"
    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uq_pipeline_rule_profiles_name_user"),
        Index("ix_pipeline_rule_profiles_created_by", "created_by"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="formal")
    market: Mapped[str | None] = mapped_column(String(50), nullable=True)
    universe: Mapped[str | None] = mapped_column(String(50), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rules_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=lambda: {})
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class PipelineRunJob(Base):
    """门禁 → simulate 编排任务（模板 §7.5）。"""

    __tablename__ = "pipeline_run_jobs"
    __table_args__ = (
        Index("ix_pipeline_run_jobs_created_by", "created_by"),
        Index("ix_pipeline_run_jobs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    seed_factor_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("seed_factors.id", ondelete="SET NULL"), nullable=True
    )
    edit_candidate_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("edit_candidates.id", ondelete="SET NULL"), nullable=True
    )
    expression: Mapped[str] = mapped_column(Text, nullable=False)

    gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gate_report: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    wq_simulation_run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("wq_simulation_runs.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    mock_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditTrail(Base):
    """Append-only audit events (M1-6)."""

    __tablename__ = "audit_trails"
    __table_args__ = (
        Index("ix_audit_trails_event_type", "event_type"),
        Index("ix_audit_trails_entity", "entity_type", "entity_id"),
        Index("ix_audit_trails_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
