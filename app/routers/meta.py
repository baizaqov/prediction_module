"""Справочные эндпоинты: каталог методов и инструкции (ТЗ 4.10.6.2 — «инструкции и
пояснения» для пользователей с разным уровнем подготовки)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..ml.registry import TaskType, available_methods
from ..roles import READ_ROLES
from ..schemas import MethodInfo
from ..security import require_roles

router = APIRouter(prefix="/v1", tags=["meta"])


@router.get("/methods", response_model=list[MethodInfo], summary="Каталог методов прогнозирования")
def methods(
    task: TaskType = Query(TaskType.REGRESSION, description="Режим задачи"),
    _=Depends(require_roles(*READ_ROLES)),
):
    return available_methods(task)


@router.get("/help", summary="Инструкции и пояснения по прогнозированию")
def help_text(_=Depends(require_roles(*READ_ROLES))) -> dict:
    return {
        "title": "Прогнозирование и оценка биологических рисков",
        "sections": [
            {
                "heading": "Назначение",
                "text": (
                    "Модуль строит прогноз заболеваемости особо опасными инфекциями по "
                    "регионам на основе исторических данных и климатических факторов, "
                    "чтобы поддержать своевременные управленческие решения."
                ),
            },
            {
                "heading": "Порядок прогнозирования",
                "text": (
                    "Плановое прогнозирование проводится ежегодно. Внеплановое — при ЧС "
                    "природного, техногенного и социального характера либо ухудшении "
                    "санитарно-эпидемической или эпизоотической ситуации."
                ),
            },
            {
                "heading": "Как пользоваться",
                "text": (
                    "1) Выберите метод прогнозирования и при необходимости измените его "
                    "параметры. 2) Укажите регионы, инфекцию и горизонт прогноза в месяцах. "
                    "3) Запустите прогноз — результаты доступны в виде таблиц, графиков и "
                    "слоя риска на карте, их можно сохранить."
                ),
            },
            {
                "heading": "Точность",
                "text": (
                    "Целевой порог точности модели — не менее 80%. Показатели качества "
                    "(accuracy, R², MAE, RMSE) отображаются рядом с результатом; модель "
                    "регулярно дообучается по мере поступления новых данных."
                ),
            },
        ],
    }
