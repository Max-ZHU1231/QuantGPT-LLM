"""add seed_factors table for seed-factor intake pipeline

Revision ID: 012
Revises: 011
Create Date: 2026-05-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seed_factors",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("econ_rationale", sa.Text(), nullable=False),
        sa.Column("market", sa.String(50), nullable=False),
        sa.Column("universe", sa.String(50), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("factor_type", sa.String(100), nullable=True),
        sa.Column("blacklist_operators", sa.JSON(), nullable=True),
        sa.Column("blacklist_fields", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("attachment_urls", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_seed_factors_name"),
    )
    op.create_index(
        "ix_seed_factors_market_universe_status",
        "seed_factors",
        ["market", "universe", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_seed_factors_market_universe_status", table_name="seed_factors")
    op.drop_table("seed_factors")
