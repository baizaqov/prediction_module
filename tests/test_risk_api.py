"""Smoke-тесты API оценки рисков: каталоги, факторы, расчёт и сохранение оценки."""
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_infections_seeded():
    r = client.get("/v1/risk/infections")
    assert r.status_code == 200
    codes = {i["code"] for i in r.json()}
    assert "plague" in codes
    assert len(codes) == 13


def test_plague_basic_panel_factors():
    r = client.get("/v1/risk/infections/plague/factors?panel=basic")
    assert r.status_code == 200
    factors = r.json()
    assert len(factors) == 50
    assert all(f["tier"] == "basic" for f in factors)


def test_unknown_infection_404():
    r = client.get("/v1/risk/infections/nope/factors")
    assert r.status_code == 404


def test_preview_assessment_computes_index():
    body = {
        "infectionCode": "plague",
        "regionCode": "KZ-15",
        "panel": "basic",
        "scores": {"1": 3, "2": 4},
    }
    r = client.post("/v1/risk/assessments/preview", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["panelSize"] == 50
    assert data["assessed"] == 2
    assert data["integralIndex"] is not None
    assert data["level"] in ("low", "medium", "high", "very_high", "red_trigger")
    assert data["assessmentId"] is None  # preview не сохраняет


def test_create_assessment_persists():
    body = {
        "infectionCode": "plague",
        "regionCode": "KZ-15",
        "period": "2026-весна",
        "panel": "basic",
        "scores": {"1": 2, "2": 2, "5": 1},
    }
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["assessmentId"] is not None
    assert data["assessed"] == 3
    assert 0.0 <= data["completeness"] <= 1.0
