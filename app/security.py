"""Валидация внутреннего токена шлюза (X-Internal-Authorization).

Повторяет контракт gisbb-common-web: заголовок содержит «Bearer <jwt>», подпись HS256
на общем секрете gisbb.internal-token.secret. Из токена читаются роли (claim ``roles``,
имена в верхнем регистре без префикса ROLE_) и ``userInfo`` для авторизации и аудита.
Авторизация — только по ролям (слой прав в платформе упразднён).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from .config import Settings, get_settings

_BEARER_PREFIX = "Bearer "


@dataclass
class UserInfo:
    user_id: int | None = None
    org_id: int | None = None
    org_name: str | None = None
    org_bin: str | None = None
    full_name: str | None = None


@dataclass
class Principal:
    roles: set[str] = field(default_factory=set)
    user_info: UserInfo = field(default_factory=UserInfo)

    def has_role(self, role: str) -> bool:
        return role.upper() in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return any(self.has_role(r) for r in roles)


def _decode(token: str, settings: Settings) -> dict:
    return jwt.decode(
        token,
        settings.internal_token_secret,
        algorithms=["HS256"],
        # iss/aud платформа на стороне сервисов не проверяет; подпись и exp обязательны.
        options={"verify_aud": False, "verify_iss": False},
    )


def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """FastAPI-зависимость: разбирает внутренний токен в Principal.

    Если проверка токена отключена (локальная разработка), возвращает пустого
    принципала — доступ открыт. При включённой проверке отсутствие/невалидность токена
    даёт 401.
    """
    if not settings.internal_token_enabled:
        return Principal()

    if not x_internal_authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует заголовок X-Internal-Authorization",
        )

    token = x_internal_authorization
    if token.startswith(_BEARER_PREFIX):
        token = token[len(_BEARER_PREFIX):]

    try:
        claims = _decode(token, settings)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Недействительный внутренний токен: {exc}",
        ) from exc

    roles = {str(r).upper() for r in claims.get("roles", []) or []}
    ui = claims.get("userInfo") or {}
    return Principal(
        roles=roles,
        user_info=UserInfo(
            user_id=ui.get("userId"),
            org_id=ui.get("orgId"),
            org_name=ui.get("orgName"),
            org_bin=ui.get("orgBin"),
            full_name=ui.get("fullName"),
        ),
    )


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_roles(*allowed: str):
    """Фабрика зависимостей: требует у принципала хотя бы одну из ролей.

    Пустой список ролей у сервиса допустим только при отключённой проверке токена —
    тогда get_principal уже вернул открытый доступ, и эта проверка не срабатывает.
    """

    def _guard(principal: PrincipalDep, settings: Annotated[Settings, Depends(get_settings)]) -> Principal:
        if not settings.internal_token_enabled:
            return principal
        if not principal.has_any_role(*allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для доступа к функции прогнозирования",
            )
        return principal

    return _guard
