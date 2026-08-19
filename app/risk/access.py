"""Доменная авторизация факторов риска.

Матрица «фактор ↔ орган» читается только из БД. Ролевое соответствие Keycloak
органам находится в app.roles, а номера факторов здесь намеренно не перечисляются.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..roles import FULL_FACTOR_ACCESS_ROLES, ORGANIZATION_BY_ROLE
from ..security import Principal
from .models import FactorOrganization


def has_full_factor_access(principal: Principal | None) -> bool:
    """Полный доступ Эксперта и обратная совместимость прежних ролей.

    Пустой принципал появляется только при отключённой проверке токена, то есть в
    локальном режиме разработки и SQLite-тестах, где исторически доступ был открыт.
    """
    return principal is None or not principal.roles or principal.has_any_role(*FULL_FACTOR_ACCESS_ROLES)


def organization_codes(principal: Principal) -> set[str]:
    """Вернуть органы, вытекающие из ролей текущего пользователя."""
    return {ORGANIZATION_BY_ROLE[role] for role in principal.roles if role in ORGANIZATION_BY_ROLE}


def accessible_factor_numbers(
    session: Session, infection_code: str, principal: Principal | None,
) -> set[int] | None:
    """Номера доступных факторов; ``None`` означает доступ ко всему каталогу."""
    if has_full_factor_access(principal):
        return None

    assert principal is not None
    org_codes = organization_codes(principal)
    if not org_codes:
        return set()

    stmt = select(FactorOrganization.factor_no).where(
        FactorOrganization.infection_code == infection_code,
        FactorOrganization.organization_code.in_(org_codes),
    )
    return set(session.execute(stmt).scalars())


def split_scores_by_access(
    session: Session,
    infection_code: str,
    scores: dict[int, int],
    catalog_factor_numbers: set[int],
    principal: Principal | None,
) -> tuple[dict[int, int], list[int]]:
    """Разделить баллы на допустимые для роли и отклонённые (T-16/T-27).

    По решению БА чужой фактор в запросе не отклоняет оценку целиком — исключается
    только он, остальное считается и сохраняется. Отклонёнными считаются лишь номера,
    реально существующие в каталоге инфекции и закреплённые за другим органом: номер,
    которого нет в каталоге вовсе, под доступ не подпадает и просто игнорируется
    движком расчёта, как и раньше — не маскируется под «чужой».
    """
    requested = {int(no): value for no, value in scores.items() if value is not None}

    allowed = accessible_factor_numbers(session, infection_code, principal)
    if allowed is None:
        return requested, []

    denied = sorted(no for no in requested if no in catalog_factor_numbers and no not in allowed)
    accepted = {no: value for no, value in requested.items() if no not in denied}
    return accepted, denied
