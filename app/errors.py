"""Формат ошибок, совместимый с платформой (gisbb-common-web BaseGlobalExceptionHandler):
{ "message": str, "errors": [ { "errorType", "serviceType", "params", "text" } ] }.
"""
from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse


def error_body(message: str, error_type: str = "SERVICE_ERROR", text: str | None = None) -> dict:
    return {
        "message": message,
        "errors": [
            {
                "errorType": error_type,
                "serviceType": "FORECAST_SERVICE",
                "params": {},
                "text": text or message,
            }
        ],
    }


class ForecastError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST,
                 error_type: str = "SERVICE_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type


async def forecast_error_handler(_: Request, exc: ForecastError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.message, exc.error_type),
    )
