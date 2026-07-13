"""Слой доступа к данным (SQLAlchemy).

Боевой профиль — общий gisbb_db, схема ``forecast``. URL БД разрешается в config.py по
приоритету (явный DATABASE_URL → платформенный SPRING_DATASOURCE_* → localhost). Для
локального запуска и тестов допускается SQLite (schema не применяется). Схема и её выдача
gisbb_service создаются идемпотентно при старте.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

log = logging.getLogger("gisbb-forecast.db")

_settings = get_settings()
_url = _settings.sqlalchemy_url
_is_sqlite = _url.startswith("sqlite")
_schema = None if _is_sqlite else _settings.db_schema

engine = create_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    metadata = MetaData(schema=_schema)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(retries: int = 10, delay_seconds: float = 3.0) -> None:
    """Создать схему (для PostgreSQL) и таблицы, если их ещё нет.

    В кластере под может стартовать раньше готовности БД, поэтому подключение к БД
    выполняется с ограниченным числом повторов, а не падает с первой попытки.
    """
    from . import models  # noqa: F401  (регистрация моделей в metadata)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if not _is_sqlite and _schema:
                with engine.begin() as conn:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_schema}"))
                    conn.execute(text(f"GRANT ALL ON SCHEMA {_schema} TO gisbb_service"))
            Base.metadata.create_all(engine)
            return
        except OperationalError as exc:
            last_error = exc
            log.warning(
                "Не удалось подключиться к БД (попытка %s/%s): %s", attempt, retries, exc
            )
            if attempt < retries:
                time.sleep(delay_seconds)
    assert last_error is not None
    raise last_error
