"""Pydantic-схемы API оценки биологических рисков (camelCase, как в app/schemas.py)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Panel(str, Enum):
    basic = "basic"
    extended = "extended"
    full = "full"


class InfectionOut(BaseModel):
    code: str
    nameRu: str
    pathogen: str | None = None
    pathogenGroup: str | None = None
    factorsTotal: int
    factorsBasic: int
    factorsExtended: int
    redTriggers: int


class FactorOut(BaseModel):
    no: int
    category: str
    name: str
    type: str
    weight: int
    tier: str
    redTrigger: bool
    direction: str | None = None
    factorClass: str | None = None
    scale: dict[str, str] = Field(default_factory=dict)
    measures: str | None = None
    normativeDoc: str | None = None
    responsible: str | None = None
    sourceData: str | None = None


class AssessmentRequest(BaseModel):
    infectionCode: str
    regionCode: str
    period: str | None = None
    panel: Panel = Panel.basic
    # {номер_фактора: балл 0..4}; отсутствующий фактор = не оценён
    scores: dict[int, int] = Field(default_factory=dict)


class RedTriggerOut(BaseModel):
    no: int
    name: str | None = None
    score: float


class AssessmentResultOut(BaseModel):
    assessmentId: int | None = None
    infectionCode: str
    regionCode: str
    period: str | None = None
    panel: str
    panelSize: int
    assessed: int
    notAssessed: int
    weightedSum: float
    integralIndex: float | None = None
    completeness: float
    adjustmentFactor: float
    adjustedIndex: float | None = None
    level: str
    levelRu: str
    hasRedTrigger: bool
    redTriggers: list[RedTriggerOut] = Field(default_factory=list)
    byCategory: dict[str, Any] = Field(default_factory=dict)
    byFactorClass: dict[str, Any] = Field(default_factory=dict)


class AssessmentSummaryOut(BaseModel):
    """Строка списка сохранённых оценок (GET /v1/risk/assessments).

    Уровень и признак триггера — снимок результата расчёта на момент сохранения оценки
    (T-07), читаются из БД как есть, см. service.list_assessments.
    """
    id: int
    infectionCode: str
    infectionNameRu: str
    regionCode: str
    period: str | None = None
    panel: str
    level: str
    levelRu: str
    hasRedTrigger: bool
    assessed: int
    createdAt: datetime
