"""Pydantic-схемы запросов и ответов API прогнозирования."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .ml.registry import DEFAULT_METHOD, ForecastMethod


class PlanningType(str, Enum):
    """Порядок прогнозирования по ТЗ 4.10.6."""

    PLANNED = "PLANNED"      # плановое (ежегодное)
    UNPLANNED = "UNPLANNED"  # внеплановое (ЧС, ухудшение ситуации)


# --- Каталог методов и справочные данные ---------------------------------------

class MethodInfo(BaseModel):
    code: str
    label: str
    tunableParams: dict[str, Any]
    isDefault: bool


# --- Климат ---------------------------------------------------------------------

class ClimateRefreshRequest(BaseModel):
    regions: list[str] | None = Field(None, description="Коды регионов; None — все")
    fromPeriod: date | None = None
    toPeriod: date | None = None


class ClimateObservationOut(BaseModel):
    regionCode: str
    period: date
    tempC: float
    humidity: float
    precipMm: float
    source: str


class ClimateRefreshResult(BaseModel):
    ingested: int
    source: str
    regions: list[str]


# --- Обучение модели ------------------------------------------------------------

class TrainRequest(BaseModel):
    method: ForecastMethod = DEFAULT_METHOD
    params: dict[str, Any] = Field(default_factory=dict)
    testMonths: int = Field(12, ge=1, le=36)


class ModelOut(BaseModel):
    id: str
    method: str
    methodLabel: str
    taskType: str
    params: dict[str, Any]
    metrics: dict[str, float]
    accuracy: float
    meetsAccuracyTarget: bool
    nTrain: int
    nTest: int
    trainedAt: datetime


# --- Прогноз --------------------------------------------------------------------

class ForecastRequest(BaseModel):
    method: ForecastMethod = DEFAULT_METHOD
    params: dict[str, Any] = Field(default_factory=dict)
    regions: list[str] | None = Field(None, description="Коды регионов; None — все")
    diseaseCode: str | None = Field(None, description="Код ООИ (целевая переменная)")
    horizonMonths: int = Field(6, ge=1, le=24)
    planningType: PlanningType = PlanningType.UNPLANNED
    modelId: str | None = Field(None, description="Готовая модель; иначе обучается новая")
    save: bool = Field(True, description="Сохранить результат прогона")


class SeriesPoint(BaseModel):
    period: date
    value: float


class RegionForecastOut(BaseModel):
    regionCode: str
    history: list[SeriesPoint]
    forecast: list[SeriesPoint]
    peakValue: float
    peakPeriod: date | None


class GeoFeatureOut(BaseModel):
    """Слой для карты (ТЗ 4.10.6.3): агрегированный риск/прогноз по региону."""

    regionCode: str
    forecastMean: float
    forecastPeak: float
    riskLevel: str  # LOW | MEDIUM | HIGH


class ForecastResultOut(BaseModel):
    id: str | None
    method: str
    methodLabel: str
    planningType: PlanningType
    diseaseCode: str | None
    horizonMonths: int
    metrics: dict[str, float]
    accuracy: float
    meetsAccuracyTarget: bool
    regions: list[RegionForecastOut]
    geo: list[GeoFeatureOut]
    createdAt: datetime | None


class RunSummaryOut(BaseModel):
    id: str
    method: str
    planningType: str
    diseaseCode: str | None
    horizonMonths: int
    accuracy: float
    createdAt: datetime


class PageResponse(BaseModel):
    """Совместимо с общей пагинацией платформы PageResponse<T>."""

    content: list[Any]
    page: int
    size: int
    totalElements: int
