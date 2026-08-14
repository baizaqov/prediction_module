"""T-15: машиночитаемая матрица факторов и органов.

Временные данные строго повторяют столбец «Роль» Приложения 4 для 46 факторов
бруцеллёза: КСЭК 20, КВКН 13, МИО 13. В дальнейшем матрицу заменяют данными
миграциями (в том числе с несколькими органами на фактор), без изменения кода
авторизации.

Revision ID: e4c3f9a7b812
Revises: 9957c584c186
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4c3f9a7b812"
down_revision: Union[str, None] = "9957c584c186"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_KSEC = (20, *range(26, 45))
_KVKN = (6, 7, 8, 9, 10, *range(12, 20))
_MIO = (1, 2, 3, 4, 5, 11, 21, 22, 23, 24, 25, 45, 46)


def _assignments(organization_code: str, factor_numbers: tuple[int, ...]) -> list[dict]:
    return [
        {
            "infection_code": "brucellosis",
            "factor_no": factor_no,
            "organization_code": organization_code,
        }
        for factor_no in factor_numbers
    ]


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name_ru", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("code"),
        schema="bb_risk",
    )
    op.create_table(
        "factor_organization",
        sa.Column("infection_code", sa.String(length=32), nullable=False),
        sa.Column("factor_no", sa.Integer(), nullable=False),
        sa.Column("organization_code", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["infection_code", "factor_no"],
            ["bb_risk.factor.infection_code", "bb_risk.factor.no"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_code"], ["bb_risk.organization.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("infection_code", "factor_no", "organization_code"),
        schema="bb_risk",
    )

    organizations = sa.table(
        "organization",
        sa.column("code", sa.String),
        sa.column("name_ru", sa.String),
        schema="bb_risk",
    )
    op.bulk_insert(organizations, [
        {"code": "KSEC", "name_ru": "КСЭК"},
        {"code": "KVKN", "name_ru": "КВКН"},
        {"code": "MIO", "name_ru": "МИО"},
    ], multiinsert=False)

    assignments = sa.table(
        "factor_organization",
        sa.column("infection_code", sa.String),
        sa.column("factor_no", sa.Integer),
        sa.column("organization_code", sa.String),
        schema="bb_risk",
    )
    op.bulk_insert(
        assignments,
        _assignments("KSEC", _KSEC)
        + _assignments("KVKN", _KVKN)
        + _assignments("MIO", _MIO),
        multiinsert=False,
    )


def downgrade() -> None:
    op.drop_table("factor_organization", schema="bb_risk")
    op.drop_table("organization", schema="bb_risk")
