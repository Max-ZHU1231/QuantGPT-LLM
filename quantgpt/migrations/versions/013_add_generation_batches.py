"""add generation_batches and edit_candidates for minimal-edit pipeline

Revision ID: 013
Revises: 012
Create Date: 2026-05-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_batches",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("seed_factor_id", sa.String(64), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("prompt_version", sa.String(50), nullable=False, server_default="m1-3-v1"),
        sa.Column("target_metric", sa.String(50), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("constraint_description", sa.Text(), nullable=True),
        sa.Column("knowledge_base_snapshot", sa.JSON(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["seed_factor_id"], ["seed_factors.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_generation_batches_seed_factor_id", "generation_batches", ["seed_factor_id"])
    op.create_index("ix_generation_batches_status", "generation_batches", ["generation_status"])

    op.create_table(
        "edit_candidates",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("seed_factor_id", sa.String(64), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("edit_summary", sa.JSON(), nullable=False),
        sa.Column("total_edits", sa.Integer(), nullable=True),
        sa.Column("edit_direction", sa.String(50), nullable=True),
        sa.Column("expected_sharpe_delta", sa.String(50), nullable=True),
        sa.Column("expected_ic_delta", sa.String(50), nullable=True),
        sa.Column("expected_turnover_delta", sa.String(50), nullable=True),
        sa.Column("impact_confidence", sa.String(50), nullable=True),
        sa.Column("core_logic_preserved", sa.Boolean(), nullable=False),
        sa.Column("deviation_explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["batch_id"], ["generation_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seed_factor_id"], ["seed_factors.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_edit_candidates_batch_id", "edit_candidates", ["batch_id"])
    op.create_index("ix_edit_candidates_seed_factor_id", "edit_candidates", ["seed_factor_id"])


def downgrade() -> None:
    op.drop_index("ix_edit_candidates_seed_factor_id", table_name="edit_candidates")
    op.drop_index("ix_edit_candidates_batch_id", table_name="edit_candidates")
    op.drop_table("edit_candidates")
    op.drop_index("ix_generation_batches_status", table_name="generation_batches")
    op.drop_index("ix_generation_batches_seed_factor_id", table_name="generation_batches")
    op.drop_table("generation_batches")
