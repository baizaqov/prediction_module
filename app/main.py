"""Точка входа сервиса gisbb-forecast (Прогнозирование и оценка биорисков, ТЗ 4.10.6).

За шлюзом сервис доступен по префиксу /api/forecast/** (StripPrefix=2), поэтому FastAPI
знает о префиксе через root_path — так корректно работают Swagger UI и ссылки OpenAPI
(/api/forecast/docs). Прикладные маршруты смонтированы под /v1/**; health — напрямую.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import init_db
from .errors import ForecastError, error_body, forecast_error_handler
from .routers import climate, forecast, health, meta, risk

logging.basicConfig(level=logging.INFO)

GATEWAY_PREFIX = "/api/forecast"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    from . import eureka

    await eureka.start(settings)
    try:
        yield
    finally:
        await eureka.stop()


app = FastAPI(
    title="ГИС ББ — Прогнозирование и оценка биологических рисков",
    description="Модуль 4.10.6: климат, обучение моделей, прогноз заболеваемости, визуализация.",
    version="0.1.0",
    root_path=GATEWAY_PREFIX,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_exception_handler(ForecastError, forecast_error_handler)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body("Ошибка валидации запроса", error_type="VALIDATION",
                           text=str(exc.errors())),
    )


# health монтируется без gateway-префикса (Eureka обращается напрямую к инстансу).
app.include_router(health.router)
app.include_router(meta.router)
app.include_router(climate.router)
app.include_router(forecast.router)
app.include_router(risk.router)
