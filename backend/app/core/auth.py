from dataclasses import dataclass
from hashlib import sha256
from typing import Callable

from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException

from app.core.config import get_settings


ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": [
        "read",
        "users:read",
        "users:write",
        "secrets:read",
        "secrets:write",
        "events:read",
        "events:write",
        "backups:read",
        "backups:write",
        "readiness:read",
        "readiness:write",
    ],
    "admin": [
        "read",
        "users:read",
        "users:write",
        "secrets:read",
        "secrets:write",
        "events:read",
        "events:write",
        "backups:read",
        "backups:write",
        "readiness:read",
        "readiness:write",
    ],
    "operator": [
        "read",
        "users:read",
        "secrets:read",
        "events:read",
        "events:write",
        "backups:read",
        "backups:write",
        "readiness:read",
        "readiness:write",
    ],
    "viewer": [
        "read",
        "users:read",
        "events:read",
        "backups:read",
        "readiness:read",
    ],
}


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    role: str
    permissions: list[str]
    auth_required: bool
    token_configured: bool


def get_current_user(
    x_user_id: str | None = Header(default=None, alias="X-AI-Trading-User"),
    x_role: str | None = Header(default=None, alias="X-AI-Trading-Role"),
    x_beta_token: str | None = Header(default=None, alias="X-Beta-Access-Token"),
) -> AuthenticatedUser:
    settings = get_settings()
    token_configured = bool(settings.beta_access_token_sha256)
    if settings.beta_auth_required:
        if not token_configured:
            raise HTTPException(status_code=503, detail="beta auth is required but no token hash is configured")
        if not x_beta_token or sha256(x_beta_token.encode("utf-8")).hexdigest() != settings.beta_access_token_sha256:
            raise HTTPException(status_code=401, detail="invalid beta access token")

    role = (x_role or settings.beta_default_role or "viewer").strip().lower()
    if role not in ROLE_PERMISSIONS:
        role = "viewer"
    user_id = (x_user_id or settings.beta_default_user_id or "default-user").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user id is required")
    return AuthenticatedUser(
        user_id=user_id,
        role=role,
        permissions=ROLE_PERMISSIONS[role],
        auth_required=settings.beta_auth_required,
        token_configured=token_configured,
    )


def require_permission(permission: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    def dependency(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if permission not in current_user.permissions:
            raise HTTPException(status_code=403, detail=f"missing permission: {permission}")
        return current_user

    return dependency
