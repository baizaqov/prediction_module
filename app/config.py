"""Конфигурация сервиса.

Приоритет источников БД и Eureka выстроен так, чтобы сервис работал с тем же общим
ConfigMap/Secret (`gisbb-config`/`gisbb-secret`), который через envFrom монтируют все
Java-сервисы, — без отдельной конфигурации деплоя:

1. явный `DATABASE_URL` (SQLAlchemy-формат) — если задан оператором, побеждает;
2. иначе платформенный `SPRING_DATASOURCE_URL` (JDBC) + `SPRING_DATASOURCE_USERNAME/PASSWORD`
   из общего ConfigMap/Secret — конвертируется в SQLAlchemy URL;
3. иначе локальный дефолт (localhost) для разработки.

Аналогично Eureka читает платформенный `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE`, а порт —
`SERVER_PORT` (в кластере = 8080).
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_DB_DEFAULT = "postgresql+psycopg://gisbb_service:qaZ-GiS-22-BB@localhost:5432/gisbb_db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = Field("gisbb-forecast", alias="APP_NAME")
    server_port: int = Field(8100, alias="SERVER_PORT")

    # Явный SQLAlchemy-URL (высший приоритет). Пусто → берём платформенный datasource.
    database_url: str = Field("", alias="DATABASE_URL")
    db_schema: str = Field("forecast", alias="FORECAST_DB_SCHEMA")

    # Платформенный datasource из общего ConfigMap/Secret (как у Java-сервисов).
    spring_datasource_url: str = Field("", alias="SPRING_DATASOURCE_URL")
    spring_datasource_username: str = Field("", alias="SPRING_DATASOURCE_USERNAME")
    spring_datasource_password: str = Field("", alias="SPRING_DATASOURCE_PASSWORD")

    # Внутренний HMAC-токен шлюза (X-Internal-Authorization). Секрет общий для всех сервисов.
    internal_token_secret: str = Field(
        "supersecretkey_supersecretkey_supersecretkey",
        alias="GISBB_INTERNAL_TOKEN_SECRET",
    )
    internal_token_enabled: bool = Field(True, alias="GISBB_INTERNAL_TOKEN_ENABLED")
    internal_token_issuer: str = Field("gisbb-gateway", alias="GISBB_INTERNAL_TOKEN_ISSUER")
    internal_token_audience: str = Field("gisbb-internal", alias="GISBB_INTERNAL_TOKEN_AUDIENCE")

    # Регистрация в Eureka. EUREKA_DEFAULT_ZONE — свой алиас; в кластере доступен
    # платформенный EUREKA_CLIENT_SERVICEURL_DEFAULTZONE (Spring-имя) — он резервный.
    eureka_enabled: bool = Field(False, alias="EUREKA_ENABLED")
    eureka_default_zone: str = Field("", alias="EUREKA_DEFAULT_ZONE")
    eureka_spring_zone: str = Field("", alias="EUREKA_CLIENT_SERVICEURL_DEFAULTZONE")

    # Порог точности прогноза из ТЗ 4.10.6.2 — не менее 80 %.
    accuracy_target: float = Field(0.80, alias="ACCURACY_TARGET")

    @property
    def sqlalchemy_url(self) -> str:
        """Итоговый URL для SQLAlchemy по приоритету источников."""
        if self.database_url:
            return self.database_url
        if self.spring_datasource_url:
            return _jdbc_to_sqlalchemy(
                self.spring_datasource_url,
                self.spring_datasource_username,
                self.spring_datasource_password,
            )
        return _LOCAL_DB_DEFAULT

    @property
    def resolved_eureka_zone(self) -> str:
        return self.eureka_default_zone or self.eureka_spring_zone or "http://localhost:8761/eureka/"


def _jdbc_to_sqlalchemy(jdbc_url: str, username: str, password: str) -> str:
    """Преобразовать `jdbc:postgresql://host:port/db[?params]` в SQLAlchemy URL psycopg.

    Учётные данные (из общего Secret) внедряются в URL с URL-кодированием.
    """
    url = jdbc_url[len("jdbc:"):] if jdbc_url.startswith("jdbc:") else jdbc_url
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            rest = url[len(scheme):]
            break
    else:
        # Уже SQLAlchemy-подобный или нестандартный — вернём как есть.
        return jdbc_url

    creds = ""
    if username:
        creds = f"{quote(username, safe='')}:{quote(password, safe='')}@" if password \
            else f"{quote(username, safe='')}@"
    return f"postgresql+psycopg://{creds}{rest}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
