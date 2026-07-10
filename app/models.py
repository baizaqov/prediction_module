"""ORM-модели домена прогнозирования (схема ``forecast``)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ClimateObservation(Base):
    """Климатические и синоптические наблюдения (ТЗ 4.10.6.1, источник — Казгидромет)."""

    __tablename__ = "climate_observation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_code: Mapped[str] = mapped_column(String(16), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    temp_c: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    precip_mm: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="SYNTHETIC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ForecastModel(Base):
    """Обученная модель: метод, гиперпараметры, метрики и сериализованный артефакт."""

    __tablename__ = "forecast_model"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    method: Mapped[str] = mapped_column(String(32))
    task_type: Mapped[str] = mapped_column(String(16), default="regression")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_names: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    meets_accuracy_target: Mapped[bool] = mapped_column(Boolean, default=False)
    n_train: Mapped[int] = mapped_column(Integer, default=0)
    n_test: Mapped[int] = mapped_column(Integer, default=0)
    dataset_signature: Mapped[str] = mapped_column(String(64), default="")
    artifact: Mapped[bytes] = mapped_column(LargeBinary)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    trained_by: Mapped[dict] = mapped_column(JSON, default=dict)


class ForecastRun(Base):
    """Сохранённый прогон прогноза (ТЗ: «функция сохранения результатов»).

    ``planning_type`` — плановое (ежегодное) или внеплановое прогнозирование (ТЗ 4.10.6).
    ``result`` хранит таблицы/ряды и гео-слой для визуализации на карте (ТЗ 4.10.6.3).
    """

    __tablename__ = "forecast_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    method: Mapped[str] = mapped_column(String(32))
    planning_type: Mapped[str] = mapped_column(String(16), default="UNPLANNED")
    disease_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    regions: Mapped[list] = mapped_column(JSON, default=list)
    horizon_months: Mapped[int] = mapped_column(Integer, default=6)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[dict] = mapped_column(JSON, default=dict)
