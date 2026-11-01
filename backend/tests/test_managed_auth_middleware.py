from fastapi import FastAPI
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.core.auth_middleware import ManagedAuthMiddleware
from app.services.production_foundation import ProductionFoundationError
from app.core.tenant_context import TenantIsolationError


class LegacyWrite(BaseModel):
    user_id: str = "default-user"
    value: str


class StrictWrite(BaseModel):
    model_config = {"extra": "forbid"}

    value: str


def _client(
    monkeypatch,
    *,
    role: str = "viewer",
    user_id: str = "tenant-a",
    rate_limit_enabled: bool = False,
    invitation_required: bool = False,
    beta_qualified: bool = True,
) -> TestClient:
    class EnabledSettings:
        managed_auth_required = True
        managed_auth_invitation_required = invitation_required
        api_rate_limit_enabled = rate_limit_enabled
        api_rate_limit_requests = 2
        api_rate_limit_window_seconds = 60
        api_login_rate_limit_requests = 1
        api_auth_failure_rate_limit_requests = 2
        redis_url = "redis://unused.test/0"
        dependency_check_timeout_seconds = 1

    actor = AuthenticatedUser(
        user_id=user_id,
        role=role,
        permissions=ROLE_PERMISSIONS[role],
        auth_required=True,
        token_configured=True,
    )

    monkeypatch.setattr("app.core.auth_middleware.get_settings", lambda: EnabledSettings())
    monkeypatch.setattr("app.core.auth_middleware.ManagedAuthService.authenticate", lambda _self, _token: actor)
    monkeypatch.setattr(
        "app.core.auth_middleware.BetaAnalyticsService.profile",
        lambda _self, *, actor: {
            "qualified": beta_qualified,
            "terms": {
                "beta_terms_version": "private-beta-current",
                "privacy_policy_version": "privacy-current",
                "consent_action": "ACCEPT_PRIVATE_BETA_TERMS",
            },
        },
    )

    app = FastAPI()
    app.add_middleware(ManagedAuthMiddleware)

    @app.get("/legacy")
    def legacy(request: Request, user_id: str = "default-user"):
        return {
            "query_user_id": user_id,
            "header_user_id": request.headers.get("x-ai-trading-user"),
            "role": request.headers.get("x-ai-trading-role"),
        }

    @app.post("/production/auth/login")
    def login():
        return {"status": "login-reached"}

    @app.post("/legacy-write")
    def legacy_write(payload: LegacyWrite):
        return payload.model_dump()

    @app.post("/strict-write")
    def strict_write(payload: StrictWrite):
        return payload.model_dump()

    @app.post("/cross-tenant-flush")
    def cross_tenant_flush():
        raise TenantIsolationError("cross-user database write denied")

    return TestClient(app)


def test_managed_auth_injects_session_subject_for_legacy_query_default(monkeypatch):
    response = _client(monkeypatch).get("/legacy?limit=10", headers={"Authorization": "Bearer valid-session"})

    assert response.status_code == 200
    assert response.json() == {
        "query_user_id": "tenant-a",
        "header_user_id": "tenant-a",
        "role": "viewer",
    }
    assert response.headers["cache-control"] == "no-store"


def test_managed_auth_denies_viewer_cross_user_query(monkeypatch):
    response = _client(monkeypatch).get(
        "/legacy?user_id=tenant-b",
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "cross-user access denied"}


def test_managed_auth_allows_admin_explicit_cross_user_query(monkeypatch):
    response = _client(monkeypatch, role="admin").get(
        "/legacy?user_id=tenant-b",
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 200
    assert response.json()["query_user_id"] == "tenant-b"


def test_managed_auth_replaces_spoofed_identity_headers(monkeypatch):
    response = _client(monkeypatch).get(
        "/legacy",
        headers={
            "Authorization": "Bearer valid-session",
            "X-AI-Trading-User": "tenant-b",
            "X-AI-Trading-Role": "owner",
        },
    )

    assert response.status_code == 200
    assert response.json()["header_user_id"] == "tenant-a"
    assert response.json()["role"] == "viewer"


def test_managed_api_rate_limit_returns_429_with_retry_after(monkeypatch):
    counts = iter([(1, 60), (2, 59), (3, 58)])
    monkeypatch.setattr(
        ManagedAuthMiddleware,
        "_consume_rate_limit",
        staticmethod(lambda **_kwargs: next(counts)),
    )
    client = _client(monkeypatch, rate_limit_enabled=True)

    assert client.get("/legacy", headers={"Authorization": "Bearer valid-session"}).status_code == 200
    assert client.get("/legacy", headers={"Authorization": "Bearer valid-session"}).status_code == 200
    response = client.get("/legacy", headers={"Authorization": "Bearer valid-session"})

    assert response.status_code == 429
    assert response.json() == {"detail": "API rate limit exceeded"}
    assert response.headers["retry-after"] == "58"
    assert response.headers["cache-control"] == "no-store"


def test_managed_login_has_stricter_client_rate_limit(monkeypatch):
    counts = iter([(1, 60), (2, 57)])
    monkeypatch.setattr(
        ManagedAuthMiddleware,
        "_consume_rate_limit",
        staticmethod(lambda **_kwargs: next(counts)),
    )
    client = _client(monkeypatch, rate_limit_enabled=True)

    assert client.post("/production/auth/login").status_code == 200
    response = client.post("/production/auth/login")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "57"


def test_rate_limit_store_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(
        ManagedAuthMiddleware,
        "_consume_rate_limit",
        staticmethod(lambda **_kwargs: (_ for _ in ()).throw(OSError("redis unavailable"))),
    )
    response = _client(monkeypatch, rate_limit_enabled=True).get(
        "/legacy",
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "API rate-limit store is unavailable; request failed closed"}
    assert response.headers["cache-control"] == "no-store"


def test_invalid_session_attempts_are_client_rate_limited(monkeypatch):
    counts = iter([(1, 60), (2, 59), (3, 58)])
    monkeypatch.setattr(
        ManagedAuthMiddleware,
        "_consume_rate_limit",
        staticmethod(lambda **_kwargs: next(counts)),
    )
    client = _client(monkeypatch, rate_limit_enabled=True)
    monkeypatch.setattr(
        "app.core.auth_middleware.ManagedAuthService.authenticate",
        lambda _self, _token: (_ for _ in ()).throw(ProductionFoundationError("invalid managed session")),
    )

    assert client.get("/legacy", headers={"Authorization": "Bearer invalid-1"}).status_code == 401
    assert client.get("/legacy", headers={"Authorization": "Bearer invalid-2"}).status_code == 401
    response = client.get("/legacy", headers={"Authorization": "Bearer invalid-3"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "58"


def test_managed_auth_injects_subject_into_json_body_before_schema_default(monkeypatch):
    response = _client(monkeypatch).post(
        "/legacy-write",
        json={"value": "safe-write"},
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": "tenant-a", "value": "safe-write"}


def test_managed_auth_denies_viewer_cross_user_json_body(monkeypatch):
    response = _client(monkeypatch).post(
        "/legacy-write",
        json={"user_id": "tenant-b", "value": "forbidden-write"},
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "cross-user access denied"}


def test_managed_auth_allows_admin_explicit_cross_user_json_body(monkeypatch):
    response = _client(monkeypatch, role="admin").post(
        "/legacy-write",
        json={"user_id": "tenant-b", "value": "admin-write"},
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": "tenant-b", "value": "admin-write"}


def test_managed_auth_does_not_inject_user_into_schema_without_user_field(monkeypatch):
    response = _client(monkeypatch).post(
        "/strict-write",
        json={"value": "schema-safe"},
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 200
    assert response.json() == {"value": "schema-safe"}


def test_managed_auth_converts_database_tenant_violation_to_403(monkeypatch):
    response = _client(monkeypatch).post(
        "/cross-tenant-flush",
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "cross-user database access denied"}
    assert response.headers["cache-control"] == "no-store"


def test_private_beta_withdrawal_blocks_product_access_immediately(monkeypatch):
    response = _client(
        monkeypatch,
        invitation_required=True,
        beta_qualified=False,
    ).get("/legacy", headers={"Authorization": "Bearer valid-session"})

    assert response.status_code == 403
    assert response.json()["code"] == "private_beta_consent_required"
    assert response.json()["recovery_path"] == "/production/beta-profile"
    assert response.headers["cache-control"] == "no-store"


def test_private_beta_reconsent_restores_product_access(monkeypatch):
    client = _client(monkeypatch, invitation_required=True, beta_qualified=True)

    response = client.get("/legacy", headers={"Authorization": "Bearer valid-session"})

    assert response.status_code == 200
    assert response.json()["query_user_id"] == "tenant-a"


def test_private_beta_recovery_routes_remain_available_after_withdrawal(monkeypatch):
    client = _client(monkeypatch, invitation_required=True, beta_qualified=False)
    headers = {"Authorization": "Bearer valid-session"}

    for path in (
        "/production/auth/logout",
        "/production/beta-profile",
        "/production/invitations/me",
        "/production/invitations/accept",
        "/production/privacy",
        "/production/privacy/export",
        "/production/support/tickets",
        "/production/support/tickets/ticket-1/replies",
        "/daily-use/local-start",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code != 403 or response.json().get("code") != "private_beta_consent_required"


def test_private_beta_gate_does_not_apply_to_staff_roles(monkeypatch):
    response = _client(
        monkeypatch,
        role="operator",
        invitation_required=True,
        beta_qualified=False,
    ).get("/legacy", headers={"Authorization": "Bearer valid-session"})

    assert response.status_code == 200
