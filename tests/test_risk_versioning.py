"""T-26/T-11: пересчёт создаёт новую версию записи реестра, актуальна последняя."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)

_BODY = {
    "infectionCode": "plague",
    "regionCode": "KZ-T26-VERSION",
    "periodFrom": "2026-01-01",
    "periodTo": "2026-01-31",
    "scores": {"1": 2},
}


def _save(**overrides) -> dict:
    body = {**_BODY, **overrides}
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_first_save_is_version_one():
    saved = _save(regionCode="KZ-T26-FIRST")
    assert saved["version"] == 1


def test_repeated_save_of_same_registry_record_increments_version():
    first = _save(regionCode="KZ-T26-REPEAT")
    second = _save(regionCode="KZ-T26-REPEAT")
    third = _save(regionCode="KZ-T26-REPEAT")

    assert [first["version"], second["version"], third["version"]] == [1, 2, 3]
    # Каждая версия — отдельная строка с собственным id, не update той же записи.
    assert len({first["assessmentId"], second["assessmentId"], third["assessmentId"]}) == 3


def test_different_registry_record_starts_its_own_version_sequence():
    """Другой период — другая «запись реестра», версии не пересекаются."""
    _save(regionCode="KZ-T26-ISOLATED", periodFrom="2026-01-01", periodTo="2026-01-31")
    other_period = _save(regionCode="KZ-T26-ISOLATED", periodFrom="2026-02-01", periodTo="2026-02-28")
    assert other_period["version"] == 1


def test_preview_does_not_carry_a_version():
    r = client.post("/v1/risk/assessments/preview", json={**_BODY, "regionCode": "KZ-T26-PREVIEW"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] is None


def test_journal_shows_only_the_latest_version():
    first = _save(regionCode="KZ-T11-JOURNAL")
    second = _save(regionCode="KZ-T11-JOURNAL")

    r = client.get("/v1/risk/assessments", params={"regionCode": "KZ-T11-JOURNAL"})
    data = r.json()
    assert data["totalElements"] == 1
    row = data["content"][0]
    assert row["id"] == second["assessmentId"]
    assert row["id"] != first["assessmentId"]
    assert row["version"] == 2


def test_previous_version_still_reachable_by_id_after_being_superseded():
    """T-26: предыдущая версия сохраняется в истории — доступна напрямую по id."""
    first = _save(regionCode="KZ-T11-HISTORY")
    _save(regionCode="KZ-T11-HISTORY")  # версия 2 перекрывает первую в журнале

    r = client.get(f"/v1/risk/assessments/{first['assessmentId']}")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["version"] == 1
    assert detail["id"] == first["assessmentId"]
