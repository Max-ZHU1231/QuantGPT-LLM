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
