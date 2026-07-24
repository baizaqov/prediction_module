"""ORM-модели домена оценки рисков (схема ``bb_risk``).

Отдельная база/метаданные (``RiskBase``) на схему bb_risk, независимая от домена
прогнозирования (схема forecast). Под SQLite (тесты) схема не применяется. Типы —
переносимые (JSON, а не JSONB; autoincrement, а не BIGSERIAL), чтобы тесты на SQLite
работали без PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, MetaData, String, Text
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
    """Фактор риска инфекции (каталог загружается из app/risk/data/<code>.json)."""

    __tablename__ = "factor"

    infection_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    no: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(Text)
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


class Assessment(RiskBase):
    """Оценка региона по инфекции за период: набор выставленных баллов по факторам."""

    __tablename__ = "assessment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    infection_code: Mapped[str] = mapped_column(String(32), index=True)
    region_code: Mapped[str] = mapped_column(String(16), index=True)  # КАТО региона/района
    period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    panel: Mapped[str] = mapped_column(String(16), default="basic")   # basic|extended|full
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[dict] = mapped_column(JSON, default=dict)


class AssessmentScore(RiskBase):
    """Балл 0..4, выставленный фактору в рамках оценки."""

    __tablename__ = "assessment_score"

    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessment.id", ondelete="CASCADE"), primary_key=True)
    factor_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    score: Mapped[int] = mapped_column(Integer)
