"""T-09: район отдельно от региона + флаг «Обобщённо по региону».

Revision ID: f3a2c9d7e1b4
Revises: d92b7f14a5c0
Create Date: 2026-08-19

ЧЕРНОВИК, НЕ ПРИМЕНЁН НИ К ОДНОЙ БД.

Обе новые колонки безопасны для существующих строк: district_code nullable
(по умолчанию NULL — «район не выбран», третье состояние, отдельное от
«Обобщённо»), is_region_wide NOT NULL со значением по умолчанию false. В отличие от
T-06 (d92b7f14a5c0), это ADD COLUMN, а не замена существующей колонки — упасть на
имеющихся данных эта миграция не должна.

Контракт формата КАТО района (какой справочник, откуда берётся) не решён —
см. questions-for-techlead.md, п.4. Здесь используется тот же тип, что и у
region_code (String(16)), без ссылки на внешний справочник.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a2c9d7e1b4"
down_revision: Union[str, None] = "d92b7f14a5c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assessment", sa.Column("district_code", sa.String(length=16), nullable=True),
        schema="bb_risk",
    )
    op.add_column(
        "assessment",
        sa.Column("is_region_wide", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="bb_risk",
    )
    op.create_check_constraint(
        "ck_bb_risk_assessment_district_xor_region_wide", "assessment",
        "NOT (district_code IS NOT NULL AND is_region_wide = true)",
        schema="bb_risk",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_bb_risk_assessment_district_xor_region_wide", "assessment", schema="bb_risk",
    )
    op.drop_column("assessment", "is_region_wide", schema="bb_risk")
    op.drop_column("assessment", "district_code", schema="bb_risk")
