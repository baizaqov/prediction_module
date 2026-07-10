"""Тестовое окружение: SQLite в памяти файла, проверка токена и Eureka выключены.

Переменные окружения выставляются до импорта приложения, т.к. настройки и движок БД
инициализируются на уровне модуля.
"""
import os
import pathlib

_DB = pathlib.Path(__file__).parent / "forecast_test.db"
if _DB.exists():
    _DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["GISBB_INTERNAL_TOKEN_ENABLED"] = "false"
os.environ["EUREKA_ENABLED"] = "false"
