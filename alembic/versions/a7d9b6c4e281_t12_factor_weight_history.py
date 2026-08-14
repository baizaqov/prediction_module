"""T-12: append-only история изменения весов факторов.

Revision ID: a7d9b6c4e281
Revises: e4c3f9a7b812
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d9b6c4e281"
down_revision: Union[str, None] = "e4c3f9a7b812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "factor_weight_change",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("infection_code", sa.String(length=32), nullable=False),
        sa.Column("factor_no", sa.Integer(), nullable=False),
        sa.Column("old_weight", sa.Integer(), nullable=False),
        sa.Column("new_weight", sa.Integer(), nullable=False),
        sa.Column("author", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="bb_risk",
    )
    op.create_index(
        "ix_bb_risk_factor_weight_change_factor",
        "factor_weight_change",
        ["infection_code", "factor_no"],
        unique=False,
        schema="bb_risk",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bb_risk_factor_weight_change_factor",
        table_name="factor_weight_change",
        schema="bb_risk",
    )
    op.drop_table("factor_weight_change", schema="bb_risk")
