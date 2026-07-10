"""Регистрация сервиса в Netflix Eureka.

FastAPI-сервис — первый не-JVM регистрант в реестре, поэтому используется REST-клиент
py_eureka_client: он публикует инстанс и шлёт heartbeat. app_name = spring.application.name
(= id для lb://), instance-id рандомизирован, объявляется IP. Регистрация опциональна и
не должна валить старт сервиса при недоступном реестре.
"""
from __future__ import annotations

import logging

from .config import Settings

log = logging.getLogger("gisbb-forecast.eureka")

_started = False


async def start(settings: Settings) -> None:
    global _started
    if not settings.eureka_enabled:
        return
    try:
        import py_eureka_client.eureka_client as eureka_client

        # Параметры соответствуют сигнатуре py-eureka-client 0.11.x. IP инстанса
        # библиотека определяет автоматически; instance_id генерируется, если пуст.
        # health-эндпоинт продублирован в health.py как /actuator/health и /health.
        await eureka_client.init_async(
            eureka_server=settings.eureka_default_zone,
            app_name=settings.app_name,
            instance_port=settings.server_port,
            status_page_url="/actuator/info",
            health_check_url="/actuator/health",
            renewal_interval_in_secs=30,
        )
        _started = True
        log.info("Registered with Eureka at %s as %s", settings.eureka_default_zone, settings.app_name)
    except Exception as exc:  # noqa: BLE001 — реестр не критичен для локального старта
        log.warning("Eureka registration skipped: %s", exc)


async def stop() -> None:
    global _started
    if not _started:
        return
    try:
        import py_eureka_client.eureka_client as eureka_client

        await eureka_client.stop_async()
    except Exception as exc:  # noqa: BLE001
        log.warning("Eureka deregistration failed: %s", exc)
    finally:
        _started = False
