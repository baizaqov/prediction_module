"""Загрузка каталогов факторов риска в БД при старте сервиса.

Читает app/risk/data/infections.json (реестр ООИ) и app/risk/data/<code>.json
(каталоги факторов), идемпотентно заполняет bb_risk.infection и bb_risk.factor.
Соответствует стилю сервиса «создать-затем-наполнить» (create_all → seed).
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from ..db import SessionLocal
from .models import Factor, Infection

log = logging.getLogger("gisbb-forecast.risk.catalog")

_DATA_DIR = pathlib.Path(__file__).parent / "data"


def _load_json(name: str) -> Any:
    with open(_DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def _read_infections_registry() -> list[dict]:
    registry = _load_json("infections.json")
    return registry.get("infections", []) if isinstance(registry, dict) else registry


def seed() -> None:
    """Заполнить справочник инфекций и каталоги факторов. Идемпотентно.

    Каталог инфекции перезаписывается только если число факторов в БД не совпадает
    с файлом — чтобы не «дёргать» таблицу на каждом старте при неизменных данных.
    """
    infections = _read_infections_registry()
    if not infections:
        log.warning("Реестр инфекций пуст (infections.json) — каталоги не загружены")
        return

    session = SessionLocal()
    try:
        for meta in infections:
            code = meta.get("code")
            if not code:
                continue

            session.merge(Infection(
                code=code,
                name_ru=meta.get("name_ru") or code,
                pathogen=meta.get("pathogen"),
                pathogen_group=meta.get("pathogen_group"),
                factors_total=meta.get("factors_total") or 0,
                factors_basic=meta.get("factors_basic") or 0,
                factors_extended=meta.get("factors_extended") or 0,
                red_triggers=meta.get("red_triggers") or 0,
            ))

            catalog_file = _DATA_DIR / f"{code}.json"
            if not catalog_file.exists():
                log.warning("Каталог факторов не найден: %s.json", code)
                continue
            factors = _load_json(f"{code}.json")

            existing = session.query(Factor).filter(Factor.infection_code == code).count()
            if existing == len(factors):
                continue  # уже загружено, данные не изменились

            session.query(Factor).filter(Factor.infection_code == code).delete()
            session.flush()
            for f in factors:
                session.add(Factor(
                    infection_code=code,
                    no=f["no"],
                    category=f.get("category") or "",
                    name=f.get("name") or "",
                    type=f.get("type") or "numeric",
                    weight=int(f.get("weight") or 1),
                    tier=f.get("tier") or "basic",
                    red_trigger=bool(f.get("red_trigger")),
                    direction=f.get("direction"),
                    factor_class=f.get("factor_class"),
                    scale=f.get("scale") or {},
                    measures=f.get("measures"),
                    normative_doc=f.get("normative_doc"),
                    responsible=f.get("responsible"),
                    source_data=f.get("source_data"),
                ))
            log.info("Загружен каталог факторов %s: %d факторов", code, len(factors))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
