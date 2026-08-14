"""Роли доступа к модулю прогнозирования.

Имена — в верхнем регистре, как в claim ``roles`` внутреннего токена (без префикса
ROLE_): security.py приводит роли из токена к верхнему регистру. Набор ролей должен
совпадать с фронтендом (frontend/gisbb-app-ui .../module-forecast/forecast.roles.ts) —
там те же роли в нижнем регистре. Все перечисленные роли реальны и заведены в Keycloak
(realm — источник истины; экспорт вручную не править).
"""

# Профильная роль модуля — полный доступ (обучение моделей, запуск прогнозов, климат).
FORECAST_ANALYST = "GISBB_FORECAST_ANALYST"
# Суперадминистратор системы — полный доступ.
SUPER_ADMIN = "GISBB_SUPER_ADMIN"
# Профильные потребители прогнозов — только чтение результатов.
NCOZ_ADMIN = "GISBB_NCOZ_ADMIN"   # НЦОЗ (общественное здравоохранение)
MCHS_ADMIN = "GISBB_MCHS_ADMIN"   # МЧС (чрезвычайные ситуации)

# Роли раздела «Оценка риска», подтверждённые в realm gisbb. Внутренний JWT
# передаёт их в верхнем регистре (см. security.py).
EXPERT = "GISBB_EXPERT"

KSEC_ADMIN = "GISBB_KSEC_ADMIN"
KSEC_HEAD = "GISBB_KSEC_HEAD"
DSEC_ADMIN = "GISBB_DSEC_ADMIN"
USEC_ADMIN = "GISBB_USEC_ADMIN"
KSEC_ROLES = (KSEC_ADMIN, KSEC_HEAD, DSEC_ADMIN, USEC_ADMIN)

KVKN_ADMIN = "GISBB_KVKN_ADMIN"
KVKN_HEAD = "GISBB_KVKN_HEAD"
KVKN_INSPECTION_ADMIN = "GISBB_KVKN_INSPECTION_ADMIN"
KVKN_ROLES = (KVKN_ADMIN, KVKN_HEAD, KVKN_INSPECTION_ADMIN)

VETSERVICE_ADMIN = "GISBB_VETSERVICE_ADMIN"
MIO_ROLES = (VETSERVICE_ADMIN,)

# Роли, которым разрешены операции записи (обучение/прогноз/климат).
WRITE_ROLES = (
    FORECAST_ANALYST, SUPER_ADMIN, EXPERT,
    *KSEC_ROLES, *KVKN_ROLES, *MIO_ROLES,
)
# Роли на чтение результатов: те, кто пишет, плюс профильные потребители ББ.
READ_ROLES = (*WRITE_ROLES, NCOZ_ADMIN, MCHS_ADMIN)

# Старые роли были единственными ролями модуля до появления T-14. Сохраняем их
# прежнюю область работы с каталогом и preview; на сохранение по-прежнему влияют
# WRITE_ROLES. Для новых ведомственных ролей набор факторов определяется данными
# таблицы bb_risk.factor_organization, а не этим списком.
FULL_FACTOR_ACCESS_ROLES = (FORECAST_ANALYST, SUPER_ADMIN, NCOZ_ADMIN, MCHS_ADMIN, EXPERT)

# Связь Keycloak-ролей с кодом органа. Это не матрица факторов: сама матрица
# хранится в БД и допускает несколько органов у одного фактора.
ORGANIZATION_BY_ROLE = {
    **{role: "KSEC" for role in KSEC_ROLES},
    **{role: "KVKN" for role in KVKN_ROLES},
    **{role: "MIO" for role in MIO_ROLES},
}
