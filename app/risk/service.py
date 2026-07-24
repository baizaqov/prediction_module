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
