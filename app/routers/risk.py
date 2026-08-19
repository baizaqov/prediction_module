"""Оценка биологических рисков (факторно-балльная модель, ТЗ 4.10.6).

Каталоги факторов по ООИ, расчёт интегрального показателя и уровня риска,
сохранение оценок регионов. Пороги/веса рабочие — подлежат экспертной валидации.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_session
from ..errors import ForecastError
from ..roles import EXPERT, READ_ROLES, WRITE_ROLES
from ..risk import service
from ..risk.schemas import (
    AssessmentDetailOut,
    AssessmentRequest,
    AssessmentResultOut,
    AssessmentSummaryOut,
    FactorOut,
    FactorWeightChangeOut,
    FactorWeightUpdate,
    InfectionOut,
    Panel,
)
from ..schemas import PageResponse
from ..security import Principal, PrincipalDep, require_roles

router = APIRouter(prefix="/v1/risk", tags=["risk"])

SessionDep = Annotated[Session, Depends(get_session)]


def _require_expert(
    principal: PrincipalDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Разрешить правку веса только Эксперту; при локальном отключении JWT доступ открыт."""
    if not settings.internal_token_enabled:
        return principal
    if not principal.has_role(EXPERT):
        raise ForecastError(
            "Недостаточно прав для изменения веса фактора",
            status_code=403,
            error_type="ACCESS_DENIED",
        )
    return principal


ExpertPrincipalDep = Annotated[Principal, Depends(_require_expert)]


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


@router.patch("/infections/{code}/factors/{factorNo}/weight", response_model=FactorOut,
              summary="Изменить вес фактора (только Эксперт госоргана)")
def update_factor_weight(
    code: str,
    factorNo: int,
    body: FactorWeightUpdate,
    session: SessionDep,
    principal: ExpertPrincipalDep,
):
    """Изменить текущий вес; фактическая правка создаёт одну запись истории."""
    if service.get_infection(session, code) is None:
        raise ForecastError(f"Неизвестная инфекция: {code}", status_code=404, error_type="NOT_FOUND")
    try:
        factor, _ = service.update_factor_weight(
            session,
            infection_code=code,
            factor_no=factorNo,
            new_weight=body.weight,
            principal=principal,
        )
    except ValueError as exc:
        raise ForecastError(str(exc), status_code=422, error_type="VALIDATION_ERROR") from exc
    if factor is None:
        raise ForecastError(
            f"Фактор {factorNo} не найден для инфекции: {code}",
            status_code=404,
            error_type="NOT_FOUND",
        )
    return _factor_out(factor)


@router.get("/infections/{code}/weight-history", response_model=PageResponse,
            summary="История изменения весов факторов (T-12A)")
def get_weight_history(code: str, session: SessionDep, principal: PrincipalDep,
                       factorNo: int | None = Query(None, description="Ограничить одним фактором"),
                       page: int = Query(0, ge=0),
                       size: int = Query(20, ge=1, le=200),
                       _=Depends(require_roles(*READ_ROLES))):
    """Смотреть может любая роль, но только по доступным ей факторам; правит вес Эксперт (T-13)."""
    if service.get_infection(session, code) is None:
        raise ForecastError(f"Неизвестная инфекция: {code}", status_code=404, error_type="NOT_FOUND")
    rows, total = service.list_weight_history(
        session, code, principal, factor_no=factorNo, page=page, size=size,
    )
    content = [
        FactorWeightChangeOut(
            factorNo=row.factor_no, oldWeight=row.old_weight, newWeight=row.new_weight,
            author=row.author, createdAt=row.created_at,
        )
        for row in rows
    ]
    return PageResponse(content=content, page=page, size=size, totalElements=total)


@router.get("/assessments", response_model=PageResponse,
            summary="Сохранённые оценки риска (список)")
def list_assessments(session: SessionDep, principal: PrincipalDep,
                     infectionCode: str | None = Query(None, description="Код инфекции"),
                     regionCode: str | None = Query(None, description="Код региона (КАТО)"),
                     districtCode: str | None = Query(None, description="Код района (КАТО)"),
                     periodFrom: date | None = Query(
                         None, description="Отдать оценки, чей период заканчивается не раньше этой даты"),
                     periodTo: date | None = Query(
                         None, description="Отдать оценки, чей период начинается не позже этой даты"),
                     search: str | None = Query(
                         None, description="Подстрока по нозологии, территории, уровню риска"),
                     page: int = Query(0, ge=0),
                     size: int = Query(20, ge=1, le=200),
                     _=Depends(require_roles(*READ_ROLES))):
    items, total = service.list_assessments(
        session,
        infection_code=infectionCode,
        region_code=regionCode,
        district_code=districtCode,
        period_from=periodFrom,
        period_to=periodTo,
        search=search,
        page=page,
        size=size,
    )
    content = [AssessmentSummaryOut(**item) for item in items]
    return PageResponse(content=content, page=page, size=size, totalElements=total)


@router.get("/assessments/{assessmentId}", response_model=AssessmentDetailOut,
            summary="Карточка сохранённой оценки риска")
def get_assessment(assessmentId: int, session: SessionDep, principal: PrincipalDep,
                   _=Depends(require_roles(*READ_ROLES))):
    """Выдать сохранённые баллы, весовые снимки и итог оценки без перерасчёта."""
    detail = service.get_assessment_detail(session, assessmentId)
    if detail is None:
        raise ForecastError(
            f"Оценка риска не найдена: {assessmentId}",
            status_code=404,
            error_type="NOT_FOUND",
        )
    return AssessmentDetailOut(**detail)


@router.post("/assessments/preview", response_model=AssessmentResultOut,
             summary="Рассчитать показатель без сохранения (для интерактивного калькулятора)")
def preview_assessment(body: AssessmentRequest, session: SessionDep, principal: PrincipalDep,
                       _=Depends(require_roles(*READ_ROLES))):
    try:
        return service.assess(session, body, principal, persist=False)
    except ValueError as exc:
        raise ForecastError(str(exc)) from exc


@router.post("/assessments", response_model=AssessmentResultOut,
             summary="Сохранить оценку региона и вернуть результат расчёта")
def create_assessment(body: AssessmentRequest, session: SessionDep, principal: PrincipalDep,
                      _=Depends(require_roles(*WRITE_ROLES))):
    try:
        return service.assess(session, body, principal, persist=True)
    except ValueError as exc:
        raise ForecastError(str(exc)) from exc
