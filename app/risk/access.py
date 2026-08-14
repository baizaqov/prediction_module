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


class FactorAccessDenied(ValueError):
    """Запрос содержит баллы по факторам вне зоны ответственности."""


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


def ensure_scores_accessible(
    session: Session, infection_code: str, scores: dict[int, int], principal: Principal | None,
) -> None:
    """Отклонить весь запрос до расчёта и сохранения, если есть чужой фактор."""
    requested = {int(no) for no in scores}
    if not requested:
        return

    allowed = accessible_factor_numbers(session, infection_code, principal)
    if allowed is None:
        return

    denied = sorted(requested - allowed)
    if denied:
        raise FactorAccessDenied(
            "Нет прав на ввод баллов по факторам: " + ", ".join(map(str, denied))
        )
