# gisbb-forecast

Микросервис **«Прогнозирование и оценка биологических рисков»** — реализация модуля ТЗ ГИС ББ п. 4.10.6.
Единственный не-JVM сервис платформы: **Python 3.12 / FastAPI / scikit-learn**, за общим шлюзом на префиксе `/api/forecast/**`.

## Что реализовано (MVP)

- **Функция получения климатических данных (4.10.6.1)** — клиент РГП «Казгидромет» (пока заглушка-синтетика), загрузка наблюдений в схему `forecast`.
- **Функция прогнозирования (4.10.6.2)** — все 8 методов ТЗ в реестре (`app/ml/registry.py`): линейная/логистическая регрессия, деревья решений, случайный лес, МНК, KNN, SVM, градиентный бустинг. Baseline (градиентный бустинг) обучается и оценивается end-to-end; порог точности ≥80% контролируется.
- **Функция отчётности и визуализации (4.10.6.3)** — результат отдаётся в виде рядов (история + прогноз), таблиц метрик и гео-слоя риска по регионам (для карты во фронте).
- Сохранение прогонов (плановые/внеплановые), каталог методов, инструкции (`/v1/help`).

## Запуск локально

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows; на *nix — .venv/bin/pip
cp .env.example .env                                # при необходимости включите SQLite
.venv/Scripts/uvicorn app.main:app --port 8100
```

Swagger: локально `http://localhost:8100/docs`; через шлюз `/api/forecast/docs`.

Тесты:
```bash
.venv/Scripts/python -m pytest -q
```

## Ключевые эндпоинты (под шлюзом — с префиксом `/api/forecast`)

| Метод | Путь | Назначение |
|------|------|-----------|
| GET | `/v1/methods?task=regression` | Каталог методов прогнозирования |
| GET | `/v1/help` | Инструкции и пояснения |
| POST | `/v1/climate/refresh` | Загрузка климатических наблюдений |
| GET | `/v1/climate` | Просмотр климата |
| POST | `/v1/models/train` | Обучить модель |
| POST | `/v1/forecast/run` | Запустить прогноз (ряды + гео-слой) |
| GET | `/v1/forecast/runs` | Сохранённые прогоны (пагинация) |
| GET | `/v1/forecast/runs/{id}` | Результат прогона |
| GET | `/actuator/health` | Health (Eureka) — напрямую, без шлюза |

## Интеграция с платформой

- **Шлюз**: маршрут `Path=/api/forecast/**` → `lb://gisbb-forecast`, `StripPrefix=2` (см. `gisbb-gateway/application-*.yaml`). FastAPI знает о префиксе через `root_path`.
- **Аутентификация**: валидация `X-Internal-Authorization` (HS256, секрет `gisbb.internal-token.secret`), авторизация по ролям из claim `roles` (`app/security.py`, `app/roles.py`).
- **Eureka**: регистрация через `py-eureka-client` (`EUREKA_ENABLED=true`), app-name = `gisbb-forecast`.
- **БД**: схема `forecast` в общем `gisbb_db`. Для MVP таблицы создаёт SQLAlchemy (`create_all`); при переходе на централизованный `gisbb-db-migration` DDL нужно перенести в Liquibase.

## Что дальше (не входит в MVP)

- Боевой клиент Казгидромета через ШЭП (навык `shep-integration`).
- Обучающая панель из реальных рядов `ooi-registry` (emergency_notifications) джойном с климатом.
- Подбор/сравнение всех методов и сохранение лучшей модели; MLflow-версионирование.
- Angular-модуль `module-forecast` (графики chart.js + карта Leaflet).
