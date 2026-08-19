"""T-09: район отдельно от региона + «Обобщённо по региону» (решение БА)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, init_db
from app.main import app
from app.risk.models import Assessment

init_db()
client = TestClient(app)

_BODY = {
    "infectionCode": "plague",
    "periodFrom": "2026-01-01",
    "periodTo": "2026-01-01",
    "scores": {"1": 2},
}


def test_district_code_alone_is_accepted():
    body = {**_BODY, "regionCode": "KZ-T09-DISTRICT", "districtCode": "KZ-T09-DISTRICT-01"}
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["districtCode"] == "KZ-T09-DISTRICT-01"
    assert data["isRegionWide"] is False


def test_region_wide_alone_is_accepted():
    body = {**_BODY, "regionCode": "KZ-T09-WIDE", "isRegionWide": True}
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["districtCode"] is None
    assert data["isRegionWide"] is True


def test_neither_district_nor_region_wide_is_accepted():
    """Район просто не выбран — третье, отдельное от «Обобщённо», состояние."""
    body = {**_BODY, "regionCode": "KZ-T09-NEITHER"}
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["districtCode"] is None
    assert data["isRegionWide"] is False


def test_district_code_and_region_wide_together_rejected_by_api():
    body = {
        **_BODY, "regionCode": "KZ-T09-CONFLICT",
        "districtCode": "KZ-T09-CONFLICT-01", "isRegionWide": True,
    }
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 422


def test_district_code_and_region_wide_together_rejected_by_db():
    """Тот же инвариант проверен на уровне БД, в обход API-валидации."""
    session = SessionLocal()
    try:
        session.add(Assessment(
            infection_code="plague",
            region_code="KZ-T09-DB-CONFLICT",
            district_code="KZ-T09-DB-CONFLICT-01",
            is_region_wide=True,
            period_from=date(2026, 1, 1),
            period_to=date(2026, 1, 1),
            panel="basic",
            level="not_assessed",
            level_ru="не оценено",
        ))
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_list_assessments_filters_by_district_code():
    client.post("/v1/risk/assessments", json={
        **_BODY, "regionCode": "KZ-T09-FILTER", "districtCode": "KZ-T09-FILTER-A",
    })
    client.post("/v1/risk/assessments", json={
        **_BODY, "regionCode": "KZ-T09-FILTER", "districtCode": "KZ-T09-FILTER-B",
    })

    r_all = client.get("/v1/risk/assessments", params={"regionCode": "KZ-T09-FILTER"})
    assert r_all.json()["totalElements"] == 2

    r = client.get("/v1/risk/assessments", params={
        "regionCode": "KZ-T09-FILTER", "districtCode": "KZ-T09-FILTER-A",
    })
    data = r.json()
    assert data["totalElements"] == 1
    assert data["content"][0]["districtCode"] == "KZ-T09-FILTER-A"


def test_search_matches_district_code():
    client.post("/v1/risk/assessments", json={
        **_BODY, "regionCode": "KZ-T09-SEARCH", "districtCode": "KZ-T09-SEARCH-UNIQUEDIST",
    })

    r = client.get("/v1/risk/assessments", params={"search": "uniquedist"})
    data = r.json()
    assert data["totalElements"] == 1
    assert data["content"][0]["districtCode"] == "KZ-T09-SEARCH-UNIQUEDIST"
