# -*- coding: utf-8 -*-
"""ГИС ББ РК — модуль «Прогнозирование и оценка биологических рисков».
Референс-реализация расчёта интегрального показателя риска. Версия 5.0

Порт поставочного reference/scoring.py (без внешних зависимостей, только stdlib);
совпадает один-в-один с reference/scoring.js. Проверяется тест-векторами
tests/risk_test_vectors.json (16 векторов, tolerance 1e-6).

МОДЕЛЬ
------
Каждый фактор риска имеет:
    weight      - весовой коэффициент 1..4
    tier        - панель: 'basic' (экспресс-оценка) | 'extended' (углублённая)
    red_trigger - признак «красного триггера» (немедленное реагирование)
    scale       - пороговые значения для баллов 0..4 (справочно, для интерфейса)

Оценщик проставляет фактору балл 0..4. Незаполненные факторы не участвуют
в расчёте - ни в числителе, ни в знаменателе.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

__version__ = '5.0'

#: Границы категорий риска. Нижняя граница включается, верхняя исключается.
RISK_THRESHOLDS = {'low': 3.0, 'medium': 5.0, 'high': 7.0}

#: Балл, начиная с которого красный триггер считается сработавшим.
RED_TRIGGER_MIN_SCORE = 3

SCORE_MIN, SCORE_MAX = 0, 4
WEIGHT_MIN, WEIGHT_MAX = 1, 4

_LEVEL_RU = {
    'not_assessed': 'не оценено',
    'low': 'низкий',
    'medium': 'средний',
    'high': 'высокий',
    'very_high': 'очень высокий',
    'red_trigger': 'красный триггер – режим экстренного реагирования',
}


def select_panel(factors: Sequence[Mapping[str, Any]], panel: str) -> List[Mapping[str, Any]]:
    """Отбор факторов используемой панели: 'basic' | 'extended' | 'full'."""
    if panel == 'full':
        return list(factors)
    if panel == 'basic':
        return [f for f in factors if (f.get('tier') or 'basic') == 'basic']
    if panel == 'extended':
        return [f for f in factors if f.get('tier') == 'extended']
    raise ValueError('Неизвестная панель: %s' % panel)


def compute_level(index: Optional[float], has_red_trigger: bool) -> str:
    """Категория риска. Красный триггер имеет приоритет над значением индекса."""
    if has_red_trigger:
        return 'red_trigger'
    if index is None:
        return 'not_assessed'
    if index < RISK_THRESHOLDS['low']:
        return 'low'
    if index < RISK_THRESHOLDS['medium']:
        return 'medium'
    if index < RISK_THRESHOLDS['high']:
        return 'high'
    return 'very_high'


def level_name_ru(level: str) -> str:
    """Человекочитаемое название уровня риска."""
    return _LEVEL_RU.get(level, level)


def calculate_risk(factors: Sequence[Mapping[str, Any]],
                   scores: Mapping[Any, Any],
                   panel: str = 'basic',
                   strict: bool = False) -> Dict[str, Any]:
    """Основной расчёт.

    Формулы:
        интегральный_индекс = SUM(балл * вес) / N_оценённых
        полнота             = N_оценённых / N_панели
        индекс_с_поправкой  = интегральный_индекс * (0.5 + 0.5 * полнота)

    :param factors: каталог факторов инфекции (data/<code>.json)
    :param scores:  {номер_фактора: балл 0..4}; отсутствующий ключ = не оценён
    :param panel:   'basic' | 'extended' | 'full'
    :param strict:  бросать ValueError при некорректных данных вместо пропуска
    """
    panel_factors = select_panel(factors, panel)

    weighted_sum = 0.0
    assessed = 0
    red_triggers: List[Dict[str, Any]] = []
    by_category: Dict[str, Dict[str, Any]] = {}
    by_factor_class: Dict[str, Dict[str, Any]] = {}

    for f in panel_factors:
        no = f.get('no')
        raw = scores.get(no, scores.get(str(no)))
        if raw is None or raw == '':
            continue
        try:
            score = float(raw)
        except (TypeError, ValueError):
            if strict:
                raise ValueError('Недопустимый балл %r у фактора №%s' % (raw, no))
            continue
        if not (SCORE_MIN <= score <= SCORE_MAX):
            if strict:
                raise ValueError('Балл вне диапазона 0..4 (%r) у фактора №%s' % (raw, no))
            continue
        try:
            weight = float(f.get('weight'))
        except (TypeError, ValueError):
            if strict:
                raise ValueError('Недопустимый вес %r у фактора №%s' % (f.get('weight'), no))
            continue
        if not (WEIGHT_MIN <= weight <= WEIGHT_MAX):
            if strict:
                raise ValueError('Вес вне диапазона 1..4 (%r) у фактора №%s' % (f.get('weight'), no))
            continue

        contribution = score * weight
        weighted_sum += contribution
        assessed += 1

        if f.get('red_trigger') and score >= RED_TRIGGER_MIN_SCORE:
            red_triggers.append({'no': no, 'name': f.get('name'), 'score': score})

        cat = f.get('category') or 'без категории'
        d = by_category.setdefault(cat, {'sum': 0.0, 'count': 0, 'max_score': 0.0})
        d['sum'] += contribution
        d['count'] += 1
        d['max_score'] = max(d['max_score'], score)

        cls = f.get('factor_class') or 'unclassified'
        c = by_factor_class.setdefault(cls, {'sum': 0.0, 'count': 0})
        c['sum'] += contribution
        c['count'] += 1

    integral_index = (weighted_sum / assessed) if assessed > 0 else None
    completeness = (assessed / len(panel_factors)) if panel_factors else 0.0
    adjustment_factor = 0.5 + 0.5 * completeness
    adjusted_index = None if integral_index is None else integral_index * adjustment_factor
    level = compute_level(integral_index, bool(red_triggers))

    for d in by_category.values():
        d['mean'] = (d['sum'] / d['count']) if d['count'] else None
    for c in by_factor_class.values():
        c['mean'] = (c['sum'] / c['count']) if c['count'] else None

    return {
        'panel': panel,
        'panel_size': len(panel_factors),
        'assessed': assessed,
        'not_assessed': len(panel_factors) - assessed,
        'weighted_sum': weighted_sum,
        'integral_index': integral_index,
        'completeness': completeness,
        'adjustment_factor': adjustment_factor,
        'adjusted_index': adjusted_index,
        'level': level,
        'level_ru': level_name_ru(level),
        'red_triggers': red_triggers,
        'has_red_trigger': bool(red_triggers),
        'by_category': by_category,
        'by_factor_class': by_factor_class,
    }


def validate_catalog(factors: Iterable[Mapping[str, Any]]) -> List[str]:
    """Проверка каталога на целостность. Возвращает список проблем (пустой = ок)."""
    problems: List[str] = []
    seen = set()
    for i, f in enumerate(factors):
        no = f.get('no')
        at = 'фактор[%d] №%s' % (i, no)
        if no is None:
            problems.append(at + ': отсутствует no')
        elif no in seen:
            problems.append(at + ': дубликат номера')
        else:
            seen.add(no)
        if not f.get('name'):
            problems.append(at + ': отсутствует name')
        if not f.get('category'):
            problems.append(at + ': отсутствует category')
        try:
            w = float(f.get('weight'))
            if not (WEIGHT_MIN <= w <= WEIGHT_MAX):
                raise ValueError
        except (TypeError, ValueError):
            problems.append(at + ': вес вне диапазона 1..4 (%r)' % f.get('weight'))
        tier = f.get('tier') or 'basic'
        if tier not in ('basic', 'extended'):
            problems.append(at + ': недопустимый tier (%r)' % f.get('tier'))
        if f.get('type') not in ('numeric', 'binary'):
            problems.append(at + ': недопустимый type (%r)' % f.get('type'))
        if f.get('type') == 'binary' and f.get('scale'):
            keys = [k for k, v in f['scale'].items() if v and v != '–']
            extra = [k for k in keys if k not in ('0', '4')]
            if extra:
                problems.append(at + ': бинарный фактор имеет баллы кроме 0 и 4 (%s)' % ','.join(extra))
    return problems
