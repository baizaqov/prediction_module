"""Оркестрация прогнозирования: климат → обучение → прогноз → гео-слой → сохранение.

MVP-замечание по данным: целевая переменная (заболеваемость) и климат берутся из единой
синтетической панели (решение по данным на старте проекта). Климатические наблюдения
дополнительно материализуются в таблицу climate_observation для функции 4.10.6.1 и для
будущего джойна. Когда появятся реальные ряды из ooi-registry (emergency_notifications) и
боевой Казгидромет, обучающая панель будет собираться джойном этих источников — контракт
признаков (app.ml.pipeline.FEATURE_COLUMNS) при этом не меняется.
"""
from __future__ import annotations

import io
from datetime import date

import joblib
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..integrations.kazhydromet import KazhydrometClient
from ..ml import pipeline
from ..ml.registry import METHOD_LABELS_RU, ForecastMethod, TaskType
from ..ml.synthetic import DEFAULT_REGIONS, default_dataset
from ..models import ClimateObservation, ForecastModel, ForecastRun
from ..security import Principal


# --- Климат (ТЗ 4.10.6.1) -------------------------------------------------------

def refresh_climate(session: Session, regions: list[str] | None) -> dict:
    """Загрузить климатические наблюдения (заглушка Казгидромета) в БД."""
    client = KazhydrometClient()
    records = client.fetch(regions=regions)
    target_regions = sorted({r.region_code for r in records})

    session.execute(
        delete(ClimateObservation).where(ClimateObservation.region_code.in_(target_regions))
    )
    session.add_all(
        [
            ClimateObservation(
                region_code=r.region_code,
                period=r.period,
                temp_c=r.temp_c,
                humidity=r.humidity,
                precip_mm=r.precip_mm,
                source=r.source,
            )
            for r in records
        ]
    )
    session.commit()
    return {"ingested": len(records), "source": records[0].source if records else "",
            "regions": target_regions}


def list_climate(session: Session, region: str | None, limit: int) -> list[ClimateObservation]:
    stmt = select(ClimateObservation).order_by(
        ClimateObservation.region_code, ClimateObservation.period
    )
    if region:
        stmt = stmt.where(ClimateObservation.region_code == region)
    return list(session.execute(stmt.limit(limit)).scalars())


# --- Обучающая панель -----------------------------------------------------------

def _modeling_panel() -> pd.DataFrame:
    """Панель регион×месяц с климатом и заболеваемостью для обучения."""
    return default_dataset()


# --- Обучение модели (ТЗ 4.10.6.2) ----------------------------------------------

def train_model(
    session: Session,
    method: ForecastMethod,
    params: dict,
    test_months: int,
    principal: Principal,
) -> ForecastModel:
    panel = _modeling_panel()
    result = pipeline.train_and_evaluate(
        panel, method, params, test_months=test_months,
        accuracy_target=get_settings().accuracy_target,
    )

    buffer = io.BytesIO()
    joblib.dump(result.estimator, buffer)

    model = ForecastModel(
        method=method.value,
        task_type=TaskType.REGRESSION.value,
        params=params or {},
        feature_names=result.feature_names,
        metrics=result.metrics,
        accuracy=result.metrics["accuracy"],
        meets_accuracy_target=result.meets_accuracy_target,
        n_train=result.n_train,
        n_test=result.n_test,
        artifact=buffer.getvalue(),
        trained_by=_principal_ref(principal),
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def _load_estimator(model: ForecastModel):
    return joblib.load(io.BytesIO(model.artifact))


# --- Прогноз (ТЗ 4.10.6.2 / 4.10.6.3) -------------------------------------------

def _risk_level(peak: float, hist_mean: float, hist_std: float) -> str:
    if peak >= hist_mean + hist_std:
        return "HIGH"
    if peak >= hist_mean:
        return "MEDIUM"
    return "LOW"


def run_forecast(session: Session, req, principal: Principal) -> dict:
    panel = _modeling_panel()
    regions = req.regions or DEFAULT_REGIONS

    target = get_settings().accuracy_target

    # Модель: готовая по id или обучаем «на лету». Метод берём из самой модели, а не из
    # запроса — иначе прогон по сохранённой модели другого метода был бы промаркирован
    # значением req.method по умолчанию.
    if req.modelId:
        model = session.get(ForecastModel, req.modelId)
        if model is None:
            raise ValueError(f"Модель не найдена: {req.modelId}")
        estimator = _load_estimator(model)
        method = ForecastMethod(model.method)
        metrics = model.metrics
        accuracy = model.accuracy
        meets = model.meets_accuracy_target
        model_id = model.id
    else:
        method = req.method
        trained = pipeline.train_and_evaluate(panel, method, req.params, accuracy_target=target)
        estimator = trained.estimator
        metrics = trained.metrics
        accuracy = trained.metrics["accuracy"]
        meets = trained.meets_accuracy_target
        model_id = None

    region_outputs: list[dict] = []
    geo: list[dict] = []
    for region in regions:
        rf = pipeline.forecast_region(estimator, panel, region, req.horizonMonths)
        hist_values = [p.predicted for p in rf.history]
        fc_values = [p.predicted for p in rf.forecast]
        hist_series = pd.Series(hist_values)
        hist_mean = float(hist_series.mean())
        hist_std = float(hist_series.std(ddof=0))
        peak = max(fc_values) if fc_values else 0.0
        peak_period = (
            rf.forecast[fc_values.index(peak)].period.date() if fc_values else None
        )

        region_outputs.append(
            {
                "regionCode": region,
                "history": [{"period": p.period.date(), "value": p.predicted} for p in rf.history[-24:]],
                "forecast": [{"period": p.period.date(), "value": p.predicted} for p in rf.forecast],
                "peakValue": round(peak, 2),
                "peakPeriod": peak_period,
            }
        )
        geo.append(
            {
                "regionCode": region,
                "forecastMean": round(sum(fc_values) / len(fc_values), 2) if fc_values else 0.0,
                "forecastPeak": round(peak, 2),
                "riskLevel": _risk_level(peak, hist_mean, hist_std),
            }
        )

    result_payload = {
        "id": None,
        "method": method.value,
        "methodLabel": METHOD_LABELS_RU[method],
        "planningType": req.planningType.value,
        "diseaseCode": req.diseaseCode,
        "horizonMonths": req.horizonMonths,
        "metrics": metrics,
        "accuracy": accuracy,
        "meetsAccuracyTarget": meets,
        "regions": region_outputs,
        "geo": geo,
        "createdAt": None,
    }

    if req.save:
        run = ForecastRun(
            model_id=model_id,
            method=method.value,
            planning_type=req.planningType.value,
            disease_code=req.diseaseCode,
            regions=regions,
            horizon_months=req.horizonMonths,
            params=req.params or {},
            metrics=metrics,
            result=_jsonable(result_payload),
            created_by=_principal_ref(principal),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        result_payload["id"] = run.id
        result_payload["createdAt"] = run.created_at

    return result_payload


def list_runs(session: Session, page: int, size: int) -> tuple[list[ForecastRun], int]:
    total = session.query(ForecastRun).count()
    rows = list(
        session.execute(
            select(ForecastRun)
            .order_by(ForecastRun.created_at.desc())
            .offset(page * size)
            .limit(size)
        ).scalars()
    )
    return rows, total


def get_run(session: Session, run_id: str) -> ForecastRun | None:
    return session.get(ForecastRun, run_id)


# --- Вспомогательное ------------------------------------------------------------

def _principal_ref(principal: Principal) -> dict:
    ui = principal.user_info
    return {
        "userId": ui.user_id,
        "orgId": ui.org_id,
        "orgBin": ui.org_bin,
        "fullName": ui.full_name,
    }


def _jsonable(payload: dict) -> dict:
    """Привести даты к ISO для хранения в JSON-колонке."""
    def conv(v):
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return conv(payload)
