"""Слой доступа к данным (SQLAlchemy).

Боевой профиль — общий gisbb_db, схема ``forecast``. Для локального запуска и тестов
допускается SQLite (schema не применяется). Схема и её выдача gisbb_service создаются
идемпотентно при старте; таблицы — через create_all (для MVP). Для централизованного
раннера gisbb-db-migration поддерживается эквивалентный SQL-скрипт в db/changelog.
"""
from __future__ import annotations

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

_settings = get_settings()
_is_sqlite = _settings.database_url.startswith("sqlite")
_schema = None if _is_sqlite else _settings.db_schema

engine = create_engine(
    _settings.database_url,
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


def init_db() -> None:
    """Создать схему (для PostgreSQL) и таблицы, если их ещё нет."""
    from . import models  # noqa: F401  (регистрация моделей в metadata)

    if not _is_sqlite and _schema:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_schema}"))
            conn.execute(text(f"GRANT ALL ON SCHEMA {_schema} TO gisbb_service"))
    Base.metadata.create_all(engine)
