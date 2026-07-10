"""Генератор синтетических данных для MVP модуля прогнозирования.

Пока нет доступа к реальным эпид/эпизоот. рядам и климату РГП «Казгидромет»
(решение по данным принято на старте), обучающая выборка формируется синтетически,
но с реалистичной структурой: сезонность, тренд, зависимость заболеваемости от
климатических факторов и автокорреляция. Контракт колонок совпадает с тем, что позже
придёт из реальных источников, поэтому переход на боевые данные не потребует правок
пайплайна.

Целевая переменная ``incidence`` — число случаев особо опасной инфекции по региону за
месяц. Факторы (features) — климатические наблюдения и производные признаки.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

# 17 условных регионов Казахстана (коды-заглушки; в бою заменяются на dict.d_ates —
# см. project_ate_root_id_1: регионы это дети узла id=1).
DEFAULT_REGIONS = [f"KZ-{i:02d}" for i in range(1, 18)]

TARGET_COLUMN = "incidence"
CLIMATE_COLUMNS = ["temp_c", "humidity", "precip_mm"]


@dataclass(frozen=True)
class SyntheticConfig:
    regions: list[str]
    start_year: int
    months: int
    seed: int = 42


def _seasonal_temperature(month_index: int, region_offset: float) -> float:
    """Резко-континентальный годовой ход температуры (°C)."""
    phase = 2 * math.pi * (month_index % 12) / 12.0
    return -8.0 + region_offset + 22.0 * math.sin(phase - math.pi / 2)


def generate_dataset(config: SyntheticConfig) -> pd.DataFrame:
    """Собрать панельные данные (регион × месяц) с климатом и заболеваемостью."""
    rng = np.random.default_rng(config.seed)
    rows: list[dict] = []

    for r_idx, region in enumerate(config.regions):
        region_offset = rng.uniform(-4.0, 4.0)
        base_incidence = rng.uniform(3.0, 12.0)
        prev_incidence = base_incidence

        for m in range(config.months):
            year = config.start_year + m // 12
            month = m % 12 + 1

            temp = _seasonal_temperature(m, region_offset) + rng.normal(0, 2.0)
            # Влажность выше зимой, осадки — весной/летом.
            humidity = float(np.clip(60 - 0.6 * temp + rng.normal(0, 5), 15, 100))
            precip = float(max(0.0, 25 + 15 * math.sin(2 * math.pi * m / 12) + rng.normal(0, 8)))

            # Заболеваемость растёт в тёплый влажный сезон, с медленным трендом и
            # автокорреляцией (вспышки «тянутся» на следующий месяц).
            seasonal = 4.0 * math.sin(2 * math.pi * (m % 12) / 12 - math.pi / 3)
            climate_effect = 0.12 * max(0.0, temp) + 0.05 * humidity + 0.03 * precip
            trend = 0.01 * m
            noise = rng.normal(0, 1.2)
            incidence = (
                0.45 * prev_incidence
                + base_incidence
                + seasonal
                + climate_effect
                + trend
                + noise
            )
            incidence = max(0.0, incidence)
            prev_incidence = incidence

            rows.append(
                {
                    "region_code": region,
                    "period": pd.Timestamp(year=year, month=month, day=1),
                    "temp_c": round(temp, 2),
                    "humidity": round(humidity, 2),
                    "precip_mm": round(precip, 2),
                    TARGET_COLUMN: round(incidence, 2),
                }
            )

    df = pd.DataFrame(rows).sort_values(["region_code", "period"]).reset_index(drop=True)
    return df


def default_dataset(seed: int = 42) -> pd.DataFrame:
    """Готовый набор: все регионы, 6 лет помесячно."""
    return generate_dataset(
        SyntheticConfig(regions=DEFAULT_REGIONS, start_year=2019, months=72, seed=seed)
    )
