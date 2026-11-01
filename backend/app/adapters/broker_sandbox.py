from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen

from app.core.config import Settings
from app.core.config import get_settings
from app.core.secrets import SecretManagerResolver


class SandboxBrokerError(ValueError):
    pass


class HttpSandboxBrokerAdapter:
    """Generic sandbox-only adapter. Production-looking hosts fail closed."""

    def __init__(self, settings: Settings | None = None, *, transport: Any | None = None):
        self.settings = settings or get_settings()
        self.secret_resolver = SecretManagerResolver(self.settings)
        self.transport = transport or self._request
        self.base_url = str(self.settings.sandbox_broker_base_url or "").rstrip("/")
        self._validate_boundary()

    def submit(self, payload: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        if not idempotency_key.strip():
            raise SandboxBrokerError("idempotency key is required")
        safe_payload = {**payload, "sandbox": True, "production_execution_allowed": False}
        return self.transport("POST", "/orders", safe_payload, idempotency_key)

    def order(self, external_order_id: str) -> dict[str, Any]:
        if not external_order_id:
            raise SandboxBrokerError("external sandbox order id is required")
        return self.transport("GET", f"/orders/{external_order_id}", None, None)

    def cancel(self, external_order_id: str, *, idempotency_key: str) -> dict[str, Any]:
        return self.transport("POST", f"/orders/{external_order_id}/cancel", {"sandbox": True}, idempotency_key)

    def _validate_boundary(self) -> None:
        if not self.base_url or not self.settings.sandbox_broker_token_ref:
            raise SandboxBrokerError("sandbox broker URL and token reference are required")
        parsed = urlparse(self.base_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(marker in hostname for marker in ("sandbox", "paper", "testnet")):
            raise SandboxBrokerError("broker adapter accepts HTTPS sandbox/paper/testnet hosts only")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None, idempotency_key: str | None) -> dict[str, Any]:
        token = self.secret_resolver.resolve(str(self.settings.sandbox_broker_token_ref)).value
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.settings.external_api_timeout_seconds) as response:
                result = json.loads(response.read().decode())
        except Exception as exc:
            raise SandboxBrokerError("sandbox broker request failed") from exc
        if not isinstance(result, dict):
            raise SandboxBrokerError("sandbox broker returned invalid JSON")
        return result
