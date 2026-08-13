"""Smoke-тесты API оценки рисков: каталоги, факторы, расчёт и сохранение оценки."""
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.risk.models import Assessment, AssessmentScore, Factor

init_db()
client = TestClient(app)


def _get_factor_weight(infection_code: str, factor_no: int) -> int:
    session = SessionLocal()
    try:
        return session.get(Factor, (infection_code, factor_no)).weight
    finally:
        session.close()


def _set_factor_weight(infection_code: str, factor_no: int, weight: int) -> None:
    """Смоделировать правку веса в справочнике (как это будет делать Эксперт после T-13)."""
    session = SessionLocal()
    try:
        factor = session.get(Factor, (infection_code, factor_no))
        factor.weight = weight
        session.commit()
    finally:
        session.close()


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


def _create_assessment(infection_code: str, region_code: str, period: str) -> dict:
    body = {
        "infectionCode": infection_code,
        "regionCode": region_code,
        "period": period,
        "panel": "basic",
        "scores": {"1": 2},
    }
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200
    return r.json()


def test_list_assessments_filters_by_infection():
    _create_assessment("tularemia", "KZ-J01", "2026-J1")
    _create_assessment("measles", "KZ-J01", "2026-J1")

    r_all = client.get("/v1/risk/assessments", params={"regionCode": "KZ-J01"})
    assert r_all.status_code == 200
    assert r_all.json()["totalElements"] == 2

    r = client.get("/v1/risk/assessments",
                   params={"regionCode": "KZ-J01", "infectionCode": "tularemia"})
    assert r.status_code == 200
    data = r.json()
    assert data["totalElements"] == 1
    row = data["content"][0]
    assert row["infectionCode"] == "tularemia"
    assert row["infectionNameRu"]
    assert row["regionCode"] == "KZ-J01"
    assert row["period"] == "2026-J1"
    assert row["panel"] == "basic"
    assert row["assessed"] == 1
    assert row["level"] in ("not_assessed", "low", "medium", "high", "very_high", "red_trigger")
    assert row["levelRu"]
    assert isinstance(row["hasRedTrigger"], bool)
    assert "createdAt" in row


def test_list_assessments_filters_by_region():
    _create_assessment("rabies", "KZ-J02", "2026-J1")
    _create_assessment("rabies", "KZ-J03", "2026-J1")

    r_all = client.get("/v1/risk/assessments", params={"infectionCode": "rabies"})
    assert r_all.status_code == 200
    assert r_all.json()["totalElements"] == 2

    r = client.get("/v1/risk/assessments",
                   params={"infectionCode": "rabies", "regionCode": "KZ-J02"})
    data = r.json()
    assert data["totalElements"] == 1
    assert data["content"][0]["regionCode"] == "KZ-J02"


def test_list_assessments_filters_by_period():
    _create_assessment("anthrax", "KZ-J04", "2026-P1")
    _create_assessment("anthrax", "KZ-J04", "2026-P2")

    r_all = client.get("/v1/risk/assessments", params={"regionCode": "KZ-J04"})
    assert r_all.json()["totalElements"] == 2

    r = client.get("/v1/risk/assessments",
                   params={"regionCode": "KZ-J04", "period": "2026-P1"})
    data = r.json()
    assert data["totalElements"] == 1
    assert data["content"][0]["period"] == "2026-P1"


def test_list_assessments_pagination():
    created_ids = [
        _create_assessment("cholera", "KZ-J05", f"2026-P{i}")["assessmentId"] for i in range(5)
    ]

    r1 = client.get("/v1/risk/assessments", params={"regionCode": "KZ-J05", "page": 0, "size": 2})
    d1 = r1.json()
    assert d1["totalElements"] == 5
    assert d1["page"] == 0
    assert d1["size"] == 2
    assert len(d1["content"]) == 2
    # сортировка по умолчанию — по убыванию даты сохранения: сначала последние созданные
    assert d1["content"][0]["id"] == created_ids[-1]
    assert d1["content"][1]["id"] == created_ids[-2]

    r2 = client.get("/v1/risk/assessments", params={"regionCode": "KZ-J05", "page": 1, "size": 2})
    d2 = r2.json()
    assert len(d2["content"]) == 2
    assert {c["id"] for c in d1["content"]}.isdisjoint({c["id"] for c in d2["content"]})

    r3 = client.get("/v1/risk/assessments", params={"regionCode": "KZ-J05", "page": 2, "size": 2})
    d3 = r3.json()
    assert len(d3["content"]) == 1
    assert d3["content"][0]["id"] == created_ids[0]


def test_list_assessments_empty_result():
    r = client.get("/v1/risk/assessments", params={"regionCode": "KZ-NOPE-999"})
    assert r.status_code == 200
    data = r.json()
    assert data["content"] == []
    assert data["totalElements"] == 0


def test_saved_assessment_result_and_weight_snapshot_match_engine_and_db():
    """T-07: сохранённые расчётные величины и снимок весов совпадают с ответом API и с БД."""
    weight_1 = _get_factor_weight("plague", 1)
    weight_2 = _get_factor_weight("plague", 2)

    body = {
        "infectionCode": "plague",
        "regionCode": "KZ-T07-DB",
        "period": "2026-T07",
        "panel": "basic",
        "scores": {"1": 3, "2": 2},
    }
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200
    saved = r.json()

    session = SessionLocal()
    try:
        row = session.get(Assessment, saved["assessmentId"])
        assert row is not None
        assert row.panel_size == saved["panelSize"]
        assert row.assessed == saved["assessed"] == 2
        assert row.integral_index == saved["integralIndex"]
        assert row.completeness == saved["completeness"]
        assert row.adjusted_index == saved["adjustedIndex"]
        assert row.level == saved["level"]
        assert row.level_ru == saved["levelRu"]
        assert row.has_red_trigger == saved["hasRedTrigger"]

        scores = {
            s.factor_no: s.weight
            for s in session.query(AssessmentScore).filter(AssessmentScore.assessment_id == row.id)
        }
        assert scores[1] == weight_1
        assert scores[2] == weight_2
    finally:
        session.close()


def test_journal_returns_same_values_as_post_response():
    body = {
        "infectionCode": "cholera",
        "regionCode": "KZ-T07-JOURNAL",
        "period": "2026-T07",
        "panel": "basic",
        "scores": {"1": 4},
    }
    r = client.post("/v1/risk/assessments", json=body)
    assert r.status_code == 200
    saved = r.json()

    r2 = client.get("/v1/risk/assessments", params={"regionCode": "KZ-T07-JOURNAL"})
    assert r2.status_code == 200
    row = r2.json()["content"][0]

    assert row["id"] == saved["assessmentId"]
    assert row["level"] == saved["level"]
    assert row["levelRu"] == saved["levelRu"]
    assert row["hasRedTrigger"] == saved["hasRedTrigger"]
    assert row["assessed"] == saved["assessed"]


def test_weight_edit_freezes_saved_assessment_but_applies_to_new_one():
    """Главный тест T-07 (снимок весов).

    Правка веса фактора в справочнике после сохранения оценки не должна задним числом
    менять её уровень (ни при чтении журнала, ни при повторном чтении той же записи) —
    он читается из снимка. Новая оценка, рассчитанная после правки, использует уже новый вес.
    """
    original_weight = _get_factor_weight("plague", 1)
    try:
        _set_factor_weight("plague", 1, 1)  # детерминированная стартовая точка

        body = {
            "infectionCode": "plague",
            "regionCode": "KZ-T07-WEIGHTEDIT",
            "panel": "basic",
            "scores": {"1": 4},
        }
        r1 = client.post("/v1/risk/assessments", json=body)
        assert r1.status_code == 200
        first = r1.json()
        assert first["integralIndex"] == 4.0
        assert first["level"] == "medium"  # 3.0 <= 4.0 < 5.0

        # Правка каталога после сохранения — как правка веса Экспертом (T-13).
        _set_factor_weight("plague", 1, 4)

        # Прошлая оценка не меняется: по новому весу это было бы 4*4=16 -> very_high,
        # но журнал обязан вернуть исходный medium из снимка.
        r_journal = client.get("/v1/risk/assessments", params={"regionCode": "KZ-T07-WEIGHTEDIT"})
        assert r_journal.status_code == 200
        row = r_journal.json()["content"][0]
        assert row["id"] == first["assessmentId"]
        assert row["level"] == "medium"
        assert row["levelRu"] == first["levelRu"]
        assert row["hasRedTrigger"] == first["hasRedTrigger"]

        # Новая оценка того же расчёта — уже по новому весу.
        r2 = client.post("/v1/risk/assessments", json=body)
        assert r2.status_code == 200
        second = r2.json()
        assert second["assessmentId"] != first["assessmentId"]
        assert second["integralIndex"] == 16.0
        assert second["level"] == "very_high"
    finally:
        _set_factor_weight("plague", 1, original_weight)
