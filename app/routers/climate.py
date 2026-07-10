"""Функция получения климатических данных (ТЗ 4.10.6.1)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_session
from ..roles import READ_ROLES, WRITE_ROLES
from ..schemas import ClimateObservationOut, ClimateRefreshRequest, ClimateRefreshResult
from ..security import require_roles
from ..services import forecast_service

router = APIRouter(prefix="/v1/climate", tags=["climate"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/refresh", response_model=ClimateRefreshResult,
             summary="Загрузить климатические наблюдения (Казгидромет)")
def refresh(
    body: ClimateRefreshRequest,
    session: SessionDep,
    _=Depends(require_roles(*WRITE_ROLES)),
):
    return forecast_service.refresh_climate(session, body.regions)


@router.get("", response_model=list[ClimateObservationOut],
            summary="Климатические наблюдения")
def list_climate(
    session: SessionDep,
    _=Depends(require_roles(*READ_ROLES)),
    region: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    rows = forecast_service.list_climate(session, region, limit)
    return [
        ClimateObservationOut(
            regionCode=r.region_code,
            period=r.period,
            tempC=r.temp_c,
            humidity=r.humidity,
            precipMm=r.precip_mm,
            source=r.source,
        )
        for r in rows
    ]
