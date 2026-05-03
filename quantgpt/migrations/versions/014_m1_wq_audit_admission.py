"""M1-5/M1-6 — WQ simulation runs, admission decisions, audit trails.

Revision ID: 014
Revises: 013
Create Date: 2026-05-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wq_simulation_runs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("edit_candidate_id", sa.String(64), nullable=True),
        sa.Column("seed_factor_id", sa.String(64), nullable=True),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("region", sa.String(20), nullable=False, server_default="USA"),
        sa.Column("universe", sa.String(40), nullable=False, server_default="TOP3000"),
        sa.Column("delay", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("decay", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("neutralization", sa.String(40), nullable=False, server_default="SUBINDUSTRY"),
        sa.Column("truncation", sa.Float(), nullable=False, server_default="0.08"),
        sa.Column("account", sa.String(20), nullable=False, server_default="primary"),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("alpha_id", sa.String(128), nullable=True),
        sa.Column("simulation_id", sa.String(128), nullable=True),
        sa.Column("is_metrics", sa.JSON(), nullable=True),
        sa.Column("oos_metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["edit_candidate_id"], ["edit_candidates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seed_factor_id"], ["seed_factors.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wq_simulation_runs_created_by", "wq_simulation_runs", ["created_by"])
    op.create_index("ix_wq_simulation_runs_edit_candidate_id", "wq_simulation_runs", ["edit_candidate_id"])

    op.create_table(
        "admission_decisions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("edit_candidate_id", sa.String(64), nullable=True),
        sa.Column("wq_simulation_run_id", sa.String(64), nullable=True),
        sa.Column("expression_snapshot", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("rule_engine_version", sa.String(32), nullable=False, server_default="m1-6-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["edit_candidate_id"], ["edit_candidates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["wq_simulation_run_id"], ["wq_simulation_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_admission_decisions_created_by", "admission_decisions", ["created_by"])
    op.create_index("ix_admission_decisions_wq_run", "admission_decisions", ["wq_simulation_run_id"])

    op.create_table(
        "audit_trails",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_trails_event_type", "audit_trails", ["event_type"])
    op.create_index("ix_audit_trails_entity", "audit_trails", ["entity_type", "entity_id"])
    op.create_index("ix_audit_trails_created_at", "audit_trails", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_trails_created_at", table_name="audit_trails")
    op.drop_index("ix_audit_trails_entity", table_name="audit_trails")
    op.drop_index("ix_audit_trails_event_type", table_name="audit_trails")
    op.drop_table("audit_trails")

    op.drop_index("ix_admission_decisions_wq_run", table_name="admission_decisions")
    op.drop_index("ix_admission_decisions_created_by", table_name="admission_decisions")
    op.drop_table("admission_decisions")

    op.drop_index("ix_wq_simulation_runs_edit_candidate_id", table_name="wq_simulation_runs")
    op.drop_index("ix_wq_simulation_runs_created_by", table_name="wq_simulation_runs")
    op.drop_table("wq_simulation_runs")
