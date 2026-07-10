"""Пайплайн обучения и прогнозирования.

Пул всех регионов обучает одну модель; признаки — сезонность, климатические факторы
и лаги заболеваемости (лаги несут региональный уровень, поэтому отдельная модель на
регион не нужна). Прогноз горизонта строится рекурсивно: предсказанное значение
становится лагом для следующего шага, а будущий климат берётся из климатической нормы
(заглушка «прогноза Казгидромета» до подключения реального источника).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .registry import ForecastMethod, TaskType, build_estimator
from .synthetic import CLIMATE_COLUMNS, TARGET_COLUMN

LAG_1 = "lag_1"
LAG_12 = "lag_12"
ROLL_3 = "roll_3"
MONTH_SIN = "month_sin"
MONTH_COS = "month_cos"

FEATURE_COLUMNS = [MONTH_SIN, MONTH_COS, *CLIMATE_COLUMNS, LAG_1, LAG_12, ROLL_3]


@dataclass
class TrainResult:
    estimator: Any
    metrics: dict[str, float]
    feature_names: list[str]
    n_train: int
    n_test: int
    meets_accuracy_target: bool


@dataclass
class ForecastPoint:
    period: pd.Timestamp
    predicted: float


@dataclass
class RegionForecast:
    region_code: str
    history: list[ForecastPoint] = field(default_factory=list)
    forecast: list[ForecastPoint] = field(default_factory=list)


def _add_time_features(g: pd.DataFrame) -> pd.DataFrame:
    month = g["period"].dt.month
    g[MONTH_SIN] = np.sin(2 * np.pi * month / 12.0)
    g[MONTH_COS] = np.cos(2 * np.pi * month / 12.0)
    return g


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Развернуть панельные данные в обучающую таблицу с лагами по каждому региону."""
    frames: list[pd.DataFrame] = []
    for _, g in df.sort_values(["region_code", "period"]).groupby("region_code"):
        g = g.copy()
        g = _add_time_features(g)
        g[LAG_1] = g[TARGET_COLUMN].shift(1)
        g[LAG_12] = g[TARGET_COLUMN].shift(12)
        g[ROLL_3] = g[TARGET_COLUMN].shift(1).rolling(3).mean()
        frames.append(g)
    out = pd.concat(frames, ignore_index=True)
    return out.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)


def _accuracy_from_mape(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    denom = np.maximum(np.abs(y_true), 1e-6)
    mape = float(np.mean(np.abs((y_true - y_pred) / denom)))
    accuracy = float(np.clip(1.0 - mape, 0.0, 1.0))
    return mape, accuracy


def train_and_evaluate(
    df: pd.DataFrame,
    method: ForecastMethod,
    params: dict[str, Any] | None = None,
    test_months: int = 12,
    accuracy_target: float = 0.80,
) -> TrainResult:
    """Обучить модель и оценить на удержанном хвосте временного ряда.

    Разбиение — по времени (последние ``test_months`` месяцев в тест), чтобы оценка не
    подсматривала будущее. Порог точности из ТЗ 4.10.6.2 — не менее 80 %.
    """
    feat = build_features(df)
    cutoff = feat["period"].max() - pd.DateOffset(months=test_months)
    train = feat[feat["period"] <= cutoff]
    test = feat[feat["period"] > cutoff]
    if train.empty or test.empty:
        raise ValueError("Недостаточно данных для разбиения на обучение и контроль")

    estimator = build_estimator(method, TaskType.REGRESSION, params)
    estimator.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN])
    pred = estimator.predict(test[FEATURE_COLUMNS])

    y_true = test[TARGET_COLUMN].to_numpy()
    rmse = float(np.sqrt(mean_squared_error(y_true, pred)))
    mae = float(mean_absolute_error(y_true, pred))
    r2 = float(r2_score(y_true, pred))
    mape, accuracy = _accuracy_from_mape(y_true, pred)

    metrics = {
        "accuracy": round(accuracy, 4),
        "r2": round(r2, 4),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape": round(mape, 4),
    }
    return TrainResult(
        estimator=estimator,
        metrics=metrics,
        feature_names=FEATURE_COLUMNS,
        n_train=len(train),
        n_test=len(test),
        meets_accuracy_target=accuracy >= accuracy_target,
    )


def _climate_normals(df: pd.DataFrame, region: str) -> dict[int, dict[str, float]]:
    """Средний климат по месяцу — заглушка прогноза климата на будущие периоды."""
    g = df[df["region_code"] == region].copy()
    g["month"] = g["period"].dt.month
    normals = g.groupby("month")[CLIMATE_COLUMNS].mean()
    return {int(m): row.to_dict() for m, row in normals.iterrows()}


def forecast_region(
    estimator: Any,
    df: pd.DataFrame,
    region: str,
    horizon: int,
) -> RegionForecast:
    """Рекурсивный прогноз заболеваемости для региона на ``horizon`` месяцев вперёд."""
    g = df[df["region_code"] == region].sort_values("period").reset_index(drop=True)
    if g.empty:
        raise ValueError(f"Нет исторических данных по региону {region}")

    normals = _climate_normals(df, region)
    series = list(g[TARGET_COLUMN].to_numpy())
    last_period = g["period"].max()

    result = RegionForecast(
        region_code=region,
        history=[
            ForecastPoint(period=p, predicted=float(v))
            for p, v in zip(g["period"], g[TARGET_COLUMN])
        ],
    )

    for step in range(1, horizon + 1):
        period = last_period + pd.DateOffset(months=step)
        month = period.month
        clim = normals.get(month, {c: float(np.mean(g[c])) for c in CLIMATE_COLUMNS})

        lag_1 = series[-1]
        lag_12 = series[-12] if len(series) >= 12 else series[0]
        roll_3 = float(np.mean(series[-3:])) if len(series) >= 3 else float(np.mean(series))

        features = {
            MONTH_SIN: np.sin(2 * np.pi * month / 12.0),
            MONTH_COS: np.cos(2 * np.pi * month / 12.0),
            "temp_c": clim["temp_c"],
            "humidity": clim["humidity"],
            "precip_mm": clim["precip_mm"],
            LAG_1: lag_1,
            LAG_12: lag_12,
            ROLL_3: roll_3,
        }
        x = pd.DataFrame([[features[c] for c in FEATURE_COLUMNS]], columns=FEATURE_COLUMNS)
        yhat = max(0.0, float(estimator.predict(x)[0]))
        series.append(yhat)
        result.forecast.append(ForecastPoint(period=period, predicted=round(yhat, 2)))

    return result
