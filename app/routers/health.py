"""Health/status для Eureka healthcheck и status page (прямой доступ, не через шлюз)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/actuator/health")
@router.get("/health")
def health() -> dict:
    return {"status": "UP"}


@router.get("/actuator/info")
def info() -> dict:
    return {"app": {"name": "gisbb-forecast", "description": "Прогнозирование и оценка биорисков"}}
