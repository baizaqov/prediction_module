"""T-08: CHECK-ограничения целостности (score, weight, type, tier) и лимит имени фактора.

Revision ID: c1f4a8e2b6d3
Revises: a7d9b6c4e281
Create Date: 2026-08-19

ЧЕРНОВИК, НЕ ПРИМЕНЁН НИ К ОДНОЙ БД. Перед `alembic upgrade` на реальном контуре
нужна проверка на копии/staging Postgres — SQLite (на котором идут тесты этого
репозитория) не проверяет ALTER TABLE ADD CONSTRAINT так же, как Postgres, и не
проверяет длину VARCHAR вовсе. Предварительная сверка данных выполнена: все 707
факторов действующих 13 каталогов (app/risk/data/*.json) укладываются в 1..4 по весу,
enum по type/tier и не длиннее 204 символов в имени — миграция не должна упасть на
уже загруженных данных, но это не заменяет проверку на реальном Postgres.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1f4a8e2b6d3"
down_revision: Union[str, None] = "a7d9b6c4e281"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "factor", "name",
        existing_type=sa.Text(),
        type_=sa.String(length=250),
        schema="bb_risk",
    )
    op.create_check_constraint(
        "ck_bb_risk_factor_weight_range", "factor", "weight BETWEEN 1 AND 4", schema="bb_risk",
    )
    op.create_check_constraint(
        "ck_bb_risk_factor_type", "factor", "type IN ('numeric', 'binary')", schema="bb_risk",
    )
    op.create_check_constraint(
        "ck_bb_risk_factor_tier", "factor", "tier IN ('basic', 'extended')", schema="bb_risk",
    )
    op.create_check_constraint(
        "ck_bb_risk_assessment_score_range", "assessment_score", "score BETWEEN 0 AND 4",
        schema="bb_risk",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bb_risk_assessment_score_range", "assessment_score", schema="bb_risk")
    op.drop_constraint("ck_bb_risk_factor_tier", "factor", schema="bb_risk")
    op.drop_constraint("ck_bb_risk_factor_type", "factor", schema="bb_risk")
    op.drop_constraint("ck_bb_risk_factor_weight_range", "factor", schema="bb_risk")
    op.alter_column(
        "factor", "name",
        existing_type=sa.String(length=250),
        type_=sa.Text(),
        schema="bb_risk",
    )
