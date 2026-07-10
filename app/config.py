"""Конфигурация сервиса. Значения по умолчанию совпадают с local-профилем платформы;
в dev/prod переопределяются переменными окружения (в т.ч. из ConfigMap gisbb-config).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = Field("gisbb-forecast", alias="APP_NAME")
    server_port: int = Field(8100, alias="SERVER_PORT")

    # Единая БД gisbb_db, отдельная схема домена (см. контракт БД платформы).
    database_url: str = Field(
        "postgresql+psycopg://gisbb_service:qaZ-GiS-22-BB@localhost:5432/gisbb_db",
        alias="DATABASE_URL",
    )
    db_schema: str = Field("forecast", alias="FORECAST_DB_SCHEMA")

    # Внутренний HMAC-токен шлюза (X-Internal-Authorization). Секрет общий для всех
    # сервисов — Spring-свойство gisbb.internal-token.secret.
    internal_token_secret: str = Field(
        "supersecretkey_supersecretkey_supersecretkey",
        alias="GISBB_INTERNAL_TOKEN_SECRET",
    )
    internal_token_enabled: bool = Field(True, alias="GISBB_INTERNAL_TOKEN_ENABLED")
    internal_token_issuer: str = Field("gisbb-gateway", alias="GISBB_INTERNAL_TOKEN_ISSUER")
    internal_token_audience: str = Field("gisbb-internal", alias="GISBB_INTERNAL_TOKEN_AUDIENCE")

    # Регистрация в Eureka. По умолчанию выключена, чтобы сервис поднимался локально без
    # реестра; в кластере включается EUREKA_ENABLED=true.
    eureka_enabled: bool = Field(False, alias="EUREKA_ENABLED")
    eureka_default_zone: str = Field(
        "http://localhost:8761/eureka/", alias="EUREKA_DEFAULT_ZONE"
    )

    # Порог точности прогноза из ТЗ 4.10.6.2 — не менее 80 %.
    accuracy_target: float = Field(0.80, alias="ACCURACY_TARGET")


@lru_cache
def get_settings() -> Settings:
    return Settings()
