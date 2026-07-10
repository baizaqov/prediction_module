"""Тесты ML-ядра: методы, точность, прогноз."""
from app.ml import pipeline
from app.ml.registry import (
    DEFAULT_METHOD,
    ForecastMethod,
    TaskType,
    available_methods,
    build_estimator,
)
from app.ml.synthetic import default_dataset


def test_all_tz_methods_registered():
    # Все 8 методов ТЗ 4.10.6.2 присутствуют.
    assert len(ForecastMethod) == 8
    reg_methods = {m["code"] for m in available_methods(TaskType.REGRESSION)}
    # Логистическая регрессия — только классификация.
    assert ForecastMethod.LOGISTIC_REGRESSION.value not in reg_methods
    cls_methods = {m["code"] for m in available_methods(TaskType.CLASSIFICATION)}
    assert ForecastMethod.LOGISTIC_REGRESSION.value in cls_methods


def test_build_estimator_drops_unknown_params():
    est = build_estimator(ForecastMethod.RANDOM_FOREST, TaskType.REGRESSION,
                          {"n_estimators": 50, "__injected__": "x"})
    assert est.n_estimators == 50


def test_baseline_meets_accuracy_target():
    df = default_dataset()
    result = pipeline.train_and_evaluate(df, DEFAULT_METHOD)
    assert result.metrics["accuracy"] >= 0.80
    assert result.meets_accuracy_target is True


def test_forecast_horizon_length():
    df = default_dataset()
    est = pipeline.train_and_evaluate(df, DEFAULT_METHOD).estimator
    rf = pipeline.forecast_region(est, df, "KZ-01", horizon=6)
    assert len(rf.forecast) == 6
    assert all(p.predicted >= 0 for p in rf.forecast)
