"""Доменные события раздела «Оценка риска» (T-19A).

Канал доставки уведомлений ещё не выбран аналитиком, поэтому пока фиксируем только
факт срабатывания — структурированной записью в лог. Постоянное хранилище (outbox) и
сам транспорт — отдельная задача, меняющая схему БД, сюда не входит.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("gisbb-forecast.risk.events")


def log_red_trigger_event(
    *,
    assessment_id: int,
    infection_code: str,
    region_code: str,
    period: str | None,
    red_triggers: list[dict[str, Any]],
) -> None:
    """Зафиксировать срабатывание красного триггера при сохранении оценки.

    Вызывается только для реально сохранённых оценок — предпросмотр в калькуляторе
    (persist=False) события не создаёт, иначе каждый пересчёт при вводе баллов
    порождал бы ложные срабатывания.
    """
    log.warning(
        "RED_TRIGGER assessmentId=%s infectionCode=%s regionCode=%s period=%s factors=%s",
        assessment_id, infection_code, region_code, period,
        [rt.get("no") for rt in red_triggers],
    )
