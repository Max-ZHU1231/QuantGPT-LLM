"""Seed-factor intake models (M1). Tables only — no business logic here."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from .models import Base, _utcnow


class SeedFactor(Base):
    """锚定 / 种子因子：后续 GenerationBatch、EditCandidate 将外键引用此表。"""

    __tablename__ = "seed_factors"
    __table_args__ = (
        UniqueConstraint("name", name="uq_seed_factors_name"),
        Index("ix_seed_factors_market_universe_status", "market", "universe", "status"),
    )

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    expression = Column(Text, nullable=False)
    econ_rationale = Column(Text, nullable=False)
    market = Column(String(50), nullable=False)
    universe = Column(String(50), nullable=False)
    frequency = Column(String(20), nullable=False)
    factor_type = Column(String(100), nullable=True)

    blacklist_operators = Column(JSON, nullable=True)
    blacklist_fields = Column(JSON, nullable=True)

    version = Column(Integer, nullable=False, default=1)
    created_by = Column(String(100), nullable=False)
    attachment_urls = Column(JSON, nullable=True)

    reference_backtest = Column(JSON, nullable=True)

    # 生命周期：使用字符串枚举值，避免错误的 Column(Enum(...)) 字面量写法
    status = Column(String(32), nullable=False, default="active")

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class GenerationBatch(Base):
    """LLM 最小改动生成批次（DeepSeek）。"""

    __tablename__ = "generation_batches"
    __table_args__ = (
        Index("ix_generation_batches_seed_factor_id", "seed_factor_id"),
        Index("ix_generation_batches_status", "generation_status"),
    )

    id = Column(String(64), primary_key=True)
    seed_factor_id = Column(String(64), ForeignKey("seed_factors.id", ondelete="CASCADE"), nullable=False)

    model = Column(String(100), nullable=False)
    temperature = Column(Float, nullable=False, default=0.3)
    prompt_version = Column(String(50), nullable=False, default="m1-3-v1")

    target_metric = Column(String(50), nullable=True)
    current_value = Column(Float, nullable=True)
    target_value = Column(Float, nullable=True)
    constraint_description = Column(Text, nullable=True)
    knowledge_base_snapshot = Column(JSON, nullable=True)

    candidate_count = Column(Integer, nullable=False, default=0)
    generation_status = Column(String(32), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class EditCandidate(Base):
    """单次批次下的表达式候选。"""

    __tablename__ = "edit_candidates"
    __table_args__ = (
        Index("ix_edit_candidates_batch_id", "batch_id"),
        Index("ix_edit_candidates_seed_factor_id", "seed_factor_id"),
    )

    id = Column(String(64), primary_key=True)
    batch_id = Column(String(64), ForeignKey("generation_batches.id", ondelete="CASCADE"), nullable=False)
    seed_factor_id = Column(String(64), ForeignKey("seed_factors.id", ondelete="CASCADE"), nullable=False)

    expression = Column(Text, nullable=False)
    edit_summary = Column(JSON, nullable=False)

    total_edits = Column(Integer, nullable=True)
    edit_direction = Column(String(50), nullable=True)

    expected_sharpe_delta = Column(String(50), nullable=True)
    expected_ic_delta = Column(String(50), nullable=True)
    expected_turnover_delta = Column(String(50), nullable=True)
    impact_confidence = Column(String(50), nullable=True)

    core_logic_preserved = Column(Boolean, nullable=False, default=True)
    deviation_explanation = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class WQSimulationRun(Base):
    """WQ BRAIN simulate-only run (M1-5); metrics persisted (no formal submit in this path)."""

    __tablename__ = "wq_simulation_runs"
    __table_args__ = (
        Index("ix_wq_simulation_runs_created_by", "created_by"),
        Index("ix_wq_simulation_runs_edit_candidate_id", "edit_candidate_id"),
    )

    id = Column(String(64), primary_key=True)
    created_by = Column(String(100), nullable=False)
    edit_candidate_id = Column(String(64), ForeignKey("edit_candidates.id", ondelete="SET NULL"), nullable=True)
    seed_factor_id = Column(String(64), ForeignKey("seed_factors.id", ondelete="SET NULL"), nullable=True)

    expression = Column(Text, nullable=False)
    region = Column(String(20), nullable=False, default="USA")
    universe = Column(String(40), nullable=False, default="TOP3000")
    delay = Column(Integer, nullable=False, default=1)
    decay = Column(Integer, nullable=False, default=0)
    neutralization = Column(String(40), nullable=False, default="SUBINDUSTRY")
    truncation = Column(Float, nullable=False, default=0.08)
    account = Column(String(20), nullable=False, default="primary")

    ok = Column(Boolean, nullable=False, default=False)
    error_message = Column(Text, nullable=True)
    alpha_id = Column(String(128), nullable=True)
    simulation_id = Column(String(128), nullable=True)
    is_metrics = Column(JSON, nullable=True)
    oos_metrics = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class AdmissionDecision(Base):
    """Rule-engine admission outcome (M1-6)."""

    __tablename__ = "admission_decisions"
    __table_args__ = (
        Index("ix_admission_decisions_created_by", "created_by"),
        Index("ix_admission_decisions_wq_run", "wq_simulation_run_id"),
    )

    id = Column(String(64), primary_key=True)
    created_by = Column(String(100), nullable=False)
    edit_candidate_id = Column(String(64), ForeignKey("edit_candidates.id", ondelete="SET NULL"), nullable=True)
    wq_simulation_run_id = Column(String(64), ForeignKey("wq_simulation_runs.id", ondelete="SET NULL"), nullable=True)
    expression_snapshot = Column(Text, nullable=True)

    decision = Column(String(32), nullable=False)
    reasons = Column(JSON, nullable=True)
    rule_engine_version = Column(String(32), nullable=False, default="m1-6-v1")

    composite_score = Column(Float, nullable=True)
    human_approval_status = Column(String(32), nullable=False, default="not_required")
    human_approval_comment = Column(Text, nullable=True)
    human_approved_by = Column(String(100), nullable=True)
    human_approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_chain = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SeedFactorRevision(Base):
    """锚因子修订快照（模板 §7.1 版本化）。"""

    __tablename__ = "seed_factor_revisions"
    __table_args__ = (Index("ix_seed_factor_revisions_seed_id", "seed_factor_id"),)

    id = Column(String(64), primary_key=True)
    seed_factor_id = Column(String(64), ForeignKey("seed_factors.id", ondelete="CASCADE"), nullable=False)
    version_after = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    edited_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PipelineRuleProfile(Base):
    """可配置规则画像（正式 / 灰度）（模板 §7.2）。"""

    __tablename__ = "pipeline_rule_profiles"
    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uq_pipeline_rule_profiles_name_user"),
        Index("ix_pipeline_rule_profiles_created_by", "created_by"),
    )

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    profile_kind = Column(String(32), nullable=False, default="formal")
    market = Column(String(50), nullable=True)
    universe = Column(String(50), nullable=True)
    frequency = Column(String(20), nullable=True)
    rules_json = Column(JSON, nullable=False, default=lambda: {})
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class PipelineRunJob(Base):
    """门禁 → simulate 编排任务（模板 §7.5）。"""

    __tablename__ = "pipeline_run_jobs"
    __table_args__ = (
        Index("ix_pipeline_run_jobs_created_by", "created_by"),
        Index("ix_pipeline_run_jobs_status", "status"),
    )

    id = Column(String(64), primary_key=True)
    created_by = Column(String(100), nullable=False)
    seed_factor_id = Column(String(64), ForeignKey("seed_factors.id", ondelete="SET NULL"), nullable=True)
    edit_candidate_id = Column(String(64), ForeignKey("edit_candidates.id", ondelete="SET NULL"), nullable=True)
    expression = Column(Text, nullable=False)

    gate_passed = Column(Boolean, nullable=False, default=False)
    gate_report = Column(JSON, nullable=True)
    wq_simulation_run_id = Column(String(64), ForeignKey("wq_simulation_runs.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(32), nullable=False, default="queued")
    error_message = Column(Text, nullable=True)
    mock_used = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class AuditTrail(Base):
    """Append-only audit events (M1-6)."""

    __tablename__ = "audit_trails"
    __table_args__ = (
        Index("ix_audit_trails_event_type", "event_type"),
        Index("ix_audit_trails_entity", "entity_type", "entity_id"),
        Index("ix_audit_trails_created_at", "created_at"),
    )

    id = Column(String(64), primary_key=True)
    user_id = Column(String(100), nullable=True)
    event_type = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
