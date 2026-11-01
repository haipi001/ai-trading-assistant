from __future__ import annotations

import json
import ipaddress
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.secrets import SecretManagerResolver, SecretResolutionError
from app.models import LocalUserConfig, OperationalEvent, SecretReference


class NotificationDeliveryError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class WebhookNotificationService:
    """Opt-in webhook delivery with host allowlisting and credential-free audit."""

    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        resolver: SecretManagerResolver | None = None,
        transport: Callable[[str, dict[str, str], bytes, int], int] | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.resolver = resolver or SecretManagerResolver(self.settings)
        self.transport = transport or self._http_post

    def readiness(self, *, user_id: str) -> dict[str, Any]:
        preference = self.db.scalar(
            select(LocalUserConfig).where(
                LocalUserConfig.user_id == user_id,
                LocalUserConfig.config_key == "notification_preferences",
            ).limit(1)
        )
        value = preference.value_json if preference is not None else {}
        external = value.get("external_channels") if isinstance(value.get("external_channels"), dict) else {}
        consent = value.get("external_delivery_consent") if isinstance(value.get("external_delivery_consent"), dict) else {}
        reference = external.get("webhook") if isinstance(external.get("webhook"), str) else None
        secret = self.db.scalar(
            select(SecretReference).where(
                SecretReference.user_id == user_id,
                SecretReference.reference_key == reference,
                SecretReference.status == "active",
            ).limit(1)
        ) if reference else None
        blockers: list[str] = []
        if not self.settings.external_notification_delivery_enabled:
            blockers.append("external_notification_delivery_disabled")
        if not self.settings.notification_webhook_allowed_hosts:
            blockers.append("webhook_host_allowlist_empty")
        if not reference or not reference.startswith(("env://", "aws-sm://", "gcp-sm://", "vault://")):
            blockers.append("webhook_secret_reference_missing")
        if secret is None or secret.last_verified_at is None:
            blockers.append("webhook_secret_reference_unverified")
        if consent.get("webhook") is not True:
            blockers.append("webhook_delivery_consent_missing")
        return {
            "status": "ready" if not blockers else "blocked",
            "channel": "webhook",
            "secret_reference": reference,
            "consent_recorded": consent.get("webhook") is True,
            "allowed_hosts_configured": bool(self.settings.notification_webhook_allowed_hosts),
            "blockers": blockers,
            "external_message_sent": False,
        }

    def deliver_alert(self, *, user_id: str, alert: OperationalEvent, test: bool = False) -> dict[str, Any]:
        readiness = self.readiness(user_id=user_id)
        if readiness["status"] != "ready":
            return {**readiness, "status": "not_attempted", "delivered": False, "attempted": False}

        source = f"alert:{alert.id}"
        prior = list(
            self.db.scalars(
                select(OperationalEvent)
                .where(
                    OperationalEvent.user_id == user_id,
                    OperationalEvent.event_type == "notification.webhook_delivery",
                    OperationalEvent.source == source,
                )
                .order_by(OperationalEvent.created_at.desc())
            ).all()
        )
        if any(item.status == "delivered" for item in prior):
            return {**readiness, "status": "already_delivered", "delivered": True, "attempted": False}
        if len(prior) >= self.settings.notification_delivery_max_attempts:
            return {**readiness, "status": "attempts_exhausted", "delivered": False, "attempted": False}
        if prior:
            latest = prior[0].created_at
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - latest).total_seconds()
            if age < self.settings.notification_delivery_retry_seconds:
                return {**readiness, "status": "retry_deferred", "delivered": False, "attempted": False}

        delivered = False
        http_status: int | None = None
        error_class: str | None = None
        try:
            resolution = self.resolver.resolve(str(readiness["secret_reference"]))
            endpoint, authorization = self._parse_secret(resolution.value)
            payload = self._safe_payload(alert=alert, test=test)
            headers = {"Content-Type": "application/json", "User-Agent": "ai-trading-os-alerts/1"}
            if authorization:
                headers["Authorization"] = authorization
            http_status = self.transport(endpoint, headers, json.dumps(payload, separators=(",", ":")).encode("utf-8"), self.settings.notification_delivery_timeout_seconds)
            delivered = 200 <= http_status < 300
            if not delivered:
                error_class = "UnexpectedHTTPStatus"
        except (NotificationDeliveryError, SecretResolutionError, OSError, ValueError, HTTPError) as exc:
            error_class = exc.__class__.__name__

        attempt = OperationalEvent(
            user_id=user_id,
            event_type="notification.webhook_delivery",
            severity="info" if delivered else "critical",
            source=source,
            message="External alert webhook delivered." if delivered else "External alert webhook delivery failed.",
            status="delivered" if delivered else "failed",
            payload_json={
                "channel": "webhook",
                "alert_event_id": alert.id,
                "attempt": len(prior) + 1,
                "http_status": http_status,
                "error_class": error_class,
                "secret_reference": readiness["secret_reference"],
                "contains_credentials": False,
                "contains_customer_data": False,
                "external_notification_delivered": delivered,
                "test": test,
                "execution_available": False,
            },
        )
        if delivered:
            for previous in prior:
                if previous.status == "failed":
                    previous.status = "resolved"
                    previous.payload_json = {
                        **(previous.payload_json or {}),
                        "resolved_at": datetime.now(timezone.utc).isoformat(),
                        "resolution_reason": "later_webhook_delivery_succeeded",
                    }
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        return {
            **readiness,
            "status": "delivered" if delivered else "failed",
            "delivered": delivered,
            "attempted": True,
            "attempt": len(prior) + 1,
            "delivery_event_id": attempt.id,
            "http_status": http_status,
            "error_class": error_class,
            "external_message_sent": delivered,
        }

    def delivery_summary(self, *, user_id: str) -> dict[str, Any]:
        delivered = int(self.db.scalar(select(func.count()).select_from(OperationalEvent).where(
            OperationalEvent.user_id == user_id,
            OperationalEvent.event_type == "notification.webhook_delivery",
            OperationalEvent.status == "delivered",
        )) or 0)
        failed = int(self.db.scalar(select(func.count()).select_from(OperationalEvent).where(
            OperationalEvent.user_id == user_id,
            OperationalEvent.event_type == "notification.webhook_delivery",
            OperationalEvent.status == "failed",
        )) or 0)
        return {"delivered": delivered, "failed": failed, "real_delivery_evidence": delivered > 0}

    def _parse_secret(self, value: str) -> tuple[str, str | None]:
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = {"url": value}
        if not isinstance(parsed_value, dict):
            raise NotificationDeliveryError("webhook secret must be a URL or JSON object")
        endpoint = str(parsed_value.get("url") or "").strip()
        authorization = str(parsed_value.get("authorization") or "").strip() or None
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise NotificationDeliveryError("webhook endpoint must be credential-free HTTPS")
        if authorization and ("\r" in authorization or "\n" in authorization):
            raise NotificationDeliveryError("webhook authorization contains invalid characters")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
            raise NotificationDeliveryError("webhook endpoint cannot use a private or reserved IP literal")
        if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(".localhost"):
            raise NotificationDeliveryError("webhook endpoint cannot use localhost")
        if parsed.hostname.lower() not in self.settings.notification_webhook_allowed_hosts:
            raise NotificationDeliveryError("webhook host is not allowlisted")
        return endpoint, authorization

    @staticmethod
    def _safe_payload(*, alert: OperationalEvent, test: bool) -> dict[str, Any]:
        metrics = alert.payload_json or {}
        return {
            "schema": "ai-trading-os.alert.v1",
            "service": "ai-trading-os-backend",
            "event": "test.notification" if test else alert.event_type,
            "severity": "info" if test else alert.severity,
            "status": alert.status,
            "alert_event_id": alert.id,
            "summary": "Test notification delivery." if test else "HTTP request SLO breached; operator review required.",
            "metrics": {
                "window_hours": metrics.get("window_hours"),
                "requests": metrics.get("requests"),
                "errors": metrics.get("errors"),
                "availability": metrics.get("availability"),
                "error_rate": metrics.get("error_rate"),
                "average_latency_ms": metrics.get("average_latency_ms"),
            },
            "contains_customer_data": False,
            "execution_available": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _http_post(endpoint: str, headers: dict[str, str], body: bytes, timeout: int) -> int:
        opener = build_opener(_NoRedirect())
        request = Request(endpoint, data=body, headers=headers, method="POST")
        with opener.open(request, timeout=timeout) as response:
            return int(response.status)
