"""T-26: версия записи реестра — пересчёт создаёт новую строку вместо перезаписи.

Revision ID: a4e8d1f5c2b7
Revises: f3a2c9d7e1b4
Create Date: 2026-08-19

ЧЕРНОВИК, НЕ ПРИМЕНЁН НИ К ОДНОЙ БД.

ADD COLUMN с server_default=1 — безопасно для существующих строк: все имеющиеся оценки
станут version=1, что корректно (они и были единственной/первой версией своей записи
реестра). Новый CHECK (version >= 1) на существующих данных не нарушается.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4e8d1f5c2b7"
down_revision: Union[str, None] = "f3a2c9d7e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assessment",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="bb_risk",
    )
    op.create_check_constraint(
        "ck_bb_risk_assessment_version_positive", "assessment", "version >= 1", schema="bb_risk",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bb_risk_assessment_version_positive", "assessment", schema="bb_risk")
    op.drop_column("assessment", "version", schema="bb_risk")
