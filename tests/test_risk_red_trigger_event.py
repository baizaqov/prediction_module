"""T-19A: фиксация события красного триггера при сохранении оценки."""
from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)

_EVENT_LOGGER = "gisbb-forecast.risk.events"


def test_saving_assessment_with_red_trigger_logs_event(caplog):
    with caplog.at_level(logging.WARNING, logger=_EVENT_LOGGER):
        response = client.post("/v1/risk/assessments", json={
            "infectionCode": "brucellosis",
            "regionCode": "KZ-T19A-TRIGGER",
            "periodFrom": "2026-01-01",
            "periodTo": "2026-01-01",
            "scores": {"17": 4},  # фактор с признаком «красный триггер»
        })

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["hasRedTrigger"] is True

    events = [r for r in caplog.records if r.name == _EVENT_LOGGER]
    assert len(events) == 1
    assert "RED_TRIGGER" in events[0].getMessage()
    assert f"assessmentId={body['assessmentId']}" in events[0].getMessage()
    assert "regionCode=KZ-T19A-TRIGGER" in events[0].getMessage()


def test_saving_assessment_without_red_trigger_does_not_log_event(caplog):
    with caplog.at_level(logging.WARNING, logger=_EVENT_LOGGER):
        response = client.post("/v1/risk/assessments", json={
            "infectionCode": "brucellosis",
            "regionCode": "KZ-T19A-NORMAL",
            "periodFrom": "2026-01-01",
            "periodTo": "2026-01-01",
            "scores": {"1": 1},
        })

    assert response.status_code == 200, response.text
    assert response.json()["hasRedTrigger"] is False
    assert [r for r in caplog.records if r.name == _EVENT_LOGGER] == []


def test_preview_with_red_trigger_does_not_log_event(caplog):
    """Предпросмотр (persist=False) ничего не сохраняет — событие не фиксируется."""
    with caplog.at_level(logging.WARNING, logger=_EVENT_LOGGER):
        response = client.post("/v1/risk/assessments/preview", json={
            "infectionCode": "brucellosis",
            "regionCode": "KZ-T19A-PREVIEW",
            "periodFrom": "2026-01-01",
            "periodTo": "2026-01-01",
            "scores": {"17": 4},
        })

    assert response.status_code == 200, response.text
    assert response.json()["hasRedTrigger"] is True
    assert [r for r in caplog.records if r.name == _EVENT_LOGGER] == []
