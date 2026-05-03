"""seed revisions, rule profiles, pipeline jobs, admission human fields, reference_backtest

Revision ID: 015
Revises: 014
Create Date: 2026-05-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("seed_factors", sa.Column("reference_backtest", sa.JSON(), nullable=True))

    op.create_table(
        "seed_factor_revisions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("seed_factor_id", sa.String(64), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("edited_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["seed_factor_id"], ["seed_factors.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_seed_factor_revisions_seed_id", "seed_factor_revisions", ["seed_factor_id"])

    op.create_table(
        "pipeline_rule_profiles",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("profile_kind", sa.String(32), nullable=False, server_default="formal"),
        sa.Column("market", sa.String(50), nullable=True),
        sa.Column("universe", sa.String(50), nullable=True),
        sa.Column("frequency", sa.String(20), nullable=True),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "created_by", name="uq_pipeline_rule_profiles_name_user"),
    )
    op.create_index("ix_pipeline_rule_profiles_created_by", "pipeline_rule_profiles", ["created_by"])

    op.create_table(
        "pipeline_run_jobs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("seed_factor_id", sa.String(64), nullable=True),
        sa.Column("edit_candidate_id", sa.String(64), nullable=True),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("gate_passed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("gate_report", sa.JSON(), nullable=True),
        sa.Column("wq_simulation_run_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("mock_used", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["seed_factor_id"], ["seed_factors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["edit_candidate_id"], ["edit_candidates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["wq_simulation_run_id"], ["wq_simulation_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pipeline_run_jobs_created_by", "pipeline_run_jobs", ["created_by"])
    op.create_index("ix_pipeline_run_jobs_status", "pipeline_run_jobs", ["status"])

    op.add_column("admission_decisions", sa.Column("composite_score", sa.Float(), nullable=True))
    op.add_column(
        "admission_decisions",
        sa.Column("human_approval_status", sa.String(32), nullable=False, server_default="not_required"),
    )
    op.add_column("admission_decisions", sa.Column("human_approval_comment", sa.Text(), nullable=True))
    op.add_column("admission_decisions", sa.Column("human_approved_by", sa.String(100), nullable=True))
    op.add_column("admission_decisions", sa.Column("human_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("admission_decisions", sa.Column("approval_chain", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("admission_decisions", "approval_chain")
    op.drop_column("admission_decisions", "human_approved_at")
    op.drop_column("admission_decisions", "human_approved_by")
    op.drop_column("admission_decisions", "human_approval_comment")
    op.drop_column("admission_decisions", "human_approval_status")
    op.drop_column("admission_decisions", "composite_score")

    op.drop_index("ix_pipeline_run_jobs_status", table_name="pipeline_run_jobs")
    op.drop_index("ix_pipeline_run_jobs_created_by", table_name="pipeline_run_jobs")
    op.drop_table("pipeline_run_jobs")

    op.drop_index("ix_pipeline_rule_profiles_created_by", table_name="pipeline_rule_profiles")
    op.drop_table("pipeline_rule_profiles")

    op.drop_index("ix_seed_factor_revisions_seed_id", table_name="seed_factor_revisions")
    op.drop_table("seed_factor_revisions")

    op.drop_column("seed_factors", "reference_backtest")
