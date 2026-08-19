"""T-06: период оценки — periodFrom/periodTo вместо свободной строки.

Revision ID: d92b7f14a5c0
Revises: c1f4a8e2b6d3
Create Date: 2026-08-19

ЧЕРНОВИК, НЕ ПРИМЕНЁН НИ К ОДНОЙ БД.

ВАЖНО перед применением: новые колонки NOT NULL, а старая ``period`` (свободная строка
вида "2026-J1") удаляется. Автоматического способа превратить произвольную строку в
корректную дату нет — если в bb_risk.assessment реальной среды уже есть строки, эта
миграция на них упадёт (осознанно, как fail-safe, а не тихая потеря данных). Перед
upgrade нужно проверить `SELECT count(*) FROM bb_risk.assessment` на целевой БД:
пусто — миграция применится как есть; есть строки — сначала нужен отдельный backfill
(period_from/period_to как nullable, ручной перенос данных, только потом NOT NULL) —
это отдельное решение, не входящее в этот черновик.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d92b7f14a5c0"
down_revision: Union[str, None] = "c1f4a8e2b6d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assessment", sa.Column("period_from", sa.Date(), nullable=False), schema="bb_risk",
    )
    op.add_column(
        "assessment", sa.Column("period_to", sa.Date(), nullable=False), schema="bb_risk",
    )
    op.create_check_constraint(
        "ck_bb_risk_assessment_period_range", "assessment", "period_to >= period_from",
        schema="bb_risk",
    )
    op.create_index(
        "ix_bb_risk_assessment_period_from", "assessment", ["period_from"], schema="bb_risk",
    )
    op.drop_column("assessment", "period", schema="bb_risk")


def downgrade() -> None:
    op.add_column(
        "assessment", sa.Column("period", sa.String(length=32), nullable=True), schema="bb_risk",
    )
    op.drop_index("ix_bb_risk_assessment_period_from", table_name="assessment", schema="bb_risk")
    op.drop_constraint("ck_bb_risk_assessment_period_range", "assessment", schema="bb_risk")
    op.drop_column("assessment", "period_to", schema="bb_risk")
    op.drop_column("assessment", "period_from", schema="bb_risk")
