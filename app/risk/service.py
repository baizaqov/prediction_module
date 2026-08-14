"""Прикладной слой домена оценки рисков: чтение каталогов и расчёт+сохранение оценки."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..security import Principal
from . import scoring
from .access import FactorAccessDenied, accessible_factor_numbers, ensure_scores_accessible
from .models import Assessment, AssessmentScore, Factor, Infection


def list_infections(session: Session) -> list[Infection]:
    return list(session.execute(select(Infection).order_by(Infection.code)).scalars())


def get_infection(session: Session, code: str) -> Infection | None:
    return session.get(Infection, code)


def list_factors(
    session: Session,
    infection_code: str,
    panel: str = "full",
    principal: Principal | None = None,
) -> list[Factor]:
    """Каталог панели с учётом зоны ответственности, если передан принципал."""
    stmt = select(Factor).where(Factor.infection_code == infection_code)
    if panel == "basic":
        stmt = stmt.where(Factor.tier == "basic")
    elif panel == "extended":
        stmt = stmt.where(Factor.tier == "extended")
    accessible_nos = accessible_factor_numbers(session, infection_code, principal)
    if accessible_nos is not None:
        stmt = stmt.where(Factor.no.in_(accessible_nos))
    return list(session.execute(stmt.order_by(Factor.no)).scalars())


def _to_catalog_dicts(factors: list[Factor]) -> list[dict]:
    """Каталог факторов в форме, которую ожидает scoring.calculate_risk."""
    return [
        {
            "no": f.no,
            "category": f.category,
            "name": f.name,
            "type": f.type,
            "weight": f.weight,
            "tier": f.tier,
            "red_trigger": f.red_trigger,
            "factor_class": f.factor_class,
            "scale": f.scale,
        }
        for f in factors
    ]


def list_assessments(
    session: Session,
    *,
    infection_code: str | None = None,
    region_code: str | None = None,
    period: str | None = None,
    page: int = 0,
    size: int = 20,
) -> tuple[list[dict], int]:
    """Список сохранённых оценок с фильтрами и пагинацией (журнал, GET /v1/risk/assessments).

    Уровень и признак красного триггера читаются из уже сохранённого результата расчёта
    (T-07), а не пересчитываются по текущему каталогу — иначе правка веса фактора задним
    числом меняла бы уровень прошлых оценок.
    """
    query = session.query(Assessment)
    if infection_code:
        query = query.filter(Assessment.infection_code == infection_code)
    if region_code:
        query = query.filter(Assessment.region_code == region_code)
    if period:
        query = query.filter(Assessment.period == period)

    total = query.count()
    rows = list(
        query.order_by(Assessment.created_at.desc(), Assessment.id.desc())
        .offset(page * size)
        .limit(size)
    )
    if not rows:
        return [], total

    names: dict[str, str] = {}
    items = []
    for a in rows:
        if a.infection_code not in names:
            infection = get_infection(session, a.infection_code)
            names[a.infection_code] = infection.name_ru if infection else a.infection_code

        items.append({
            "id": a.id,
            "infectionCode": a.infection_code,
            "infectionNameRu": names[a.infection_code],
            "regionCode": a.region_code,
            "period": a.period,
            "panel": a.panel,
            "level": a.level,
            "levelRu": a.level_ru,
            "hasRedTrigger": a.has_red_trigger,
            "assessed": a.assessed,
            "createdAt": a.created_at,
        })

    return items, total


def assess(session: Session, req, principal: Principal, persist: bool = True) -> dict:
    """Рассчитать интегральный показатель по выставленным баллам и (опц.) сохранить оценку."""
    infection = get_infection(session, req.infectionCode)
    if infection is None:
        raise ValueError(f"Неизвестная инфекция: {req.infectionCode}")

    # Проверка происходит до расчёта и тем более до создания Assessment: отказ по
    # одному чужому фактору не оставляет в транзакции частично сохранённых строк.
    ensure_scores_accessible(session, req.infectionCode, req.scores or {}, principal)

    # Полный каталог инфекции; панель выбирает scoring.calculate_risk по полю tier.
    catalog = _to_catalog_dicts(list_factors(session, req.infectionCode, panel="full"))
    panel = req.panel.value if hasattr(req.panel, "value") else str(req.panel)
    result = scoring.calculate_risk(catalog, req.scores, panel=panel)

    assessment_id = None
    if persist:
        assessment = Assessment(
            infection_code=req.infectionCode,
            region_code=req.regionCode,
            period=req.period,
            panel=panel,
            created_by=asdict(principal.user_info) if principal else {},
            panel_size=result["panel_size"],
            assessed=result["assessed"],
            integral_index=result["integral_index"],
            completeness=result["completeness"],
            adjusted_index=result["adjusted_index"],
            level=result["level"],
            level_ru=result["level_ru"],
            has_red_trigger=result["has_red_trigger"],
        )
        session.add(assessment)
        session.flush()
        # Снимок веса берём из того же каталога, что уже пересчитал результат выше — не из
        # req.scores напрямую: фактор, которого нет в каталоге инфекции, движок и так
        # игнорирует, поэтому для него нет веса для снимка и строка не сохраняется.
        weight_by_no = {f["no"]: f["weight"] for f in catalog}
        for no, score in (req.scores or {}).items():
            if score is None:
                continue
            factor_no = int(no)
            weight = weight_by_no.get(factor_no)
            if weight is None:
                continue
            session.add(AssessmentScore(
                assessment_id=assessment.id, factor_no=factor_no, score=int(score), weight=int(weight),
            ))
        session.commit()
        assessment_id = assessment.id

    return {
        "assessmentId": assessment_id,
        "infectionCode": req.infectionCode,
        "regionCode": req.regionCode,
        "period": req.period,
        "panel": result["panel"],
        "panelSize": result["panel_size"],
        "assessed": result["assessed"],
        "notAssessed": result["not_assessed"],
        "weightedSum": result["weighted_sum"],
        "integralIndex": result["integral_index"],
        "completeness": result["completeness"],
        "adjustmentFactor": result["adjustment_factor"],
        "adjustedIndex": result["adjusted_index"],
        "level": result["level"],
        "levelRu": result["level_ru"],
        "hasRedTrigger": result["has_red_trigger"],
        "redTriggers": result["red_triggers"],
        "byCategory": result["by_category"],
        "byFactorClass": result["by_factor_class"],
    }
