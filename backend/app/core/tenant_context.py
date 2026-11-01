from __future__ import annotations

from contextvars import ContextVar
from contextvars import Token


class TenantIsolationError(RuntimeError):
    pass


_current_tenant_id: ContextVar[str | None] = ContextVar("ai_trading_os_tenant_id", default=None)


def current_tenant_id() -> str | None:
    return _current_tenant_id.get()


def bind_tenant(user_id: str) -> Token:
    normalized = user_id.strip()
    if not normalized:
        raise TenantIsolationError("tenant user id is required")
    return _current_tenant_id.set(normalized)


def reset_tenant(token: Token) -> None:
    _current_tenant_id.reset(token)
