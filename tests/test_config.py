"""Тесты разрешения конфигурации БД/Eureka (совместимость с общим ConfigMap платформы)."""
from app.config import Settings, _jdbc_to_sqlalchemy


def test_jdbc_to_sqlalchemy_injects_credentials():
    url = _jdbc_to_sqlalchemy(
        "jdbc:postgresql://192.168.34.50:5432/gisbb_db", "gisbb_service", "qaZ-GiS-22-BB"
    )
    assert url == "postgresql+psycopg://gisbb_service:qaZ-GiS-22-BB@192.168.34.50:5432/gisbb_db"


def test_jdbc_special_chars_are_url_encoded():
    url = _jdbc_to_sqlalchemy("jdbc:postgresql://h:5432/db", "user", "p@ss:word")
    assert "p%40ss%3Aword" in url


def test_explicit_database_url_wins_over_spring(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./x.db")
    monkeypatch.setenv("SPRING_DATASOURCE_URL", "jdbc:postgresql://h:5432/db")
    assert Settings().sqlalchemy_url == "sqlite:///./x.db"


def test_spring_datasource_used_when_no_explicit_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SPRING_DATASOURCE_URL", "jdbc:postgresql://db-host:5432/gisbb_db")
    monkeypatch.setenv("SPRING_DATASOURCE_USERNAME", "gisbb_service")
    monkeypatch.setenv("SPRING_DATASOURCE_PASSWORD", "secret")
    assert Settings().sqlalchemy_url == "postgresql+psycopg://gisbb_service:secret@db-host:5432/gisbb_db"


def test_local_default_when_nothing_set(monkeypatch):
    for var in ("DATABASE_URL", "SPRING_DATASOURCE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert Settings().sqlalchemy_url.startswith("postgresql+psycopg://gisbb_service:")
    assert "@localhost:5432/gisbb_db" in Settings().sqlalchemy_url


def test_eureka_zone_falls_back_to_spring_var(monkeypatch):
    monkeypatch.delenv("EUREKA_DEFAULT_ZONE", raising=False)
    monkeypatch.setenv("EUREKA_CLIENT_SERVICEURL_DEFAULTZONE", "http://gisbb-eureka-service:8080/eureka/")
    assert Settings().resolved_eureka_zone == "http://gisbb-eureka-service:8080/eureka/"
