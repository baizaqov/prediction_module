"""Реестр методов прогнозирования по ТЗ ГИС ББ п. 4.10.6.2.

Каждый метод из ТЗ отображается на оценщик scikit-learn для двух режимов задачи:
регрессия (прогноз числового значения целевой переменной, например заболеваемости)
и классификация (прогноз вероятности/класса события, например вспышки).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor


class TaskType(str, Enum):
    REGRESSION = "regression"
    CLASSIFICATION = "classification"


class ForecastMethod(str, Enum):
    """Методы обработки и анализа статистических данных из ТЗ 4.10.6.2."""

    LINEAR_REGRESSION = "LINEAR_REGRESSION"        # Линейная регрессия
    LOGISTIC_REGRESSION = "LOGISTIC_REGRESSION"    # Логистическая регрессия
    DECISION_TREE = "DECISION_TREE"                # Деревья решений
    RANDOM_FOREST = "RANDOM_FOREST"                # Случайный лес
    LEAST_SQUARES = "LEAST_SQUARES"                # Метод наименьших квадратов
    KNN = "KNN"                                    # K ближайших соседей
    SVM = "SVM"                                    # Метод опорных векторов
    GRADIENT_BOOSTING = "GRADIENT_BOOSTING"        # Градиентный бустинг


# Человекочитаемые названия для UI (RU) — по формулировкам ТЗ.
METHOD_LABELS_RU: dict[ForecastMethod, str] = {
    ForecastMethod.LINEAR_REGRESSION: "Линейная регрессия",
    ForecastMethod.LOGISTIC_REGRESSION: "Логистическая регрессия",
    ForecastMethod.DECISION_TREE: "Деревья решений",
    ForecastMethod.RANDOM_FOREST: "Случайный лес",
    ForecastMethod.LEAST_SQUARES: "Метод наименьших квадратов",
    ForecastMethod.KNN: "K ближайших соседей (KNN)",
    ForecastMethod.SVM: "Метод опорных векторов (SVM)",
    ForecastMethod.GRADIENT_BOOSTING: "Градиентный бустинг",
}


@dataclass(frozen=True)
class MethodSpec:
    method: ForecastMethod
    # Фабрики оценщиков; None означает, что метод неприменим в этом режиме задачи
    # (логистическая регрессия — только классификация).
    regressor: Callable[..., Any] | None
    classifier: Callable[..., Any] | None
    # Гиперпараметры, которые пользователь может менять из интерфейса (ТЗ: "изменение
    # параметров прогнозирования"), с безопасными значениями по умолчанию.
    tunable_params: dict[str, Any]


_REGISTRY: dict[ForecastMethod, MethodSpec] = {
    ForecastMethod.LINEAR_REGRESSION: MethodSpec(
        ForecastMethod.LINEAR_REGRESSION,
        regressor=LinearRegression,
        classifier=None,
        tunable_params={},
    ),
    ForecastMethod.LEAST_SQUARES: MethodSpec(
        # МНК = обыкновенная линейная регрессия, минимизирующая сумму квадратов ошибок.
        ForecastMethod.LEAST_SQUARES,
        regressor=LinearRegression,
        classifier=None,
        tunable_params={},
    ),
    ForecastMethod.LOGISTIC_REGRESSION: MethodSpec(
        ForecastMethod.LOGISTIC_REGRESSION,
        regressor=None,
        classifier=lambda **kw: LogisticRegression(max_iter=1000, **kw),
        tunable_params={"C": 1.0},
    ),
    ForecastMethod.DECISION_TREE: MethodSpec(
        ForecastMethod.DECISION_TREE,
        regressor=DecisionTreeRegressor,
        classifier=DecisionTreeClassifier,
        tunable_params={"max_depth": None, "min_samples_leaf": 1},
    ),
    ForecastMethod.RANDOM_FOREST: MethodSpec(
        ForecastMethod.RANDOM_FOREST,
        regressor=RandomForestRegressor,
        classifier=RandomForestClassifier,
        tunable_params={"n_estimators": 300, "max_depth": None},
    ),
    ForecastMethod.KNN: MethodSpec(
        ForecastMethod.KNN,
        regressor=KNeighborsRegressor,
        classifier=KNeighborsClassifier,
        tunable_params={"n_neighbors": 5},
    ),
    ForecastMethod.SVM: MethodSpec(
        ForecastMethod.SVM,
        regressor=SVR,
        classifier=SVC,
        tunable_params={"C": 1.0, "kernel": "rbf"},
    ),
    ForecastMethod.GRADIENT_BOOSTING: MethodSpec(
        ForecastMethod.GRADIENT_BOOSTING,
        regressor=GradientBoostingRegressor,
        classifier=GradientBoostingClassifier,
        tunable_params={"n_estimators": 300, "learning_rate": 0.05, "max_depth": 3},
    ),
}

# Метод по умолчанию для baseline-прогноза (устойчив, хорошо работает на табличных
# данных с сезонностью — подходит для заболеваемости ООИ на синтетике MVP).
DEFAULT_METHOD = ForecastMethod.GRADIENT_BOOSTING


class UnsupportedMethodError(ValueError):
    pass


def build_estimator(
    method: ForecastMethod,
    task: TaskType,
    params: dict[str, Any] | None = None,
) -> Any:
    """Создать не обученный оценщик sklearn для метода/режима задачи.

    ``params`` перекрывает значения по умолчанию; неизвестные ключи отбрасываются,
    чтобы недоверенный ввод из интерфейса не мог сломать конструктор.
    """
    spec = _REGISTRY.get(method)
    if spec is None:
        raise UnsupportedMethodError(f"Неизвестный метод прогнозирования: {method}")

    factory = spec.regressor if task == TaskType.REGRESSION else spec.classifier
    if factory is None:
        raise UnsupportedMethodError(
            f"Метод {METHOD_LABELS_RU[method]} не поддерживает режим задачи '{task.value}'"
        )

    merged = dict(spec.tunable_params)
    if params:
        merged.update({k: v for k, v in params.items() if k in spec.tunable_params})
    return factory(**merged)


def available_methods(task: TaskType) -> list[dict[str, Any]]:
    """Каталог методов для конкретного режима задачи — для наполнения UI."""
    out: list[dict[str, Any]] = []
    for method, spec in _REGISTRY.items():
        supported = (
            spec.regressor if task == TaskType.REGRESSION else spec.classifier
        ) is not None
        if not supported:
            continue
        out.append(
            {
                "code": method.value,
                "label": METHOD_LABELS_RU[method],
                "tunableParams": spec.tunable_params,
                "isDefault": method == DEFAULT_METHOD,
            }
        )
    return out
