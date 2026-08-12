"""Прикладной слой домена оценки рисков: чтение каталогов и расчёт+сохранение оценки."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..security import Principal
from . import scoring
from .models import Assessment, AssessmentScore, Factor, Infection


def list_infections(session: Session) -> list[Infection]:
    return list(session.execute(select(Infection).order_by(Infection.code)).scalars())


def get_infection(session: Session, code: str) -> Infection | None:
    return session.get(Infection, code)


def list_factors(session: Session, infection_code: str, panel: str = "full") -> list[Factor]:
    stmt = select(Factor).where(Factor.infection_code == infection_code)
    if panel == "basic":
        stmt = stmt.where(Factor.tier == "basic")
    elif panel == "extended":
        stmt = stmt.where(Factor.tier == "extended")
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

    Расчётные величины в БД не хранятся (миграций пока нет): уровень и признак
    красного триггера пересчитываются по сохранённым баллам и текущему каталогу —
    так же, как это делает assess().
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

    ids = [a.id for a in rows]
    scores_by_assessment: dict[int, dict[int, int]] = {i: {} for i in ids}
    for s in session.execute(
        select(AssessmentScore).where(AssessmentScore.assessment_id.in_(ids))
    ).scalars():
        scores_by_assessment[s.assessment_id][s.factor_no] = s.score

    catalogs: dict[str, list[dict]] = {}
    names: dict[str, str] = {}
    items = []
    for a in rows:
        if a.infection_code not in catalogs:
            infection = get_infection(session, a.infection_code)
            names[a.infection_code] = infection.name_ru if infection else a.infection_code
            catalogs[a.infection_code] = _to_catalog_dicts(list_factors(session, a.infection_code, panel="full"))

        result = scoring.calculate_risk(catalogs[a.infection_code], scores_by_assessment[a.id], panel=a.panel)
        items.append({
            "id": a.id,
            "infectionCode": a.infection_code,
            "infectionNameRu": names[a.infection_code],
            "regionCode": a.region_code,
            "period": a.period,
            "panel": a.panel,
            "level": result["level"],
            "levelRu": result["level_ru"],
            "hasRedTrigger": result["has_red_trigger"],
            "assessed": result["assessed"],
            "createdAt": a.created_at,
        })

    return items, total


def assess(session: Session, req, principal: Principal, persist: bool = True) -> dict:
    """Рассчитать интегральный показатель по выставленным баллам и (опц.) сохранить оценку."""
    infection = get_infection(session, req.infectionCode)
    if infection is None:
        raise ValueError(f"Неизвестная инфекция: {req.infectionCode}")

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
        )
        session.add(assessment)
        session.flush()
        for no, score in (req.scores or {}).items():
            if score is None:
                continue
            session.add(AssessmentScore(assessment_id=assessment.id, factor_no=int(no), score=int(score)))
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
