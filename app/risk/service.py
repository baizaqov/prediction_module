"""Прикладной слой домена оценки рисков: чтение каталогов и расчёт+сохранение оценки."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..security import Principal
from . import scoring
from .access import accessible_factor_numbers, split_scores_by_access
from .events import log_red_trigger_event
from .models import Assessment, AssessmentScore, Factor, FactorWeightChange, Infection


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


def update_factor_weight(
    session: Session,
    *,
    infection_code: str,
    factor_no: int,
    new_weight: int,
    principal: Principal,
) -> tuple[Factor | None, bool]:
    """Изменить вес и записать историю одной транзакцией.

    ``changed=False`` означает идемпотентный PATCH: передан уже действующий вес, поэтому
    состояние каталога и история не меняются. Проверку роли выполняет API до вызова
    сервиса; здесь ``principal`` нужен для автора неизменяемой записи истории.
    """
    if not 1 <= new_weight <= 4:
        raise ValueError("Вес фактора должен быть целым числом от 1 до 4")

    factor = session.get(Factor, (infection_code, factor_no))
    if factor is None:
        return None, False

    old_weight = factor.weight
    if old_weight == new_weight:
        return factor, False

    factor.weight = new_weight
    session.add(FactorWeightChange(
        infection_code=infection_code,
        factor_no=factor_no,
        old_weight=old_weight,
        new_weight=new_weight,
        author=asdict(principal.user_info),
    ))
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    return factor, True


def list_weight_history(
    session: Session,
    infection_code: str,
    principal: Principal | None,
    *,
    factor_no: int | None = None,
    page: int = 0,
    size: int = 20,
) -> tuple[list[FactorWeightChange], int]:
    """История правок веса, видимая роли только по доступным ей факторам (T-12A).

    Правку веса делает только Эксперт (T-13), но смотреть историю может любая роль —
    в пределах своей зоны ответственности, как и каталог (см. list_factors).
    """
    query = session.query(FactorWeightChange).filter(
        FactorWeightChange.infection_code == infection_code
    )

    accessible_nos = accessible_factor_numbers(session, infection_code, principal)
    if accessible_nos is not None:
        if not accessible_nos:
            return [], 0
        query = query.filter(FactorWeightChange.factor_no.in_(accessible_nos))

    if factor_no is not None:
        query = query.filter(FactorWeightChange.factor_no == factor_no)

    total = query.count()
    rows = list(
        query.order_by(FactorWeightChange.created_at.desc(), FactorWeightChange.id.desc())
        .offset(page * size)
        .limit(size)
    )
    return rows, total


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
    period_from: date | None = None,
    period_to: date | None = None,
    search: str | None = None,
    page: int = 0,
    size: int = 20,
) -> tuple[list[dict], int]:
    """Список сохранённых оценок с фильтрами и пагинацией (журнал, GET /v1/risk/assessments).

    Уровень и признак красного триггера читаются из уже сохранённого результата расчёта
    (T-07), а не пересчитываются по текущему каталогу — иначе правка веса фактора задним
    числом меняла бы уровень прошлых оценок.

    ``period_from``/``period_to`` — фильтр по интервалу (решение БА), а не точное совпадение
    строки: отдаётся всё, чей [period_from, period_to] пересекается с заданным окном. Любая
    из границ может быть не задана — тогда окно открыто с этой стороны.

    ``search`` — подстрока по текстовым полям строки журнала (решение БА): нозология,
    территория, уровень риска. Регистронезависимо. Период — теперь пара дат, а не
    свободный текст, поэтому в подстрочный поиск не входит.
    """
    query = session.query(Assessment)
    if infection_code:
        query = query.filter(Assessment.infection_code == infection_code)
    if region_code:
        query = query.filter(Assessment.region_code == region_code)
    if period_from is not None:
        query = query.filter(Assessment.period_to >= period_from)
    if period_to is not None:
        query = query.filter(Assessment.period_from <= period_to)
    if search:
        pattern = f"%{search.strip()}%"
        matching_infection_codes = select(Infection.code).where(Infection.name_ru.ilike(pattern))
        query = query.filter(
            Assessment.infection_code.in_(matching_infection_codes)
            | Assessment.region_code.ilike(pattern)
            | Assessment.level_ru.ilike(pattern)
        )

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
            "periodFrom": a.period_from,
            "periodTo": a.period_to,
            "panel": a.panel,
            "level": a.level,
            "levelRu": a.level_ru,
            "hasRedTrigger": a.has_red_trigger,
            "assessed": a.assessed,
            "createdAt": a.created_at,
        })

    return items, total


def get_assessment_detail(session: Session, assessment_id: int) -> dict | None:
    """Вернуть карточку сохранённой оценки без перерасчёта и чтения текущих весов.

    ``AssessmentScore`` не связан внешним ключом с каталогом факторов. Это позволяет
    сохранить в карточке балл и вес фактора, даже если его уже удалили из каталога.
    """
    assessment = session.get(Assessment, assessment_id)
    if assessment is None:
        return None

    infection = get_infection(session, assessment.infection_code)
    scores = list(
        session.execute(
            select(AssessmentScore)
            .where(AssessmentScore.assessment_id == assessment.id)
            .order_by(AssessmentScore.factor_no)
        ).scalars()
    )
    return {
        "id": assessment.id,
        "infectionCode": assessment.infection_code,
        "infectionNameRu": infection.name_ru if infection else assessment.infection_code,
        "regionCode": assessment.region_code,
        "periodFrom": assessment.period_from,
        "periodTo": assessment.period_to,
        "panel": assessment.panel,
        "createdAt": assessment.created_at,
        "panelSize": assessment.panel_size,
        "assessed": assessment.assessed,
        "integralIndex": assessment.integral_index,
        "completeness": assessment.completeness,
        "adjustedIndex": assessment.adjusted_index,
        "level": assessment.level,
        "levelRu": assessment.level_ru,
        "hasRedTrigger": assessment.has_red_trigger,
        "scores": [
            {"factorNo": score.factor_no, "score": score.score, "weight": score.weight}
            for score in scores
        ],
    }


def assess(session: Session, req, principal: Principal, persist: bool = True) -> dict:
    """Рассчитать интегральный показатель по выставленным баллам и (опц.) сохранить оценку."""
    infection = get_infection(session, req.infectionCode)
    if infection is None:
        raise ValueError(f"Неизвестная инфекция: {req.infectionCode}")

    # Полный каталог инфекции; панель выбирает scoring.calculate_risk по полю tier.
    catalog = _to_catalog_dicts(list_factors(session, req.infectionCode, panel="full"))
    catalog_nos = {f["no"] for f in catalog}

    # Баллы по чужим факторам исключаются из расчёта и сохранения, но не отклоняют
    # оценку целиком — по решению БА сохраняется корректная часть (T-16/T-27).
    accepted_scores, rejected_factors = split_scores_by_access(
        session, req.infectionCode, req.scores or {}, catalog_nos, principal,
    )

    panel = req.panel.value if hasattr(req.panel, "value") else str(req.panel)
    result = scoring.calculate_risk(catalog, accepted_scores, panel=panel)

    assessment_id = None
    if persist:
        assessment = Assessment(
            infection_code=req.infectionCode,
            region_code=req.regionCode,
            period_from=req.periodFrom,
            period_to=req.periodTo,
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
        # Снимок веса берём из того же каталога, что уже пересчитал результат выше. Источник
        # баллов — accepted_scores, не req.scores: чужой фактор уже отфильтрован выше и не
        # должен попасть в сохранённую оценку. Номера, которых нет в каталоге инфекции,
        # по-прежнему отсеиваются здесь же — для них нет веса для снимка.
        weight_by_no = {f["no"]: f["weight"] for f in catalog}
        for no, score in accepted_scores.items():
            factor_no = int(no)
            weight = weight_by_no.get(factor_no)
            if weight is None:
                continue
            session.add(AssessmentScore(
                assessment_id=assessment.id, factor_no=factor_no, score=int(score), weight=int(weight),
            ))
        session.commit()
        assessment_id = assessment.id

        if result["has_red_trigger"]:
            log_red_trigger_event(
                assessment_id=assessment.id,
                infection_code=req.infectionCode,
                region_code=req.regionCode,
                period_from=req.periodFrom,
                period_to=req.periodTo,
                red_triggers=result["red_triggers"],
            )

    return {
        "assessmentId": assessment_id,
        "infectionCode": req.infectionCode,
        "regionCode": req.regionCode,
        "periodFrom": req.periodFrom,
        "periodTo": req.periodTo,
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
        "rejectedFactors": rejected_factors,
        "byCategory": result["by_category"],
        "byFactorClass": result["by_factor_class"],
    }
