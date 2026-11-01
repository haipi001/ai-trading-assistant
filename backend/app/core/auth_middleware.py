from __future__ import annotations

import json
from hashlib import sha256
from fastapi.routing import APIRoute
from starlette.routing import Match
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from urllib.parse import parse_qsl
from urllib.parse import urlencode

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.tenant_context import bind_tenant
from app.core.tenant_context import reset_tenant
from app.core.tenant_context import TenantIsolationError
from app.db.session import get_session_factory
from app.services.production_foundation import ManagedAuthService
from app.services.production_foundation import ProductionFoundationError
from app.services.beta_analytics import BetaAnalyticsService


class ManagedAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/production/auth/login")
    LOGIN_PATH = "/production/auth/login"
    BETA_RECOVERY_PATHS = (
        "/production/auth/logout",
        "/production/beta-profile",
        "/production/invitations/me",
        "/production/invitations/accept",
        "/production/privacy",
        "/production/support/tickets",
        "/daily-use/local-start",
    )

    @classmethod
    def _is_beta_recovery_path(cls, path: str) -> bool:
        return any(path == allowed or path.startswith(f"{allowed}/") for allowed in cls.BETA_RECOVERY_PATHS)

    @classmethod
    def _private_beta_access_denial(cls, *, db, settings, actor, path: str) -> JSONResponse | None:
        if not (
            getattr(settings, "managed_auth_invitation_required", False)
            and actor.role == "viewer"
            and not cls._is_beta_recovery_path(path)
        ):
            return None
        status = BetaAnalyticsService(db, settings=settings).profile(actor=actor)
        if status["qualified"]:
            return None
        return JSONResponse(
            {
                "detail": "current private Beta consent and ICP qualification are required",
                "code": "private_beta_consent_required",
                "recovery_path": "/production/beta-profile",
                "terms": status["terms"],
            },
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )

    @staticmethod
    def _consume_rate_limit(*, settings, identity: str, scope: str, limit: int) -> tuple[int, int]:
        """Atomically consume one fixed-window request without storing raw identities."""
        window_seconds = max(1, int(settings.api_rate_limit_window_seconds))
        safe_limit = max(1, int(limit))
        identity_hash = sha256(identity.encode("utf-8")).hexdigest()
        key = f"atos:api-rate-limit:{scope}:{identity_hash}"
        script = """
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        local ttl = redis.call('TTL', KEYS[1])
        return {count, ttl}
        """
        client = Redis.from_url(
            str(settings.redis_url),
            socket_connect_timeout=settings.dependency_check_timeout_seconds,
            socket_timeout=settings.dependency_check_timeout_seconds,
        )
        count, ttl = client.eval(script, 1, key, window_seconds)
        return int(count), max(1, int(ttl))

    def _rate_limit_response(self, *, settings, identity: str, scope: str, limit: int) -> JSONResponse | None:
        if not settings.api_rate_limit_enabled:
            return None
        try:
            count, retry_after = self._consume_rate_limit(
                settings=settings,
                identity=identity,
                scope=scope,
                limit=limit,
            )
        except (RedisError, OSError, ValueError, TypeError):
            return JSONResponse(
                {"detail": "API rate-limit store is unavailable; request failed closed"},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        if count <= max(1, int(limit)):
            return None
        return JSONResponse(
            {"detail": "API rate limit exceeded"},
            status_code=429,
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )

    @staticmethod
    def _route_body_accepts_user_id(request: Request) -> bool:
        for route in request.app.router.routes:
            if not isinstance(route, APIRoute):
                continue
            match, _ = route.matches(request.scope)
            if match != Match.FULL or route.body_field is None:
                continue
            annotation = getattr(route.body_field.field_info, "annotation", None)
            model_fields = getattr(annotation, "model_fields", {})
            return "user_id" in model_fields
        return False

    async def _bind_json_user(self, request: Request, actor) -> JSONResponse | None:
        """Bind top-level JSON user_id to the managed subject before validation."""
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return None
        raw_body = await request.body()
        if not raw_body:
            return None
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        requested_user_id = payload.get("user_id")
        if requested_user_id is not None and str(requested_user_id).strip() != actor.user_id and actor.role not in {"owner", "admin"}:
            return JSONResponse(
                {"detail": "cross-user access denied"},
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        if requested_user_id is not None:
            request.state.tenant_user_id = str(requested_user_id).strip()
            return None
        if not self._route_body_accepts_user_id(request):
            return None

        payload["user_id"] = actor.user_id
        request.state.tenant_user_id = actor.user_id
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request._body = encoded
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": encoded, "more_body": False}

        request._receive = receive
        request.scope["headers"] = [
            (key, value)
            for key, value in request.scope["headers"]
            if key != b"content-length"
        ] + [(b"content-length", str(len(encoded)).encode("ascii"))]
        return None

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path == self.LOGIN_PATH:
            client_host = request.client.host if request.client else "unknown-client"
            limited = self._rate_limit_response(
                settings=settings,
                identity=f"login:{client_host}",
                scope="managed-login",
                limit=settings.api_login_rate_limit_requests,
            )
            if limited is not None:
                return limited
            return await call_next(request)
        if not settings.managed_auth_required or request.url.path.startswith(self.PUBLIC_PREFIXES):
            return await call_next(request)
        authorization = request.headers.get("authorization") or ""
        if not authorization.startswith("Bearer "):
            return JSONResponse({"detail": "managed session bearer token is required"}, status_code=401)
        try:
            with get_session_factory()() as db:
                actor = ManagedAuthService(db).authenticate(authorization.removeprefix("Bearer ").strip())
                beta_denial = self._private_beta_access_denial(
                    db=db,
                    settings=settings,
                    actor=actor,
                    path=request.url.path,
                )
                if beta_denial is not None:
                    return beta_denial
        except ProductionFoundationError as exc:
            client_host = request.client.host if request.client else "unknown-client"
            limited = self._rate_limit_response(
                settings=settings,
                identity=f"auth-failure:{client_host}",
                scope="managed-auth-failure",
                limit=settings.api_auth_failure_rate_limit_requests,
            )
            if limited is not None:
                return limited
            return JSONResponse({"detail": str(exc)}, status_code=401)
        limited = self._rate_limit_response(
            settings=settings,
            identity=f"user:{actor.user_id}",
            scope="managed-api",
            limit=settings.api_rate_limit_requests,
        )
        if limited is not None:
            return limited
        requested_user_id = request.query_params.get("user_id")
        if requested_user_id and requested_user_id != actor.user_id and actor.role not in {"owner", "admin"}:
            return JSONResponse({"detail": "cross-user access denied"}, status_code=403)
        # A number of legacy endpoints still expose ``user_id`` as a query
        # parameter with a local-only ``default-user`` default.  In managed
        # auth mode, an omitted parameter must resolve to the authenticated
        # subject instead of that shared default, otherwise two tenants can
        # accidentally read or write the same records.
        if requested_user_id is None:
            query = parse_qsl(request.scope.get("query_string", b"").decode("utf-8"), keep_blank_values=True)
            query.append(("user_id", actor.user_id))
            request.scope["query_string"] = urlencode(query, doseq=True).encode("utf-8")
        request.state.tenant_user_id = requested_user_id or actor.user_id
        body_denial = await self._bind_json_user(request, actor)
        if body_denial is not None:
            return body_denial
        request.state.current_user = actor
        headers = [(key, value) for key, value in request.scope["headers"] if key not in {b"x-ai-trading-user", b"x-ai-trading-role"}]
        headers.extend([(b"x-ai-trading-user", actor.user_id.encode()), (b"x-ai-trading-role", actor.role.encode())])
        request.scope["headers"] = headers
        tenant_token = bind_tenant(request.state.tenant_user_id)
        try:
            try:
                response = await call_next(request)
            except TenantIsolationError:
                response = JSONResponse(
                    {"detail": "cross-user database access denied"},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )
        finally:
            reset_tenant(tenant_token)
        response.headers["Cache-Control"] = "no-store"
        return response
