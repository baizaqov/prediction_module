"""Клиент климатических данных РГП «Казгидромет» (ТЗ 4.10.6.1).

MVP-заглушка: реальный источник (через ШЭП/HTTPS) ещё не подключён — данные генерируются
синтетически с реалистичной сезонной структурой. Интерфейс класса стабилен, поэтому при
появлении боевого канала достаточно заменить реализацию ``fetch`` на SOAP/HTTPS-вызов,
не трогая вызывающий код.

Построение боевого клиента к Казгидромету через ШЭП — задача навыка shep-integration
(по образцу sync-канала elicense-client).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..ml.synthetic import DEFAULT_REGIONS, SyntheticConfig, generate_dataset

SOURCE_STUB = "KAZHYDROMET_STUB"


@dataclass
class ClimateRecord:
    region_code: str
    period: date
    temp_c: float
    humidity: float
    precip_mm: float
    source: str = SOURCE_STUB


class KazhydrometClient:
    """Провайдер климатических и синоптических наблюдений."""

    def __init__(self, seed: int = 42):
        self._seed = seed

    def fetch(
        self,
        regions: list[str] | None = None,
        start_year: int = 2019,
        months: int = 72,
    ) -> list[ClimateRecord]:
        """Вернуть помесячные наблюдения по регионам.

        В боевой версии здесь будет запрос к Казгидромету за период; сигнатура и формат
        записи остаются прежними.
        """
        regions = regions or DEFAULT_REGIONS
        df = generate_dataset(
            SyntheticConfig(regions=regions, start_year=start_year, months=months, seed=self._seed)
        )
        return [
            ClimateRecord(
                region_code=row.region_code,
                period=row.period.date() if isinstance(row.period, pd.Timestamp) else row.period,
                temp_c=float(row.temp_c),
                humidity=float(row.humidity),
                precip_mm=float(row.precip_mm),
            )
            for row in df.itertuples(index=False)
        ]
