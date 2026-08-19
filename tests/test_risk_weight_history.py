"""T-12/T-13: история изменения весов и правка веса Экспертом."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.main import app
from app.risk.models import Assessment, AssessmentScore, Factor, FactorWeightChange
from app.roles import EXPERT, FORECAST_ANALYST, KSEC_ROLES, KVKN_ROLES, MIO_ROLES, NCOZ_ADMIN, SUPER_ADMIN

init_db()
client = TestClient(app)

_TEST_TOKEN_SECRET = "risk-weight-history-test-token"
_AUTH_SETTINGS = Settings(
    GISBB_INTERNAL_TOKEN_ENABLED=True,
    GISBB_INTERNAL_TOKEN_SECRET=_TEST_TOKEN_SECRET,
)
_INFECTION_CODE = "brucellosis"
_FACTOR_NO = 1
_AUTHOR = {
    "userId": 501,
    "orgId": 77,
    "orgName": "Тестовый госорган",
    "orgBin": "000000000000",
    "fullName": "Тестовый Эксперт",
}


@contextmanager
def _authenticated_api() -> Iterator[None]:
    """Включить реальную JWT-проверку для API-теста и не менять общие настройки."""
    previous = app.dependency_overrides.get(get_settings)
    app.dependency_overrides[get_settings] = lambda: _AUTH_SETTINGS
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_settings, None)
        else:
            app.dependency_overrides[get_settings] = previous


def _headers(*roles: str, user_info: dict | None = None) -> dict[str, str]:
    token = jwt.encode(
        {"roles": list(roles), "userInfo": user_info or {}},
        _TEST_TOKEN_SECRET,
        algorithm="HS256",
    )
    return {"X-Internal-Authorization": f"Bearer {token}"}


def _factor_weight() -> int:
    session = SessionLocal()
    try:
        factor = session.get(Factor, (_INFECTION_CODE, _FACTOR_NO))
        assert factor is not None
        return factor.weight
    finally:
        session.close()


def _history_count() -> int:
    session = SessionLocal()
    try:
        return session.query(FactorWeightChange).filter_by(
            infection_code=_INFECTION_CODE,
            factor_no=_FACTOR_NO,
        ).count()
    finally:
        session.close()


def _patch_weight(weight: int, *roles: str, user_info: dict | None = None):
    return client.patch(
        f"/v1/risk/infections/{_INFECTION_CODE}/factors/{_FACTOR_NO}/weight",
        json={"weight": weight},
        headers=_headers(*roles, user_info=user_info),
    )


def test_weight_edit_without_jwt_is_unauthorized():
    before_weight = _factor_weight()
    before_history = _history_count()

    with _authenticated_api():
        response = client.patch(
            f"/v1/risk/infections/{_INFECTION_CODE}/factors/{_FACTOR_NO}/weight",
            json={"weight": 4 if before_weight != 4 else 3},
        )

    assert response.status_code == 401
    assert _factor_weight() == before_weight
    assert _history_count() == before_history


def test_expert_edits_weight_and_creates_exactly_one_history_record():
    original_weight = _factor_weight()
    new_weight = 4 if original_weight != 4 else 3
    history_before = _history_count()

    with _authenticated_api():
        try:
            response = _patch_weight(new_weight, EXPERT, user_info=_AUTHOR)
            assert response.status_code == 200, response.text
            assert response.json()["weight"] == new_weight
            assert _factor_weight() == new_weight
            assert _history_count() == history_before + 1

            session = SessionLocal()
            try:
                change = session.query(FactorWeightChange).filter_by(
                    infection_code=_INFECTION_CODE,
                    factor_no=_FACTOR_NO,
                ).order_by(FactorWeightChange.id.desc()).first()
                assert change is not None
                assert change.old_weight == original_weight
                assert change.new_weight == new_weight
                assert change.author == {
                    "user_id": _AUTHOR["userId"],
                    "org_id": _AUTHOR["orgId"],
                    "org_name": _AUTHOR["orgName"],
                    "org_bin": _AUTHOR["orgBin"],
                    "full_name": _AUTHOR["fullName"],
                }
                assert change.created_at is not None
            finally:
                session.close()
        finally:
            restored = _patch_weight(original_weight, EXPERT, user_info=_AUTHOR)
            assert restored.status_code == 200, restored.text


@pytest.mark.parametrize(
    "roles",
    [
        (KSEC_ROLES[0],),
        (KVKN_ROLES[0],),
        (MIO_ROLES[0],),
        (FORECAST_ANALYST,),
        (SUPER_ADMIN,),
        (NCOZ_ADMIN,),
    ],
)
def test_non_expert_cannot_edit_weight_or_create_history(roles: tuple[str, ...]):
    before_weight = _factor_weight()
    before_history = _history_count()

    with _authenticated_api():
        response = _patch_weight(4 if before_weight != 4 else 3, *roles)

    assert response.status_code == 403
    assert response.json()["errors"][0]["errorType"] == "ACCESS_DENIED"
    assert _factor_weight() == before_weight
    assert _history_count() == before_history


@pytest.mark.parametrize("weight", [0, 5])
def test_weight_outside_range_does_not_change_catalog_or_history(weight: int):
    before_weight = _factor_weight()
    before_history = _history_count()

    with _authenticated_api():
        response = _patch_weight(weight, EXPERT, user_info=_AUTHOR)

    assert response.status_code == 422
    assert _factor_weight() == before_weight
    assert _history_count() == before_history


def test_repeating_current_weight_is_a_history_free_noop():
    current_weight = _factor_weight()
    history_before = _history_count()

    with _authenticated_api():
        response = _patch_weight(current_weight, EXPERT, user_info=_AUTHOR)

    assert response.status_code == 200
    assert response.json()["weight"] == current_weight
    assert _history_count() == history_before


def test_weight_edit_returns_404_for_unknown_factor_without_history():
    history_before = _history_count()

    with _authenticated_api():
        response = client.patch(
            f"/v1/risk/infections/{_INFECTION_CODE}/factors/9999/weight",
            json={"weight": 2},
            headers=_headers(EXPERT, user_info=_AUTHOR),
        )

    assert response.status_code == 404
    assert response.json()["errors"][0]["errorType"] == "NOT_FOUND"
    assert _history_count() == history_before


def test_saved_assessment_keeps_old_weight_snapshot_after_expert_edit():
    original_weight = _factor_weight()
    new_weight = 4 if original_weight != 4 else 3
    first_region = "KZ-T13-SNAPSHOT-OLD"
    second_region = "KZ-T13-SNAPSHOT-NEW"

    with _authenticated_api():
        try:
            first = client.post("/v1/risk/assessments", json={
                "infectionCode": _INFECTION_CODE,
                "regionCode": first_region,
                "panel": "basic",
                "scores": {str(_FACTOR_NO): 4},
            }, headers=_headers(EXPERT, user_info=_AUTHOR))
            assert first.status_code == 200, first.text

            changed = _patch_weight(new_weight, EXPERT, user_info=_AUTHOR)
            assert changed.status_code == 200, changed.text

            second = client.post("/v1/risk/assessments", json={
                "infectionCode": _INFECTION_CODE,
                "regionCode": second_region,
                "panel": "basic",
                "scores": {str(_FACTOR_NO): 4},
            }, headers=_headers(EXPERT, user_info=_AUTHOR))
            assert second.status_code == 200, second.text

            session = SessionLocal()
            try:
                first_assessment = session.get(Assessment, first.json()["assessmentId"])
                first_score = session.get(
                    AssessmentScore,
                    (first.json()["assessmentId"], _FACTOR_NO),
                )
                second_score = session.get(
                    AssessmentScore,
                    (second.json()["assessmentId"], _FACTOR_NO),
                )
                assert first_assessment is not None
                assert first_score is not None
                assert second_score is not None
                assert first_score.weight == original_weight
                assert first_assessment.integral_index == first.json()["integralIndex"]
                assert second_score.weight == new_weight
            finally:
                session.close()
        finally:
            restored = _patch_weight(original_weight, EXPERT, user_info=_AUTHOR)
            assert restored.status_code == 200, restored.text


def _get_history(*roles: str, factor_no: int | None = None, **params):
    query = dict(params)
    if factor_no is not None:
        query["factorNo"] = factor_no
    return client.get(
        f"/v1/risk/infections/{_INFECTION_CODE}/weight-history",
        params=query,
        headers=_headers(*roles, user_info=_AUTHOR),
    )


def test_weight_history_endpoint_lists_the_change_just_made():
    """T-12A: GET-эндпоинт отдаёт то, что записал T-13 PATCH."""
    original_weight = _factor_weight()
    new_weight = 4 if original_weight != 4 else 3

    with _authenticated_api():
        try:
            changed = _patch_weight(new_weight, EXPERT, user_info=_AUTHOR)
            assert changed.status_code == 200, changed.text

            response = _get_history(EXPERT, factor_no=_FACTOR_NO)
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["content"], "история не должна быть пустой сразу после правки"
            latest = body["content"][0]
            assert latest["factorNo"] == _FACTOR_NO
            assert latest["oldWeight"] == original_weight
            assert latest["newWeight"] == new_weight
            assert latest["author"]["full_name"] == _AUTHOR["fullName"]
        finally:
            restored = _patch_weight(original_weight, EXPERT, user_info=_AUTHOR)
            assert restored.status_code == 200, restored.text


def test_weight_history_is_filtered_by_accessible_factors_for_organization_role():
    """БА: смотреть могут все, но только по доступным им факторам (фактор 1 — МИО)."""
    original_weight = _factor_weight()
    new_weight = 4 if original_weight != 4 else 3

    with _authenticated_api():
        try:
            changed = _patch_weight(new_weight, EXPERT, user_info=_AUTHOR)
            assert changed.status_code == 200, changed.text

            own = _get_history(MIO_ROLES[0], factor_no=_FACTOR_NO)
            assert own.status_code == 200, own.text
            assert any(row["factorNo"] == _FACTOR_NO for row in own.json()["content"])

            foreign = _get_history(KSEC_ROLES[0], factor_no=_FACTOR_NO)
            assert foreign.status_code == 200, foreign.text
            assert foreign.json()["content"] == []
        finally:
            restored = _patch_weight(original_weight, EXPERT, user_info=_AUTHOR)
            assert restored.status_code == 200, restored.text


def test_weight_history_returns_404_for_unknown_infection():
    with _authenticated_api():
        response = client.get(
            "/v1/risk/infections/unknown-disease/weight-history",
            headers=_headers(EXPERT, user_info=_AUTHOR),
        )
    assert response.status_code == 404
    assert response.json()["errors"][0]["errorType"] == "NOT_FOUND"


def test_history_records_cannot_be_updated_or_deleted_through_orm():
    original_weight = _factor_weight()
    new_weight = 4 if original_weight != 4 else 3

    with _authenticated_api():
        try:
            created = _patch_weight(new_weight, EXPERT, user_info=_AUTHOR)
            assert created.status_code == 200, created.text

            session = SessionLocal()
            try:
                change = session.query(FactorWeightChange).filter_by(
                    infection_code=_INFECTION_CODE,
                    factor_no=_FACTOR_NO,
                ).order_by(FactorWeightChange.id.desc()).first()
                assert change is not None
                change.new_weight = original_weight
                with pytest.raises(ValueError, match="нельзя изменять"):
                    session.commit()
                session.rollback()

                unchanged = session.get(FactorWeightChange, change.id)
                assert unchanged is not None
                assert unchanged.new_weight == new_weight

                session.delete(unchanged)
                with pytest.raises(ValueError, match="нельзя удалять"):
                    session.commit()
                session.rollback()
                assert session.get(FactorWeightChange, change.id) is not None
            finally:
                session.close()
        finally:
            restored = _patch_weight(original_weight, EXPERT, user_info=_AUTHOR)
            assert restored.status_code == 200, restored.text
