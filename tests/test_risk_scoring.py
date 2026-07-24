"""Проверка порта расчётного ядра (app/risk/scoring.py) на 16 тест-векторах.

Векторы и допуск — из поставочного пакета (reference/test_vectors.json →
tests/risk_test_vectors.json). Совпадение подтверждает, что порт идентичен эталону.
"""
import json
import pathlib

from app.risk.scoring import calculate_risk

BASE = pathlib.Path(__file__).parent
DATA = BASE.parent / "app" / "risk" / "data"

_vectors_doc = json.load(open(BASE / "risk_test_vectors.json", encoding="utf-8"))
TOL = _vectors_doc.get("tolerance", 1e-6)
VECTORS = _vectors_doc["vectors"]


def _load_catalog(code):
    return json.load(open(DATA / f"{code}.json", encoding="utf-8"))


def _near(a, b):
    if a is None or b is None:
        return a == b
    return abs(a - b) <= TOL


def test_all_vectors_pass():
    failures = []
    for v in VECTORS:
        factors = _load_catalog(v["infection"])
        scores = {int(k): val for k, val in v["scores"].items()}
        r = calculate_risk(factors, scores, panel=v["panel"])
        e = v["expected"]
        checks = [
            ("panel_size", r["panel_size"], e["panel_size"]),
            ("assessed", r["assessed"], e["assessed"]),
            ("weighted_sum", r["weighted_sum"], e["weighted_sum"]),
            ("integral_index", r["integral_index"], e["integral_index"]),
            ("completeness", r["completeness"], e["completeness"]),
            ("adjustment_factor", r["adjustment_factor"], e["adjustment_factor"]),
            ("adjusted_index", r["adjusted_index"], e["adjusted_index"]),
            ("level", r["level"], e["level"]),
            ("has_red_trigger", r["has_red_trigger"], e["has_red_trigger"]),
            ("red_trigger_count", len(r["red_triggers"]), e["red_trigger_count"]),
        ]
        for field, got, exp in checks:
            ok = _near(got, exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) else got == exp
            if not ok:
                failures.append(f"{v['name']}.{field}: got {got!r}, exp {exp!r}")
    assert not failures, "Несовпадения с эталоном:\n" + "\n".join(failures)


def test_sixteen_vectors_present():
    assert len(VECTORS) == 16
