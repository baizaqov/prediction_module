"""Тесты API: методы, климат, обучение, прогноз, сохранение прогонов."""
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_health():
    r = client.get("/actuator/health")
    assert r.status_code == 200
    assert r.json()["status"] == "UP"


def test_methods_catalog():
    r = client.get("/v1/methods?task=regression")
    assert r.status_code == 200
    codes = {m["code"] for m in r.json()}
    assert "GRADIENT_BOOSTING" in codes
    assert any(m["isDefault"] for m in r.json())


def test_help():
    r = client.get("/v1/help")
    assert r.status_code == 200
    assert "sections" in r.json()


def test_climate_refresh_and_list():
    r = client.post("/v1/climate/refresh", json={"regions": ["KZ-01", "KZ-02"]})
    assert r.status_code == 200
    assert r.json()["ingested"] > 0
    r2 = client.get("/v1/climate?region=KZ-01&limit=10")
    assert r2.status_code == 200
    assert len(r2.json()) == 10
    assert r2.json()[0]["regionCode"] == "KZ-01"


def test_train_model():
    r = client.post("/v1/models/train", json={"method": "GRADIENT_BOOSTING"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accuracy"] >= 0.80
    assert body["meetsAccuracyTarget"] is True
    assert body["id"]


def test_run_forecast_and_persist():
    r = client.post(
        "/v1/forecast/run",
        json={
            "method": "GRADIENT_BOOSTING",
            "regions": ["KZ-01", "KZ-03"],
            "diseaseCode": "A20",
            "horizonMonths": 6,
            "planningType": "UNPLANNED",
            "save": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert len(body["regions"]) == 2
    assert len(body["regions"][0]["forecast"]) == 6
    assert len(body["geo"]) == 2
    assert body["geo"][0]["riskLevel"] in {"LOW", "MEDIUM", "HIGH"}

    run_id = body["id"]
    r2 = client.get(f"/v1/forecast/runs/{run_id}")
    assert r2.status_code == 200
    assert r2.json()["id"] == run_id

    r3 = client.get("/v1/forecast/runs?page=0&size=10")
    assert r3.status_code == 200
    assert r3.json()["totalElements"] >= 1


def test_forecast_with_saved_model_reports_model_method():
    # Обучаем RANDOM_FOREST, затем прогоняем прогноз по его id, оставляя method по
    # умолчанию (GRADIENT_BOOSTING). Ответ должен отражать метод модели, а не запроса.
    trained = client.post("/v1/models/train", json={"method": "RANDOM_FOREST"})
    assert trained.status_code == 200, trained.text
    model_id = trained.json()["id"]

    run = client.post(
        "/v1/forecast/run",
        json={"modelId": model_id, "regions": ["KZ-02"], "horizonMonths": 3, "save": True},
    )
    assert run.status_code == 200, run.text
    assert run.json()["method"] == "RANDOM_FOREST"

    # И в сохранённом прогоне тоже.
    saved = client.get(f"/v1/forecast/runs/{run.json()['id']}")
    assert saved.json()["method"] == "RANDOM_FOREST"
