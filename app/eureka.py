"""Регистрация сервиса в Netflix Eureka.

FastAPI-сервис — первый не-JVM регистрант в реестре, поэтому используется REST-клиент
py_eureka_client: он публикует инстанс и шлёт heartbeat. app_name = spring.application.name
(= id для lb://). Регистрация опциональна и не должна валить старт сервиса при недоступном
реестре.

ВАЖНО (Kubernetes): по умолчанию py-eureka-client регистрирует инстанс по hostName, который
в поде равен имени пода (например ``gisbb-forecast-5bdfdf975b-g8rrw``). Кластерный DNS такое
имя не резолвит, и шлюз на маршруте ``lb://gisbb-forecast`` падает с UnknownHostException →
500. Java-сервисы регистрируются по IP (``eureka.instance.prefer-ip-address=true``); повторяем
это поведение — определяем IP пода и регистрируемся по нему (и hostName, и ipAddr = IP пода).
"""
from __future__ import annotations

import logging
import os
import socket
from urllib.parse import urlparse

from .config import Settings

log = logging.getLogger("gisbb-forecast.eureka")

_started = False


def _resolve_instance_ip(settings: Settings) -> str:
    """IP пода для регистрации в Eureka.

    Приоритет: явный ``POD_IP`` (Kubernetes downward API) / ``EUREKA_INSTANCE_IP`` →
    автоопределение локального IP интерфейса, через который идёт трафик к реестру.
    """
    explicit = os.getenv("POD_IP") or os.getenv("EUREKA_INSTANCE_IP")
    if explicit:
        return explicit.strip()

    # Пытаемся определить исходящий интерфейс к самому реестру (в мультихоум-случае — верный
    # IP), затем — по литеральному адресу, который не требует DNS (запасной вариант, если
    # имя реестра локально не резолвится).
    candidates = []
    parsed = urlparse(settings.resolved_eureka_zone)
    if parsed.hostname:
        candidates.append(parsed.hostname)
    candidates.append("10.254.254.254")  # литерал: DNS не нужен, пакеты не шлются

    for target in candidates:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # UDP-«connect» не шлёт пакетов: ядро лишь выбирает исходящий интерфейс,
            # и getsockname() возвращает его локальный IP (= IP пода в кластере).
            sock.connect((target, 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            continue
        finally:
            sock.close()

    log.warning("Could not auto-detect instance IP; falling back to library default")
    return ""


async def start(settings: Settings) -> None:
    global _started
    if not settings.eureka_enabled:
        return
    try:
        import py_eureka_client.eureka_client as eureka_client

        instance_ip = _resolve_instance_ip(settings)

        init_kwargs = dict(
            eureka_server=settings.resolved_eureka_zone,
            app_name=settings.app_name,
            instance_port=settings.server_port,
            status_page_url="/actuator/info",
            health_check_url="/actuator/health",
            renewal_interval_in_secs=30,
        )
        # Регистрируемся по IP пода, а не по hostName (= имя пода), которое не резолвится
        # кластерным DNS. Если IP определить не удалось — оставляем поведение библиотеки.
        if instance_ip:
            init_kwargs["instance_host"] = instance_ip
            init_kwargs["instance_ip"] = instance_ip

        await eureka_client.init_async(**init_kwargs)
        _started = True
        log.info(
            "Registered with Eureka at %s as %s (host=%s)",
            settings.resolved_eureka_zone, settings.app_name, instance_ip or "auto",
        )
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
