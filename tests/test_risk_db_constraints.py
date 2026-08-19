"""T-08: CHECK-ограничения целостности в БД, а не только в приложении.

Тесты вставляют строки напрямую через ORM-модели, в обход scoring.py/service.py —
это намеренно: цель проверить, что источником отказа является сама схема, а не
валидация в коде.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, init_db
from app.risk.models import Assessment, AssessmentScore, Factor

init_db()

_TEST_INFECTION = "t08-constraint-check"


def _valid_factor_kwargs(**overrides) -> dict:
    kwargs = dict(
        infection_code=_TEST_INFECTION,
        no=9001,
        category="Тест",
        name="Тестовый фактор",
        type="numeric",
        weight=2,
        tier="basic",
    )
    kwargs.update(overrides)
    return kwargs


def _insert_factor(**overrides) -> None:
    session = SessionLocal()
    try:
        session.add(Factor(**_valid_factor_kwargs(**overrides)))
        session.commit()
    finally:
        session.rollback()
        session.close()


@pytest.mark.parametrize("weight", [0, 5, -1])
def test_factor_weight_outside_1_4_rejected_by_db(weight: int):
    with pytest.raises(IntegrityError):
        _insert_factor(no=9001, weight=weight)


def test_factor_weight_inside_1_4_accepted_by_db():
    _insert_factor(no=9002, weight=4)
    session = SessionLocal()
    try:
        assert session.get(Factor, (_TEST_INFECTION, 9002)) is not None
    finally:
        session.query(Factor).filter_by(infection_code=_TEST_INFECTION, no=9002).delete()
        session.commit()
        session.close()


@pytest.mark.parametrize("bad_type", ["numer1c", "", "NUMERIC"])
def test_factor_type_outside_enum_rejected_by_db(bad_type: str):
    with pytest.raises(IntegrityError):
        _insert_factor(no=9003, type=bad_type)


@pytest.mark.parametrize("bad_tier", ["expert", "", "Basic"])
def test_factor_tier_outside_enum_rejected_by_db(bad_tier: str):
    with pytest.raises(IntegrityError):
        _insert_factor(no=9004, tier=bad_tier)


def _create_assessment_for_score_test() -> int:
    session = SessionLocal()
    try:
        assessment = Assessment(
            infection_code=_TEST_INFECTION,
            region_code="KZ-T08-CONSTRAINT",
            panel="basic",
            level="not_assessed",
            level_ru="не оценено",
        )
        session.add(assessment)
        session.commit()
        return assessment.id
    finally:
        session.close()


@pytest.mark.parametrize("score", [-1, 5, 100])
def test_assessment_score_outside_0_4_rejected_by_db(score: int):
    assessment_id = _create_assessment_for_score_test()
    session = SessionLocal()
    try:
        session.add(AssessmentScore(
            assessment_id=assessment_id, factor_no=1, score=score, weight=2,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_assessment_score_inside_0_4_accepted_by_db():
    assessment_id = _create_assessment_for_score_test()
    session = SessionLocal()
    try:
        session.add(AssessmentScore(
            assessment_id=assessment_id, factor_no=1, score=4, weight=2,
        ))
        session.commit()
        assert session.get(AssessmentScore, (assessment_id, 1)) is not None
    finally:
        session.close()
