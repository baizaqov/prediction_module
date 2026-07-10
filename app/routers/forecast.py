"""Функции прогнозирования, обучения моделей и визуализации (ТЗ 4.10.6.2 / 4.10.6.3)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import ForecastError
from ..ml.registry import METHOD_LABELS_RU
from ..roles import READ_ROLES, WRITE_ROLES
from ..schemas import (
    ForecastRequest,
    ForecastResultOut,
    ModelOut,
    PageResponse,
    RunSummaryOut,
    TrainRequest,
)
from ..security import PrincipalDep, require_roles
from ..services import forecast_service

router = APIRouter(prefix="/v1", tags=["forecast"])

SessionDep = Annotated[Session, Depends(get_session)]


def _model_out(m) -> ModelOut:
    return ModelOut(
        id=m.id,
        method=m.method,
        methodLabel=METHOD_LABELS_RU.get(m.method, m.method),
        taskType=m.task_type,
        params=m.params,
        metrics=m.metrics,
        accuracy=m.accuracy,
        meetsAccuracyTarget=m.meets_accuracy_target,
        nTrain=m.n_train,
        nTest=m.n_test,
        trainedAt=m.trained_at,
    )


@router.post("/models/train", response_model=ModelOut, summary="Обучить модель прогнозирования")
def train(
    body: TrainRequest,
    session: SessionDep,
    principal: PrincipalDep,
    _=Depends(require_roles(*WRITE_ROLES)),
):
    try:
        model = forecast_service.train_model(
            session, body.method, body.params, body.testMonths, principal
        )
    except ValueError as exc:
        raise ForecastError(str(exc)) from exc
    return _model_out(model)


@router.post("/forecast/run", response_model=ForecastResultOut, summary="Запустить прогноз")
def run_forecast(
    body: ForecastRequest,
    session: SessionDep,
    principal: PrincipalDep,
    _=Depends(require_roles(*WRITE_ROLES)),
):
    try:
        return forecast_service.run_forecast(session, body, principal)
    except ValueError as exc:
        raise ForecastError(str(exc)) from exc


@router.get("/forecast/runs", response_model=PageResponse, summary="Сохранённые прогоны прогноза")
def list_runs(
    session: SessionDep,
    _=Depends(require_roles(*READ_ROLES)),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=200),
):
    rows, total = forecast_service.list_runs(session, page, size)
    content = [
        RunSummaryOut(
            id=r.id,
            method=r.method,
            planningType=r.planning_type,
            diseaseCode=r.disease_code,
            horizonMonths=r.horizon_months,
            accuracy=r.metrics.get("accuracy", 0.0),
            createdAt=r.created_at,
        )
        for r in rows
    ]
    return PageResponse(content=content, page=page, size=size, totalElements=total)


@router.get("/forecast/runs/{run_id}", response_model=ForecastResultOut,
            summary="Результат сохранённого прогона")
def get_run(
    run_id: str,
    session: SessionDep,
    _=Depends(require_roles(*READ_ROLES)),
):
    run = forecast_service.get_run(session, run_id)
    if run is None:
        raise ForecastError("Прогон прогноза не найден", status_code=404, error_type="VALIDATION")
    payload = dict(run.result)
    payload["id"] = run.id
    payload["createdAt"] = run.created_at
    return payload
