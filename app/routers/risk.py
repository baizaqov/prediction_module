"""Оценка биологических рисков (факторно-балльная модель, ТЗ 4.10.6).

Каталоги факторов по ООИ, расчёт интегрального показателя и уровня риска,
сохранение оценок регионов. Пороги/веса рабочие — подлежат экспертной валидации.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import ForecastError
from ..roles import READ_ROLES, WRITE_ROLES
from ..risk import service
from ..risk.schemas import (
    AssessmentRequest,
    AssessmentResultOut,
    AssessmentSummaryOut,
    FactorOut,
    InfectionOut,
    Panel,
)
from ..schemas import PageResponse
from ..security import PrincipalDep, require_roles

router = APIRouter(prefix="/v1/risk", tags=["risk"])

SessionDep = Annotated[Session, Depends(get_session)]


def _infection_out(i) -> InfectionOut:
    return InfectionOut(
        code=i.code, nameRu=i.name_ru, pathogen=i.pathogen, pathogenGroup=i.pathogen_group,
        factorsTotal=i.factors_total, factorsBasic=i.factors_basic,
        factorsExtended=i.factors_extended, redTriggers=i.red_triggers,
    )


def _factor_out(f) -> FactorOut:
    return FactorOut(
        no=f.no, category=f.category, name=f.name, type=f.type, weight=f.weight,
        tier=f.tier, redTrigger=f.red_trigger, direction=f.direction,
        factorClass=f.factor_class, scale=f.scale or {}, measures=f.measures,
        normativeDoc=f.normative_doc, responsible=f.responsible, sourceData=f.source_data,
    )


@router.get("/infections", response_model=list[InfectionOut],
            summary="Список ООИ с факторной оценкой риска")
def list_infections(session: SessionDep, principal: PrincipalDep,
                    _=Depends(require_roles(*READ_ROLES))):
    return [_infection_out(i) for i in service.list_infections(session)]


@router.get("/infections/{code}/factors", response_model=list[FactorOut],
            summary="Каталог факторов инфекции по панели")
def list_factors(code: str, session: SessionDep, principal: PrincipalDep,
                 panel: Panel = Query(Panel.full, description="basic | extended | full"),
                 _=Depends(require_roles(*READ_ROLES))):
    if service.get_infection(session, code) is None:
        raise ForecastError(f"Неизвестная инфекция: {code}", status_code=404, error_type="NOT_FOUND")
    return [_factor_out(f) for f in service.list_factors(session, code, panel.value, principal)]


@router.get("/assessments", response_model=PageResponse,
            summary="Сохранённые оценки риска (список)")
def list_assessments(session: SessionDep, principal: PrincipalDep,
                     infectionCode: str | None = Query(None, description="Код инфекции"),
                     regionCode: str | None = Query(None, description="Код региона (КАТО)"),
                     period: str | None = Query(None, description="Отчётный период"),
                     page: int = Query(0, ge=0),
                     size: int = Query(20, ge=1, le=200),
                     _=Depends(require_roles(*READ_ROLES))):
    items, total = service.list_assessments(
        session,
        infection_code=infectionCode,
        region_code=regionCode,
        period=period,
        page=page,
        size=size,
    )
    content = [AssessmentSummaryOut(**item) for item in items]
    return PageResponse(content=content, page=page, size=size, totalElements=total)


@router.post("/assessments/preview", response_model=AssessmentResultOut,
             summary="Рассчитать показатель без сохранения (для интерактивного калькулятора)")
def preview_assessment(body: AssessmentRequest, session: SessionDep, principal: PrincipalDep,
                       _=Depends(require_roles(*READ_ROLES))):
    try:
        return service.assess(session, body, principal, persist=False)
    except service.FactorAccessDenied as exc:
        raise ForecastError(str(exc), status_code=403, error_type="ACCESS_DENIED") from exc
    except ValueError as exc:
        raise ForecastError(str(exc)) from exc


@router.post("/assessments", response_model=AssessmentResultOut,
             summary="Сохранить оценку региона и вернуть результат расчёта")
def create_assessment(body: AssessmentRequest, session: SessionDep, principal: PrincipalDep,
                      _=Depends(require_roles(*WRITE_ROLES))):
    try:
        return service.assess(session, body, principal, persist=True)
    except service.FactorAccessDenied as exc:
        raise ForecastError(str(exc), status_code=403, error_type="ACCESS_DENIED") from exc
    except ValueError as exc:
        raise ForecastError(str(exc)) from exc
