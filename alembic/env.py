"""Alembic env для gisbb-forecast.

БД gisbb_db общая для всей платформы: своя схема есть только у forecast (SQLAlchemy
``Base``, app/db.py) и bb_risk (``RiskBase``, app/risk/models.py). Остальные схемы
принадлежат Java-сервисам платформы и autogenerate не должен их видеть — иначе при
сравнении с пустой (для нас) метадатой он предложит DROP на чужие таблицы.
Поэтому include_name отсекает чужие схемы ещё на этапе обхода, до сравнения объектов,
а include_object — дополнительный фильтр на уровне таблиц/колонок/constraint'ов.

URL берётся из app.config.get_settings().sqlalchemy_url — та же приоритетная цепочка
источников (explicit DATABASE_URL → платформенный SPRING_DATASOURCE_* → localhost), что
и у самого сервиса. sqlalchemy.url в alembic.ini сознательно не используется: пароль из
платформенного Secret может содержать символы, которые ConfigParser интерпретирует как
свои (например ``%``).
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, text

from alembic import context

sys.path.insert(0, os.getcwd())

from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
from app import models as _forecast_models  # noqa: E402,F401  регистрирует таблицы forecast
from app.risk import models as _risk_models  # noqa: E402  регистрирует таблицы bb_risk

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = [Base.metadata, _risk_models.RiskBase.metadata]

ALLOWED_SCHEMAS = {"forecast", "bb_risk"}


def include_name(name, type_, parent_names):
    """Не дать autogenerate даже обойти чужие схемы — платформенная гарантия."""
    if type_ == "schema":
        return name in ALLOWED_SCHEMAS
    return True


def include_object(object, name, type_, reflected, compare_to):
    """Подстраховка на уровне объектов: таблица/колонка/constraint только из своих схем."""
    if type_ == "table":
        return object.schema in ALLOWED_SCHEMAS
    table = getattr(object, "table", None)
    if table is not None:
        return table.schema in ALLOWED_SCHEMAS
    return True


def _database_url() -> str:
    return get_settings().sqlalchemy_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        version_table_schema="forecast",
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    connectable = create_engine(url)

    with connectable.connect() as connection:
        # forecast должна существовать до старта миграций: именно в ней Alembic создаёт
        # alembic_version (version_table_schema), а это происходит раньше, чем выполнится
        # хотя бы одна ревизия. bb_risk создаём тут же, чтобы baseline-миграция на пустой
        # базе не зависела от отдельного бутстрап-шага.
        if url.startswith("postgresql"):
            for schema in sorted(ALLOWED_SCHEMAS):
                connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            include_object=include_object,
            version_table_schema="forecast",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
