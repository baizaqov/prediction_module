"""T-14..T-16: роли Keycloak и разграничение факторов риска."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import Settings
from app.db import SessionLocal, init_db
from app.main import app
from app.risk.models import Assessment, AssessmentScore, FactorOrganization
from app.roles import (
    EXPERT,
    FORECAST_ANALYST,
    KSEC_ROLES,
    KVKN_ROLES,
    MCHS_ADMIN,
    MIO_ROLES,
    NCOZ_ADMIN,
    READ_ROLES,
    SUPER_ADMIN,
    WRITE_ROLES,
)
from app.security import Principal, get_principal, require_roles

init_db()
client = TestClient(app)


@contextmanager
def _as_roles(*roles: str) -> Iterator[None]:
    """Подменить principal для API-теста, не включая реальную проверку токена."""
    previous = app.dependency_overrides.get(get_principal)
    app.dependency_overrides[get_principal] = lambda: Principal(roles=set(roles))
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_principal, None)
        else:
            app.dependency_overrides[get_principal] = previous


def _factors_for(role: str) -> list[int]:
    with _as_roles(role):
        response = client.get("/v1/risk/infections/brucellosis/factors?panel=full")
    assert response.status_code == 200, response.text
    return [factor["no"] for factor in response.json()]


@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        (KSEC_ROLES, set((20, *range(26, 45)))),
        (KVKN_ROLES, set((6, 7, 8, 9, 10, *range(12, 20)))),
        (MIO_ROLES, {1, 2, 3, 4, 5, 11, 21, 22, 23, 24, 25, 45, 46}),
    ],
)
def test_each_organization_role_gets_only_its_appendix_4_factors(
    roles: tuple[str, ...], expected: set[int],
):
    for role in roles:
        assert set(_factors_for(role)) == expected
        assert role in READ_ROLES
        assert role in WRITE_ROLES


def test_expert_gets_all_brucellosis_factors():
    assert _factors_for(EXPERT) == list(range(1, 47))
    assert EXPERT in READ_ROLES
    assert EXPERT in WRITE_ROLES


def test_keycloak_role_from_jwt_claim_is_normalized_and_authorizes_write():
    """Имена из realm приходят в claim roles и приводятся security.py к верхнему регистру."""
    secret = "test-internal-token-secret"
    settings = Settings(
        GISBB_INTERNAL_TOKEN_ENABLED=True,
        GISBB_INTERNAL_TOKEN_SECRET=secret,
    )
    role = "gisbb_kvkn_inspection_admin"
    token = jwt.encode({"roles": [role]}, secret, algorithm="HS256")

    principal = get_principal(settings, f"Bearer {token}")
    assert principal.has_role(role)
    assert require_roles(*WRITE_ROLES)(principal, settings) is principal


@pytest.mark.parametrize("role", [*KSEC_ROLES, *KVKN_ROLES, *MIO_ROLES, EXPERT])
def test_every_confirmed_role_is_accepted_by_write_guard(role: str):
    settings = Settings(GISBB_INTERNAL_TOKEN_ENABLED=True)
    principal = Principal(roles={role})
    assert require_roles(*WRITE_ROLES)(principal, settings) is principal


def test_preview_rejects_score_for_foreign_factor():
    with _as_roles(KSEC_ROLES[0]):
        response = client.post("/v1/risk/assessments/preview", json={
            "infectionCode": "brucellosis",
            "regionCode": "KZ-T15-PREVIEW",
            "scores": {"1": 4},  # фактор МИО
        })

    assert response.status_code == 403
    assert response.json()["errors"][0]["errorType"] == "ACCESS_DENIED"


def test_create_rejects_foreign_factor_atomically():
    region = "KZ-T15-ATOMIC"
    session = SessionLocal()
    try:
        assessments_before = session.query(Assessment).filter(Assessment.region_code == region).count()
        scores_before = session.query(AssessmentScore).count()
    finally:
        session.close()

    with _as_roles(KSEC_ROLES[0]):
        response = client.post("/v1/risk/assessments", json={
            "infectionCode": "brucellosis",
            "regionCode": region,
            "scores": {"20": 4, "1": 4},  # 20 — КСЭК, 1 — МИО
        })

    assert response.status_code == 403
    session = SessionLocal()
    try:
        assert session.query(Assessment).filter(Assessment.region_code == region).count() == assessments_before
        assert session.query(AssessmentScore).count() == scores_before
    finally:
        session.close()


def test_existing_roles_keep_current_catalog_and_preview_scenarios():
    for role in (FORECAST_ANALYST, SUPER_ADMIN, NCOZ_ADMIN, MCHS_ADMIN):
        assert _factors_for(role) == list(range(1, 47))

    with _as_roles(NCOZ_ADMIN):
        preview = client.post("/v1/risk/assessments/preview", json={
            "infectionCode": "brucellosis",
            "regionCode": "KZ-T15-COMPAT",
            "scores": {"1": 2},
        })
    assert preview.status_code == 200, preview.text


def test_matrix_change_in_database_changes_authorization_without_code_change():
    """Имитация будущей миграции данных методологов: фактор 1 переходит КСЭК."""
    session = SessionLocal()
    row = session.get(FactorOrganization, ("brucellosis", 1, "MIO"))
    assert row is not None
    try:
        row.organization_code = "KSEC"
        session.commit()
        factors = _factors_for(KSEC_ROLES[0])
        assert 1 in factors
    finally:
        row.organization_code = "MIO"
        session.commit()
        session.close()
