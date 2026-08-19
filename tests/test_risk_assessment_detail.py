"""T-22: карточка ранее сохранённой оценки со снимками весов."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.risk.models import Assessment, AssessmentScore, Factor

init_db()
client = TestClient(app)


def _create_assessment(*, region_code: str, scores: dict[str, int]) -> dict:
    response = client.post("/v1/risk/assessments", json={
        "infectionCode": "plague",
        "regionCode": region_code,
        "periodFrom": "2026-10-01",
        "periodTo": "2026-10-31",
        "panel": "basic",
        "scores": scores,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _detail(assessment_id: int) -> dict:
    response = client.get(f"/v1/risk/assessments/{assessment_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_saved_assessment_detail_returns_persisted_result_and_score_snapshots():
    saved = _create_assessment(
        region_code="KZ-T22-DETAIL",
        scores={"1": 3, "2": 2},
    )
    detail = _detail(saved["assessmentId"])

    session = SessionLocal()
    try:
        assessment = session.get(Assessment, saved["assessmentId"])
        assert assessment is not None
        stored_scores = list(
            session.query(AssessmentScore)
            .filter(AssessmentScore.assessment_id == assessment.id)
            .order_by(AssessmentScore.factor_no)
        )
    finally:
        session.close()

    assert detail["id"] == assessment.id
    assert detail["infectionCode"] == assessment.infection_code == saved["infectionCode"]
    assert detail["infectionNameRu"]
    assert detail["regionCode"] == assessment.region_code == saved["regionCode"]
    assert detail["periodFrom"] == str(assessment.period_from) == saved["periodFrom"]
    assert detail["periodTo"] == str(assessment.period_to) == saved["periodTo"]
    assert detail["panel"] == assessment.panel == saved["panel"]
    assert detail["createdAt"]
    assert detail["panelSize"] == assessment.panel_size == saved["panelSize"]
    assert detail["assessed"] == assessment.assessed == saved["assessed"]
    assert detail["integralIndex"] == assessment.integral_index == saved["integralIndex"]
    assert detail["completeness"] == assessment.completeness == saved["completeness"]
    assert detail["adjustedIndex"] == assessment.adjusted_index == saved["adjustedIndex"]
    assert detail["level"] == assessment.level == saved["level"]
    assert detail["levelRu"] == assessment.level_ru == saved["levelRu"]
    assert detail["hasRedTrigger"] == assessment.has_red_trigger == saved["hasRedTrigger"]
    assert detail["scores"] == [
        {"factorNo": score.factor_no, "score": score.score, "weight": score.weight}
        for score in stored_scores
    ]


def test_saved_assessment_detail_returns_not_found_for_unknown_id():
    response = client.get("/v1/risk/assessments/999999")

    assert response.status_code == 404
    assert response.json()["errors"][0]["errorType"] == "NOT_FOUND"


def test_saved_assessment_detail_keeps_weight_and_result_after_catalog_weight_change():
    session = SessionLocal()
    try:
        factor = session.get(Factor, ("plague", 1))
        assert factor is not None
        original_weight = factor.weight
    finally:
        session.close()

    saved = _create_assessment(
        region_code="KZ-T22-WEIGHT",
        scores={"1": 4},
    )
    before_change = _detail(saved["assessmentId"])
    new_weight = 4 if original_weight != 4 else 3
    try:
        changed = client.patch(
            "/v1/risk/infections/plague/factors/1/weight",
            json={"weight": new_weight},
        )
        assert changed.status_code == 200, changed.text

        after_change = _detail(saved["assessmentId"])
        assert after_change["scores"] == before_change["scores"]
        for field in (
            "panelSize", "assessed", "integralIndex", "completeness", "adjustedIndex",
            "level", "levelRu", "hasRedTrigger",
        ):
            assert after_change[field] == before_change[field]
    finally:
        restored = client.patch(
            "/v1/risk/infections/plague/factors/1/weight",
            json={"weight": original_weight},
        )
        assert restored.status_code == 200, restored.text


def test_saved_assessment_detail_keeps_score_when_factor_is_removed_from_catalog():
    saved = _create_assessment(
        region_code="KZ-T22-DELETED-FACTOR",
        scores={"1": 2},
    )
    before_deletion = _detail(saved["assessmentId"])

    session = SessionLocal()
    try:
        factor = session.get(Factor, ("plague", 1))
        assert factor is not None
        factor_values = {column.name: getattr(factor, column.name) for column in Factor.__table__.columns}
        session.delete(factor)
        session.commit()

        after_deletion = _detail(saved["assessmentId"])
        assert after_deletion["scores"] == before_deletion["scores"]
    finally:
        session.rollback()
        if "factor_values" in locals():
            session.add(Factor(**factor_values))
            session.commit()
        session.close()
