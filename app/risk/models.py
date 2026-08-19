"""ORM-модели домена оценки рисков (схема ``bb_risk``).

Отдельная база/метаданные (``RiskBase``) на схему bb_risk, независимая от домена
прогнозирования (схема forecast). Под SQLite (тесты) схема не применяется. Типы —
переносимые (JSON, а не JSONB; autoincrement, а не BIGSERIAL), чтобы тесты на SQLite
работали без PostgreSQL.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index,
    Integer, MetaData, String, Text, event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import _is_sqlite

_RISK_SCHEMA = None if _is_sqlite else "bb_risk"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RiskBase(DeclarativeBase):
    metadata = MetaData(schema=_RISK_SCHEMA)


class Infection(RiskBase):
    """Справочник ООИ, для которых ведётся факторная оценка риска."""

    __tablename__ = "infection"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(255))
    pathogen: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pathogen_group: Mapped[str | None] = mapped_column(String(8), nullable=True)
    factors_total: Mapped[int] = mapped_column(Integer, default=0)
    factors_basic: Mapped[int] = mapped_column(Integer, default=0)
    factors_extended: Mapped[int] = mapped_column(Integer, default=0)
    red_triggers: Mapped[int] = mapped_column(Integer, default=0)


class Factor(RiskBase):
    """Фактор риска инфекции (каталог загружается из app/risk/data/<code>.json).

    Ограничения T-08 — на уровне БД, не только приложения: 707 факторов действующих 13
    каталогов проверены перед вводом ограничения, ни один не нарушает ни одно из них.
    """

    __tablename__ = "factor"
    __table_args__ = (
        CheckConstraint("weight BETWEEN 1 AND 4", name="ck_bb_risk_factor_weight_range"),
        CheckConstraint("type IN ('numeric', 'binary')", name="ck_bb_risk_factor_type"),
        CheckConstraint("tier IN ('basic', 'extended')", name="ck_bb_risk_factor_tier"),
    )

    infection_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    no: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(250))  # BR-037; максимум в действующих каталогах — 204
    type: Mapped[str] = mapped_column(String(16))          # numeric | binary
    weight: Mapped[int] = mapped_column(Integer)           # 1..4
    tier: Mapped[str] = mapped_column(String(16))          # basic | extended
    red_trigger: Mapped[bool] = mapped_column(Boolean, default=False)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    factor_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scale: Mapped[dict] = mapped_column(JSON, default=dict)
    measures: Mapped[str | None] = mapped_column(Text, nullable=True)
    normative_doc: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_data: Mapped[str | None] = mapped_column(Text, nullable=True)


class Organization(RiskBase):
    """Орган, которому могут быть назначены факторы риска."""

    __tablename__ = "organization"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(255))


class FactorOrganization(RiskBase):
    """Машиночитаемая связь «фактор ↔ орган» (многие-ко-многим)."""

    __tablename__ = "factor_organization"
    __table_args__ = (
        ForeignKeyConstraint(
            ["infection_code", "factor_no"],
            ["factor.infection_code", "factor.no"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["organization_code"], ["organization.code"], ondelete="CASCADE"),
    )

    infection_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    factor_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_code: Mapped[str] = mapped_column(String(32), primary_key=True)


class FactorWeightChange(RiskBase):
    """Неизменяемая запись истории фактической правки веса фактора (T-12)."""

    __tablename__ = "factor_weight_change"
    __table_args__ = (
        Index("ix_bb_risk_factor_weight_change_factor", "infection_code", "factor_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    infection_code: Mapped[str] = mapped_column(String(32))
    factor_no: Mapped[int] = mapped_column(Integer)
    old_weight: Mapped[int] = mapped_column(Integer)
    new_weight: Mapped[int] = mapped_column(Integer)
    author: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


@event.listens_for(FactorWeightChange, "before_update")
def _prevent_factor_weight_change_update(_, __, ___) -> None:
    """История весов append-only: ORM не может изменить существующую запись."""
    raise ValueError("Записи истории изменения весов нельзя изменять")


@event.listens_for(FactorWeightChange, "before_delete")
def _prevent_factor_weight_change_delete(_, __, ___) -> None:
    """История весов append-only: ORM не может удалить существующую запись."""
    raise ValueError("Записи истории изменения весов нельзя удалять")


class Assessment(RiskBase):
    """Оценка региона по инфекции за период: набор выставленных баллов по факторам.

    Результат расчёта (``panel_size``..``has_red_trigger``) заполняется из
    ``scoring.calculate_risk`` в момент сохранения (T-07) и дальше не пересчитывается:
    правка веса фактора в каталоге не должна задним числом менять уже сохранённые оценки
    (см. CLAUDE.md, «Веса и история»). Снимок весов, по которым посчитан именно этот
    результат, — в ``AssessmentScore.weight``.
    """

    __tablename__ = "assessment"
    __table_args__ = (
        CheckConstraint("period_to >= period_from", name="ck_bb_risk_assessment_period_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    infection_code: Mapped[str] = mapped_column(String(32), index=True)
    region_code: Mapped[str] = mapped_column(String(16), index=True)  # КАТО региона/района
    # Отчётный период — две обязательные даты (T-06, BR-021/022), заменяет свободную строку.
    period_from: Mapped[date] = mapped_column(Date, index=True)
    period_to: Mapped[date] = mapped_column(Date)
    panel: Mapped[str] = mapped_column(String(16), default="basic")   # basic|extended|full
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[dict] = mapped_column(JSON, default=dict)

    panel_size: Mapped[int] = mapped_column(Integer, default=0)
    assessed: Mapped[int] = mapped_column(Integer, default=0)
    integral_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)
    adjusted_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    level: Mapped[str] = mapped_column(String(16))
    level_ru: Mapped[str] = mapped_column(String(255))
    has_red_trigger: Mapped[bool] = mapped_column(Boolean, default=False)


class AssessmentScore(RiskBase):
    """Балл 0..4, выставленный фактору в рамках оценки.

    ``weight`` — снимок ``Factor.weight`` на момент сохранения оценки (T-07), а не текущее
    значение из каталога: правка веса в каталоге не должна менять состав уже сохранённого
    расчёта.
    """

    __tablename__ = "assessment_score"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 4", name="ck_bb_risk_assessment_score_range"),
    )

    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessment.id", ondelete="CASCADE"), primary_key=True)
    factor_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    score: Mapped[int] = mapped_column(Integer)
    weight: Mapped[int] = mapped_column(Integer)
