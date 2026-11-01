from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any

from redis import Redis
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.core.config import get_settings
from app.core.observability import ObservabilityUnavailable
from app.core.observability import RedisRequestMetrics
from app.models import DataSourceConnection
from app.models import ExportArtifact
from app.models import LocalUserConfig
from app.models import OperationalEvent
from app.models import ProductionReadinessTarget
from app.models import SecretReference
from app.schemas.core import contains_secret_config_key
from app.services.data_sources import DataSourceService
from app.services.notifications import WebhookNotificationService


REQUIRED_PRODUCTION_TARGET_TYPES = {"error_reporting", "backup_target", "secret_manager", "deployment"}

NOTIFICATION_CHANNELS = ("in_app", "email", "webhook", "feishu", "telegram")


class OpsReadinessService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def stability_report(self, *, user_id: str = "default-user") -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        checks = [
            self._database_check(),
            self._redis_check(),
            self._data_freshness_check(),
            self._backup_check(user_id=user_id, checked_at=checked_at),
            self._restore_drill_check(user_id=user_id, checked_at=checked_at),
            self._secret_reference_check(),
            self._ops_event_check(),
            self._ci_check(),
            self._safe_logging_check(),
            self._observability_metrics_check(),
            self._monitoring_check(user_id=user_id),
            self._api_abuse_check(),
            self._production_targets_check(user_id=user_id),
            self._deployment_check(),
            self._safety_check(),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        if any(check["status"] == "block" for check in checks):
            overall_status = "block"
        elif any(check["status"] == "warn" for check in checks):
            overall_status = "warn"
        else:
            overall_status = "ok"
        return {
            "environment": self.settings.environment,
            "deployment_target": self.settings.deployment_target,
            "checked_at": checked_at,
            "overall_status": overall_status,
            "execution_available": False,
            "blockers": blockers,
            "commands": [
                "cd backend && .venv/bin/pytest -q",
                "cd frontend && npm run typecheck",
                "cd backend && .venv/bin/alembic upgrade head",
                "./scripts/regression_check.sh",
                "git status --short",
            ],
            "checks": checks,
        }

    def product_stability_packet(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        stability = self.stability_report(user_id=user_id)
        baseline_doc = Path(__file__).resolve().parents[3] / "docs" / "BASELINE_HEALTH.md"
        checks = [
            stability_packet_check(
                "regression",
                "Regression command",
                "ok" if "./scripts/regression_check.sh" in stability["commands"] else "block",
                {"commands": stability["commands"]},
            ),
            stability_packet_check(
                "e2e",
                "E2E smoke readiness",
                "warn",
                {"recommended_command": "RUN_E2E=1 ./scripts/regression_check.sh", "automatically_ran_e2e": False},
            ),
            stability_packet_check(
                "docs",
                "Operator documentation",
                "ok" if baseline_doc.exists() else "warn",
                {"baseline_health_doc": "docs/BASELINE_HEALTH.md", "exists": baseline_doc.exists()},
            ),
            stability_packet_check(
                "rollback",
                "Rollback and restore",
                "warn" if stability["overall_status"] != "ok" else "ok",
                {"restore_drill_required": True, "overall_status": stability["overall_status"]},
            ),
            stability_packet_check(
                "execution_boundary",
                "Execution boundary",
                "ok",
                {"deployment_triggered": False, "restore_executed": False, "execution_available": False},
            ),
        ]
        blockers = list(stability["blockers"]) + [check["key"] for check in checks if check["status"] == "block"]
        if blockers:
            status = "blocked"
        elif any(check["status"] == "warn" for check in checks) or stability["overall_status"] == "warn":
            status = "hardening_required"
        else:
            status = "stable_for_beta_candidate"
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "packet_status": status,
            "stability_status": stability["overall_status"],
            "blockers": blockers,
            "next_actions": [
                "Run ./scripts/regression_check.sh before tagging any beta candidate.",
                "Run RUN_E2E=1 ./scripts/regression_check.sh before external demo or beta invite.",
                "Record a backup manifest and restore drill in an isolated environment before external beta.",
            ],
            "stability_report": stability,
            "checks": checks,
            "deployment_triggered": False,
            "restore_executed": False,
            "execution_available": False,
        }

    def restore_drill(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        artifact = self.db.scalar(
            select(ExportArtifact)
            .where(ExportArtifact.user_id == user_id, ExportArtifact.export_type == "local_backup_manifest")
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        status = "ok" if artifact is not None else "warn"
        steps = [
            {
                "key": "backup_manifest",
                "status": "ok" if artifact is not None else "warn",
                "detail": f"Latest backup artifact: {artifact.id}" if artifact is not None else "No local backup manifest exists yet.",
            },
            {
                "key": "database_restore_plan",
                "status": "manual",
                "detail": "Restore from a copied local database or managed backup into an isolated environment; this endpoint does not restore data.",
            },
            {
                "key": "migration_check",
                "status": "manual",
                "detail": "After restore, run `cd backend && .venv/bin/alembic upgrade head`.",
            },
            {
                "key": "regression_check",
                "status": "manual",
                "detail": "After restore, run `./scripts/regression_check.sh` and inspect demo smoke output.",
            },
        ]
        event = OperationalEvent(
            user_id=user_id,
            event_type="restore_drill",
            severity="info" if artifact is not None else "warning",
            source="ops_restore_drill",
            message="Restore drill plan generated; no restore command was executed.",
            status="resolved",
            payload_json={
                "latest_backup_artifact_id": artifact.id if artifact is not None else None,
                "latest_backup_created_at": artifact.created_at.isoformat() if artifact is not None else None,
                "restore_steps": steps,
                "execution_available": False,
            },
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": status,
            "latest_backup_artifact_id": artifact.id if artifact is not None else None,
            "latest_backup_created_at": artifact.created_at if artifact is not None else None,
            "operational_event": event,
            "restore_steps": steps,
            "execution_available": False,
        }

    def notification_channel_status(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        preference = self._local_config(user_id, "notification_preferences")
        value = preference.value_json if preference is not None else {}
        external_channels = value.get("external_channels") if isinstance(value.get("external_channels"), dict) else {}
        secret_refs = {
            item.reference_key: item
            for item in self.db.scalars(select(SecretReference).where(SecretReference.user_id == user_id)).all()
        }
        channels: list[dict[str, Any]] = []
        blockers: list[str] = []
        for channel in NOTIFICATION_CHANNELS:
            if channel == "in_app":
                channels.append({
                    "channel": channel,
                    "status": "ready",
                    "label": "In-app / Today Queue",
                    "requires_secret_reference": False,
                    "secret_reference": None,
                    "delivery_mode": "local_only",
                    "can_send_external": False,
                    "next_action": "Due reminders appear in Today Queue and settings.",
                })
                continue
            configured = external_channels.get(channel)
            reference_key = configured if isinstance(configured, str) and configured.startswith(("env:", "secretref:", "vault:", "keychain:", "local-secret:", "aws-sm:", "gcp-sm:")) else None
            ref = secret_refs.get(reference_key or "")
            if reference_key and ref is not None and ref.status == "active":
                status = "preflight_ready"
                next_action = "Run a dry-run test notification; production delivery remains opt-in."
            elif reference_key:
                status = "needs_secret_verification"
                blockers.append(f"{channel}_secret_reference_not_active")
                next_action = "Verify the secret reference in Secret Manager before enabling this channel."
            else:
                status = "not_configured"
                blockers.append(f"{channel}_not_configured")
                next_action = "Add a Secret Reference, not an inline token, before enabling this external channel."
            channels.append({
                "channel": channel,
                "status": status,
                "label": channel.title(),
                "requires_secret_reference": True,
                "secret_reference": reference_key,
                "delivery_mode": "external_dry_run_only",
                "can_send_external": False,
                "next_action": next_action,
            })
        webhook_service = WebhookNotificationService(self.db, self.settings)
        webhook_readiness = webhook_service.readiness(user_id=user_id)
        delivery_summary = webhook_service.delivery_summary(user_id=user_id)
        webhook_channel = next(item for item in channels if item["channel"] == "webhook")
        webhook_channel["status"] = "delivery_ready" if webhook_readiness["status"] == "ready" else webhook_channel["status"]
        webhook_channel["can_send_external"] = webhook_readiness["status"] == "ready"
        webhook_channel["delivery_readiness"] = webhook_readiness
        ready_external = [item for item in channels if item["channel"] != "in_app" and item["status"] in {"preflight_ready", "delivery_ready"}]
        if delivery_summary["real_delivery_evidence"]:
            external_delivery_status = "delivery_verified"
        elif webhook_readiness["status"] == "ready":
            external_delivery_status = "ready_not_tested"
        else:
            external_delivery_status = "dry_run_only" if ready_external else "not_configured"
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": "local_ready" if channels[0]["status"] == "ready" else "blocked",
            "external_delivery_status": external_delivery_status,
            "webhook_delivery": {"readiness": webhook_readiness, "summary": delivery_summary},
            "channels": channels,
            "blockers": blockers,
            "next_actions": [
                "Keep Today Queue and in-app reminders as the default notification path.",
                "Configure one external channel with a Secret Reference when you are ready.",
                "Run a dry-run test notification before any production delivery is enabled.",
            ],
            "execution_available": False,
            "external_message_sent": False,
        }

    def evaluate_observability_alert(self, *, user_id: str = "default-user") -> dict[str, Any]:
        try:
            report = RedisRequestMetrics(self.settings).snapshot(window_hours=24)
        except ObservabilityUnavailable:
            report = {
                "status": "unavailable",
                "reason": "request_metrics_store_unavailable",
                "sample_sufficient": False,
                "real_request_metrics": False,
            }
        open_events = list(
            self.db.scalars(
                select(OperationalEvent).where(
                    OperationalEvent.user_id == user_id,
                    OperationalEvent.event_type == "observability.slo_breached",
                    OperationalEvent.status == "open",
                )
            ).all()
        )
        created = False
        resolved = 0
        delivery: dict[str, Any] = {"status": "not_required", "delivered": False, "attempted": False}
        alert_event: OperationalEvent | None = open_events[0] if open_events else None
        if report["status"] == "breached" and not open_events:
            event = OperationalEvent(
                user_id=user_id,
                event_type="observability.slo_breached",
                severity="critical",
                source="redis-http-request-metrics",
                message="HTTP request SLO breached; operator review required.",
                status="open",
                payload_json={
                    "window_hours": report.get("window_hours"),
                    "requests": report.get("requests"),
                    "errors": report.get("errors"),
                    "availability": report.get("availability"),
                    "error_rate": report.get("error_rate"),
                    "average_latency_ms": report.get("average_latency_ms"),
                    "targets": report.get("targets"),
                    "contains_customer_data": False,
                    "external_notification_delivered": False,
                },
            )
            self.db.add(event)
            self.db.flush()
            alert_event = event
            created = True
        elif report["status"] == "ok" and open_events:
            resolved = len(open_events)
            for event in open_events:
                event.status = "resolved"
                event.payload_json = {
                    **(event.payload_json or {}),
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "resolution_reason": "request_slo_recovered",
                }
        if created or resolved:
            self.db.commit()
        if report["status"] == "breached" and alert_event is not None:
            delivery = WebhookNotificationService(self.db, self.settings).deliver_alert(user_id=user_id, alert=alert_event)
            if delivery.get("delivered"):
                alert_event.payload_json = {
                    **(alert_event.payload_json or {}),
                    "external_notification_delivered": True,
                    "external_notification_delivery_event_id": delivery.get("delivery_event_id"),
                }
                self.db.commit()
        return {
            "status": report["status"],
            "report": report,
            "alert_created": created,
            "alerts_resolved": resolved,
            "open_alerts": 1 if created else max(0, len(open_events) - resolved),
            "notification": {
                "in_app_event_recorded": created,
                "external_delivery_required": report["status"] == "breached",
                "external_notification_delivered": bool(delivery.get("delivered")),
                "external_delivery": delivery,
            },
            "execution_available": False,
        }

    def notification_webhook_test(self, *, user_id: str = "default-user") -> dict[str, Any]:
        rate_limit = self._consume_rate_limit(user_id=user_id, scope="notification_dry_run")
        if not rate_limit["allowed"]:
            raise ValueError("notification test is rate limited")
        event = OperationalEvent(
            user_id=user_id,
            event_type="notification.webhook_test",
            severity="info",
            source="notification_center",
            message="Operator explicitly requested an external webhook delivery test.",
            status="test",
            payload_json={"contains_customer_data": False, "execution_available": False},
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        result = WebhookNotificationService(self.db, self.settings).deliver_alert(user_id=user_id, alert=event, test=True)
        return {
            "status": result["status"],
            "delivery": result,
            "test_event_id": event.id,
            "rate_limit": rate_limit,
            "execution_available": False,
        }

    def notification_dry_run(self, *, user_id: str = "default-user", channel: str = "in_app", subject: str = "AI Trading OS test") -> dict[str, Any]:
        normalized = channel.strip().lower()
        if normalized not in NOTIFICATION_CHANNELS:
            raise ValueError("unsupported notification channel")
        status = self.notification_channel_status(user_id=user_id)
        channel_status = next((item for item in status["channels"] if item["channel"] == normalized), None)
        if channel_status is None:
            raise ValueError("notification channel not found")
        rate_limit = self._consume_rate_limit(user_id=user_id, scope="notification_dry_run")
        blocked = (normalized != "in_app" and channel_status["status"] != "preflight_ready") or not rate_limit["allowed"]
        outbox_payload = {
            "channel": normalized,
            "subject": subject,
            "status": "blocked" if blocked else "dry_run_recorded",
            "reason": "rate_limited" if not rate_limit["allowed"] else channel_status["status"],
            "secret_reference": channel_status["secret_reference"],
            "rate_limit": rate_limit,
            "external_message_sent": False,
            "execution_available": False,
        }
        event = OperationalEvent(
            user_id=user_id,
            event_type="notification_dry_run",
            severity="warning" if blocked else "info",
            source="notification_center",
            message="Notification dry run recorded; no external message was sent.",
            status="resolved" if not blocked else "open",
            payload_json=outbox_payload,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return {
            "user_id": user_id,
            "channel": normalized,
            "status": outbox_payload["status"],
            "blocked": blocked,
            "outbox_event_id": event.id,
            "outbox": outbox_payload,
            "rate_limit": rate_limit,
            "next_actions": [
                "Review the outbox event in Admin audit search.",
                "Keep external delivery disabled until the channel is verified and consented.",
            ],
            "execution_available": False,
            "external_message_sent": False,
        }

    def consume_rate_limit(self, *, user_id: str = "default-user", scope: str) -> dict[str, Any]:
        return self._consume_rate_limit(user_id=user_id, scope=scope)

    def security_control_plane(self, *, user_id: str = "default-user") -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        threat_model = self._local_config(user_id, "security_threat_model")
        rate_limits = self._local_config(user_id, "rate_limit_policy")
        if threat_model is None:
            threat_model = self._upsert_local_config(
                user_id,
                "security_threat_model",
                {
                    "version": "local-safe-v1",
                    "assets": ["portfolio data", "secret references", "order intents", "audit logs", "user sessions"],
                    "trust_boundaries": ["browser", "backend api", "local database", "external read-only providers", "secret manager references"],
                    "top_threats": [
                        {"key": "inline_secret_leak", "status": "mitigated", "control": "reject inline secrets in configs and payloads"},
                        {"key": "approval_bypass", "status": "mitigated", "control": "fail closed gates and execution_available=false"},
                        {"key": "notification_spam", "status": "needs_rate_limit", "control": "dry-run outbox and per-channel rate limits"},
                        {"key": "stale_data_promotion", "status": "mitigated", "control": "quality report, snapshot replay, fallback policy"},
                        {"key": "credential_scope_creep", "status": "needs_external_proof", "control": "read-only key evidence packet"},
                    ],
                    "execution_available": False,
                },
                "Local threat model. No secrets, no live execution.",
            )
        if rate_limits is None:
            rate_limits = self._upsert_local_config(
                user_id,
                "rate_limit_policy",
                {
                    "version": "local-safe-v1",
                    "rules": [
                        {"scope": "command_bar", "limit": 30, "window_seconds": 60, "mode": "audit_only"},
                        {"scope": "llm_calls", "limit": 20, "window_seconds": 3600, "mode": "fail_closed_when_provider_enabled"},
                        {"scope": "notification_dry_run", "limit": 10, "window_seconds": 3600, "mode": "fail_closed_local"},
                        {"scope": "external_read_only_sync", "limit": 60, "window_seconds": 3600, "mode": "provider_safe"},
                        {"scope": "broker_sandbox", "limit": 20, "window_seconds": 3600, "mode": "idempotent_only"},
                    ],
                    "default_action": "fail_closed_for_execution_paths",
                    "execution_available": False,
                },
                "Local rate-limit policy. Audit-only unless an external provider is explicitly enabled.",
            )
        else:
            normalized_policy = self._normalize_rate_limit_policy(rate_limits.value_json)
            if normalized_policy != rate_limits.value_json:
                rate_limits = self._upsert_local_config(
                    user_id,
                    "rate_limit_policy",
                    normalized_policy,
                    "Local rate-limit policy. Safe local actions are fail-closed where needed.",
                )
        missing_controls: list[str] = []
        if not threat_model.value_json.get("top_threats"):
            missing_controls.append("threat_model_top_threats_missing")
        if not rate_limits.value_json.get("rules"):
            missing_controls.append("rate_limit_rules_missing")
        rate_limit_statuses = [
            self._rate_limit_status(user_id=user_id, scope=str(rule.get("scope")))
            for rule in rate_limits.value_json.get("rules", [])
            if rule.get("scope")
        ]
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": "ready" if not missing_controls else "review_required",
            "threat_model": threat_model.value_json,
            "rate_limit_policy": rate_limits.value_json,
            "rate_limit_statuses": rate_limit_statuses,
            "missing_controls": missing_controls,
            "next_actions": [
                "Review the top threats before enabling any external integration.",
                "Keep execution paths fail-closed unless Auth, Secret Manager, monitoring, and legal gates are verified.",
                "Enable and verify the Redis-backed API middleware limits in staging before private beta.",
            ],
            "execution_available": False,
        }

    def list_production_targets(self, *, user_id: str = "default-user", limit: int = 50) -> list[ProductionReadinessTarget]:
        return list(
            self.db.scalars(
                select(ProductionReadinessTarget)
                .where(ProductionReadinessTarget.user_id == user_id)
                .order_by(ProductionReadinessTarget.updated_at.desc(), ProductionReadinessTarget.id.desc())
                .limit(limit)
            ).all()
        )

    def upsert_production_target(self, **payload: Any) -> ProductionReadinessTarget:
        metadata_json = payload.get("metadata_json") or {}
        if contains_secret_config_key(metadata_json):
            raise ValueError("production target metadata must not contain inline secrets")
        user_id = str(payload.get("user_id") or "default-user")
        target_type = str(payload.get("target_type") or "error_reporting")
        provider = str(payload.get("provider") or "manual")
        target = self.db.scalar(
            select(ProductionReadinessTarget)
            .where(
                ProductionReadinessTarget.user_id == user_id,
                ProductionReadinessTarget.target_type == target_type,
                ProductionReadinessTarget.provider == provider,
            )
            .limit(1)
        )
        if target is None:
            target = ProductionReadinessTarget(
                user_id=user_id,
                target_type=target_type,
                provider=provider,
                label=str(payload.get("label") or target_type),
                reference_key=payload.get("reference_key"),
                status=str(payload.get("status") or "configured"),
                required=bool(payload.get("required", True)),
                metadata_json=metadata_json,
                last_verified_at=datetime.now(timezone.utc) if payload.get("status") == "verified" else None,
            )
            self.db.add(target)
            action = "production_readiness_target.created"
        else:
            target.label = str(payload.get("label") or target.label)
            target.reference_key = payload.get("reference_key") or target.reference_key
            target.status = str(payload.get("status") or target.status)
            target.required = bool(payload.get("required", target.required))
            target.metadata_json = metadata_json
            if target.status == "verified":
                target.last_verified_at = datetime.now(timezone.utc)
            action = "production_readiness_target.updated"
        self.db.flush()
        write_audit_log(
            self.db,
            action=action,
            entity_type="ProductionReadinessTarget",
            entity_id=target.id,
            payload_json={
                "user_id": target.user_id,
                "target_type": target.target_type,
                "provider": target.provider,
                "status": target.status,
                "contains_secret": False,
                "execution_available": False,
            },
            actor_id="ops-readiness-service",
        )
        self.db.commit()
        self.db.refresh(target)
        return target

    def _local_config(self, user_id: str, config_key: str) -> LocalUserConfig | None:
        return self.db.scalar(
            select(LocalUserConfig)
            .where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == config_key)
            .limit(1)
        )

    def _upsert_local_config(self, user_id: str, config_key: str, value_json: dict[str, Any], description: str) -> LocalUserConfig:
        config = self._local_config(user_id, config_key)
        if config is None:
            config = LocalUserConfig(user_id=user_id, config_key=config_key, value_json=value_json, description=description)
            self.db.add(config)
        else:
            config.value_json = value_json
            config.description = description
        self.db.commit()
        self.db.refresh(config)
        return config

    def _normalize_rate_limit_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        rules = policy.get("rules") if isinstance(policy.get("rules"), list) else []
        normalized_rules: list[dict[str, Any]] = []
        seen: set[str] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            scope = str(rule.get("scope") or "").strip()
            if not scope:
                continue
            updated = dict(rule)
            if scope == "notification_dry_run":
                updated["limit"] = int(updated.get("limit") or 10)
                updated["window_seconds"] = int(updated.get("window_seconds") or 3600)
                updated["mode"] = "fail_closed_local"
            normalized_rules.append(updated)
            seen.add(scope)
        if "notification_dry_run" not in seen:
            normalized_rules.append({"scope": "notification_dry_run", "limit": 10, "window_seconds": 3600, "mode": "fail_closed_local"})
        return {
            **policy,
            "version": policy.get("version") or "local-safe-v1",
            "rules": normalized_rules,
            "default_action": policy.get("default_action") or "fail_closed_for_execution_paths",
            "execution_available": False,
        }

    def _rate_limit_rule(self, user_id: str, scope: str) -> dict[str, Any]:
        plane = self.security_control_plane(user_id=user_id)
        for rule in plane["rate_limit_policy"].get("rules", []):
            if rule.get("scope") == scope:
                return dict(rule)
        return {"scope": scope, "limit": 1, "window_seconds": 3600, "mode": "fail_closed_local"}

    def _rate_limit_status(self, *, user_id: str, scope: str) -> dict[str, Any]:
        rule = self._rate_limit_rule_without_plane(user_id=user_id, scope=scope)
        now = datetime.now(timezone.utc)
        usage_config = self._local_config(user_id, "rate_limit_usage")
        usage = usage_config.value_json if usage_config is not None else {}
        buckets = usage.get("buckets") if isinstance(usage.get("buckets"), dict) else {}
        bucket = buckets.get(scope) if isinstance(buckets.get(scope), dict) else {}
        window_started_at = self._parse_datetime(bucket.get("window_started_at")) or now
        if now - window_started_at >= timedelta(seconds=int(rule["window_seconds"])):
            count = 0
            window_started_at = now
        else:
            count = int(bucket.get("count") or 0)
        remaining = max(0, int(rule["limit"]) - count)
        return {
            "scope": scope,
            "mode": rule["mode"],
            "limit": int(rule["limit"]),
            "window_seconds": int(rule["window_seconds"]),
            "window_started_at": window_started_at.isoformat(),
            "count": count,
            "remaining": remaining,
            "allowed": remaining > 0 or str(rule["mode"]) == "audit_only",
            "execution_available": False,
        }

    def _consume_rate_limit(self, *, user_id: str, scope: str) -> dict[str, Any]:
        rule = self._rate_limit_rule(user_id=user_id, scope=scope)
        now = datetime.now(timezone.utc)
        usage_config = self._local_config(user_id, "rate_limit_usage")
        usage = usage_config.value_json if usage_config is not None else {"version": "local-safe-v1", "buckets": {}}
        buckets = usage.get("buckets") if isinstance(usage.get("buckets"), dict) else {}
        bucket = buckets.get(scope) if isinstance(buckets.get(scope), dict) else {}
        window_started_at = self._parse_datetime(bucket.get("window_started_at")) or now
        if now - window_started_at >= timedelta(seconds=int(rule["window_seconds"])):
            count = 0
            window_started_at = now
        else:
            count = int(bucket.get("count") or 0)
        allowed = count < int(rule["limit"]) or str(rule["mode"]) == "audit_only"
        next_count = count + 1 if allowed else count
        buckets[scope] = {
            "window_started_at": window_started_at.isoformat(),
            "count": next_count,
            "last_checked_at": now.isoformat(),
            "last_allowed": allowed,
        }
        usage = {"version": "local-safe-v1", "buckets": buckets, "updated_at": now.isoformat()}
        self._upsert_local_config(user_id, "rate_limit_usage", usage, "Local rate-limit usage counters. No secrets.")
        return {
            "scope": scope,
            "mode": rule["mode"],
            "limit": int(rule["limit"]),
            "window_seconds": int(rule["window_seconds"]),
            "window_started_at": window_started_at.isoformat(),
            "count": next_count,
            "remaining": max(0, int(rule["limit"]) - next_count),
            "allowed": allowed,
            "execution_available": False,
        }

    def _rate_limit_rule_without_plane(self, *, user_id: str, scope: str) -> dict[str, Any]:
        config = self._local_config(user_id, "rate_limit_policy")
        policy = self._normalize_rate_limit_policy(config.value_json if config is not None else {})
        for rule in policy.get("rules", []):
            if rule.get("scope") == scope:
                return {
                    "scope": scope,
                    "limit": int(rule.get("limit") or 1),
                    "window_seconds": int(rule.get("window_seconds") or 3600),
                    "mode": str(rule.get("mode") or "fail_closed_local"),
                }
        return {"scope": scope, "limit": 1, "window_seconds": 3600, "mode": "fail_closed_local"}

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _database_check(self) -> dict[str, Any]:
        try:
            self.db.execute(text("SELECT 1"))
        except Exception as exc:
            return check(
                "database",
                "Database",
                "block",
                f"Database query failed: {exc}",
                blockers=["Database must respond before any beta or daily workflow is reliable."],
                next_actions=["Check DATABASE_URL and run migrations before continuing."],
            )
        return check("database", "Database", "ok", "Database responded to SELECT 1.")

    def _redis_check(self) -> dict[str, Any]:
        try:
            client = Redis.from_url(
                str(self.settings.redis_url),
                socket_connect_timeout=self.settings.dependency_check_timeout_seconds,
                socket_timeout=self.settings.dependency_check_timeout_seconds,
            )
            if client.ping():
                return check("redis", "Redis", "ok", "Redis ping succeeded.")
        except Exception:
            pass
        return check(
            "redis",
            "Redis",
            "warn",
            "Redis is unavailable; core read-only flows still work, but async/background workflows should stay manual.",
            next_actions=["Start Redis or keep scheduled jobs in manual-run mode."],
        )

    def _data_freshness_check(self) -> dict[str, Any]:
        freshness = DataSourceService(self.db).freshness_overview()
        status = freshness["overall_status"]
        if status == "ok":
            return check("data_freshness", "Data freshness", "ok", "Tracked datasets are fresh enough for local review.")
        if status == "block":
            return check(
                "data_freshness",
                "Data freshness",
                "block",
                f"{freshness['blocked_count']} dataset(s) have blocking quality issues.",
                blockers=["Refresh or repair blocked datasets before using them in decision workflows."],
                next_actions=["Open Data Sources and review the freshness table."],
            )
        return check(
            "data_freshness",
            "Data freshness",
            "warn",
            f"{freshness['stale_count']} stale and {freshness['missing_count']} missing dataset(s) need attention.",
            next_actions=["Refresh read-only market/account data or import a CSV snapshot."],
        )

    def _backup_check(self, *, user_id: str, checked_at: datetime) -> dict[str, Any]:
        artifact = self.db.scalar(
            select(ExportArtifact)
            .where(ExportArtifact.user_id == user_id, ExportArtifact.export_type == "local_backup_manifest")
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        if artifact is None:
            return check(
                "backup",
                "Backup manifest",
                "warn",
                "No local backup manifest exists for this user.",
                next_actions=["Create a backup manifest from Settings before wider beta testing."],
            )
        created_at = artifact.created_at if artifact.created_at.tzinfo else artifact.created_at.replace(tzinfo=timezone.utc)
        if created_at >= checked_at - timedelta(days=7):
            return check("backup", "Backup manifest", "ok", f"Latest backup manifest is fresh: {created_at.isoformat()}.")
        return check(
            "backup",
            "Backup manifest",
            "warn",
            f"Latest backup manifest is older than 7 days: {created_at.isoformat()}.",
            next_actions=["Create a fresh local backup manifest."],
        )

    def _restore_drill_check(self, *, user_id: str, checked_at: datetime) -> dict[str, Any]:
        event = self.db.scalar(
            select(OperationalEvent)
            .where(
                OperationalEvent.user_id == user_id,
                OperationalEvent.event_type == "restore_drill",
                OperationalEvent.status == "resolved",
            )
            .order_by(OperationalEvent.created_at.desc(), OperationalEvent.id.desc())
            .limit(1)
        )
        if event is None:
            return check(
                "restore_drill",
                "Restore drill",
                "warn",
                "No restore drill event has been recorded.",
                next_actions=["Run the restore drill plan from Settings before external beta."],
            )
        created_at = event.created_at if event.created_at.tzinfo else event.created_at.replace(tzinfo=timezone.utc)
        if created_at >= checked_at - timedelta(days=30):
            return check("restore_drill", "Restore drill", "ok", f"Latest restore drill was recorded at {created_at.isoformat()}.")
        return check(
            "restore_drill",
            "Restore drill",
            "warn",
            f"Latest restore drill is older than 30 days: {created_at.isoformat()}.",
            next_actions=["Run a fresh restore drill plan before external beta."],
        )

    def _secret_reference_check(self) -> dict[str, Any]:
        secret_refs = self._count(select(func.count()).select_from(SecretReference))
        credentialed_sources = self._count(
            select(func.count()).select_from(DataSourceConnection).where(DataSourceConnection.credentials_ref.is_not(None))
        )
        if credentialed_sources and not secret_refs:
            return check(
                "secret_references",
                "Secret references",
                "warn",
                f"{credentialed_sources} credentialed data source(s) exist but no metadata-only secret reference is registered.",
                next_actions=["Register SecretReference rows for every credentials_ref before external beta."],
            )
        return check(
            "secret_references",
            "Secret references",
            "ok",
            f"{secret_refs} secret reference(s), {credentialed_sources} credentialed data source(s). Inline secrets are not required.",
        )

    def _ops_event_check(self) -> dict[str, Any]:
        open_critical = self._count(
            select(func.count())
            .select_from(OperationalEvent)
            .where(OperationalEvent.status != "resolved", OperationalEvent.severity.in_(["error", "critical"]))
        )
        total = self._count(select(func.count()).select_from(OperationalEvent))
        if open_critical:
            return check(
                "ops_events",
                "Operational events",
                "block",
                f"{open_critical} unresolved error/critical operational event(s) exist.",
                blockers=["Resolve or acknowledge critical operational events before beta expansion."],
                next_actions=["Review /beta/events and close the operational issue."],
            )
        if total:
            return check("ops_events", "Operational events", "ok", f"{total} operational event(s) are recorded.")
        return check(
            "ops_events",
            "Operational events",
            "warn",
            "No operational event has been recorded yet.",
            next_actions=["Create a smoke operational event from Settings to verify the audit path."],
        )

    def _ci_check(self) -> dict[str, Any]:
        root = Path(__file__).resolve().parents[3]
        regression_script = root / "scripts" / "regression_check.sh"
        migration_guard = root / "scripts" / "migration_guard.sh"
        secret_scan = root / "scripts" / "secret_scan.py"
        workflows_dir = root / ".github" / "workflows"
        ci_file = workflows_dir / "ci.yml"
        workflow_text = ci_file.read_text(encoding="utf-8") if ci_file.exists() else ""
        required_markers = ("migration_guard.sh", "secret_scan.py", "pip-audit", "bandit", "npm audit")
        missing_markers = [marker for marker in required_markers if marker not in workflow_text]
        if regression_script.exists() and migration_guard.exists() and secret_scan.exists() and ci_file.exists() and not missing_markers:
            return check(
                "ci",
                "CI and release protection",
                "ok",
                "CI includes regression, migration parity/rollback, dependency audit, SAST, and secret scanning gates.",
            )
        if ci_file.exists() and (not migration_guard.exists() or not secret_scan.exists() or missing_markers):
            missing = []
            if not migration_guard.exists():
                missing.append("migration_guard.sh")
            if not secret_scan.exists():
                missing.append("secret_scan.py")
            missing.extend(missing_markers)
            return check(
                "ci",
                "CI and release protection",
                "warn",
                f"CI security/release gates are incomplete: {', '.join(sorted(set(missing)))}.",
                next_actions=["Restore every migration, dependency, SAST, and secret-scanning gate before private beta."],
            )
        if regression_script.exists() and workflows_dir.exists():
            return check(
                "ci",
                "CI and regression",
                "warn",
                "Regression script and workflow directory exist, but ci.yml was not found.",
                next_actions=["Add .github/workflows/ci.yml before inviting external users."],
            )
        if regression_script.exists():
            return check(
                "ci",
                "CI and regression",
                "warn",
                "Regression script exists, but no GitHub workflow directory was found.",
                next_actions=["Add CI workflow wiring before inviting external users."],
            )
        return check(
            "ci",
            "CI and regression",
            "warn",
            "No regression script was found.",
            next_actions=["Add a repeatable regression command before beta testing."],
        )

    def _safe_logging_check(self) -> dict[str, Any]:
        if self.settings.safe_request_logging_enabled:
            return check(
                "safe_request_logging",
                "Safe request logging",
                "ok",
                "Structured request logs exclude query strings, headers, bodies, raw paths, and exception messages; Uvicorn access logs are disabled.",
            )
        production_like = self.settings.environment.lower() in {"staging", "production"} or self.settings.deployment_target.lower() != "local"
        return check(
            "safe_request_logging",
            "Safe request logging",
            "block" if production_like else "warn",
            "Safe structured request logging is disabled.",
            blockers=["Enable SAFE_REQUEST_LOGGING_ENABLED before private beta."] if production_like else [],
            next_actions=["Enable safe request logging and verify redaction tests before deployment."],
        )

    def _observability_metrics_check(self) -> dict[str, Any]:
        if self.settings.observability_metrics_enabled:
            return check(
                "observability_metrics",
                "Request metrics and SLO",
                "ok",
                "Redis-backed HTTP request counts, 5xx errors, latency, availability, Prometheus export, and SLO evaluation are enabled.",
            )
        production_like = self.settings.environment.lower() in {"staging", "production"} or self.settings.deployment_target.lower() != "local"
        return check(
            "observability_metrics",
            "Request metrics and SLO",
            "block" if production_like else "warn",
            "Real HTTP request metrics are disabled; OperationalEvent counts are not accepted as availability evidence.",
            blockers=["Enable OBSERVABILITY_METRICS_ENABLED before private beta."] if production_like else [],
            next_actions=["Enable Redis request metrics and verify an injected 5xx produces an SLO alert."],
        )

    def _monitoring_check(self, *, user_id: str) -> dict[str, Any]:
        production_like = self.settings.environment.lower() in {"staging", "production"} or self.settings.deployment_target.lower() != "local"
        delivery = WebhookNotificationService(self.db, self.settings).delivery_summary(user_id=user_id)
        if self.settings.error_reporting_enabled and delivery["real_delivery_evidence"]:
            return check("monitoring", "Error reporting and alert delivery", "ok", "External error reporting is enabled and at least one webhook delivery is recorded.")
        blockers: list[str] = []
        if production_like and not self.settings.error_reporting_enabled:
            blockers.append("Enable an external error reporting provider before private beta.")
        if production_like and not delivery["real_delivery_evidence"]:
            blockers.append("Deliver and verify an external test alert before private beta.")
        return check(
            "monitoring",
            "Error reporting and alert delivery",
            "block" if production_like else "warn",
            "External error reporting and real alert delivery evidence are both required; configuration alone is insufficient.",
            blockers=blockers,
            next_actions=["Configure error reporting, send an explicit webhook test, and confirm the responsible operator received it."],
        )

    def _api_abuse_check(self) -> dict[str, Any]:
        if self.settings.managed_auth_required and self.settings.api_rate_limit_enabled:
            return check(
                "api_abuse_protection",
                "API abuse protection",
                "ok",
                (
                    "Managed login and authenticated API requests use Redis-backed atomic fixed-window limits "
                    f"({self.settings.api_login_rate_limit_requests} login / "
                    f"{self.settings.api_auth_failure_rate_limit_requests} failed-auth / "
                    f"{self.settings.api_rate_limit_requests} API requests per "
                    f"{self.settings.api_rate_limit_window_seconds}s); store failure fails closed."
                ),
            )
        production_like = self.settings.environment.lower() in {"staging", "production"} or self.settings.deployment_target.lower() != "local"
        return check(
            "api_abuse_protection",
            "API abuse protection",
            "block" if production_like else "warn",
            "Managed-auth API rate limiting is not fully enabled.",
            blockers=["Enable managed auth and Redis-backed API rate limiting before private beta."] if production_like else [],
            next_actions=[
                "Set MANAGED_AUTH_REQUIRED=true and API_RATE_LIMIT_ENABLED=true in staging/production.",
                "Verify Redis availability and run login/authenticated request throttle tests.",
            ],
        )

    def _production_targets_check(self, *, user_id: str) -> dict[str, Any]:
        targets = self.list_production_targets(user_id=user_id, limit=100)
        configured = {
            target.target_type
            for target in targets
            if target.required and target.status in {"configured", "verified"}
        }
        missing = sorted(REQUIRED_PRODUCTION_TARGET_TYPES - configured)
        if not missing:
            return check(
                "production_targets",
                "Production targets",
                "ok",
                "Required production targets have metadata records for deployment, backups, secrets, and error reporting.",
            )
        return check(
            "production_targets",
            "Production targets",
            "warn",
            f"Missing production target metadata: {', '.join(missing)}.",
            next_actions=["Record metadata-only production targets before external beta; do not paste secrets."],
        )

    def _deployment_check(self) -> dict[str, Any]:
        if self.settings.environment.lower() == "local" or self.settings.deployment_target.lower() == "local":
            return check(
                "deployment",
                "Deployment",
                "warn",
                f"Running in {self.settings.environment}/{self.settings.deployment_target}; this is local-validation only.",
                next_actions=["Use a managed beta deployment target with secrets, logs, backups, and rollback notes."],
            )
        return check("deployment", "Deployment", "ok", f"Deployment target is {self.settings.deployment_target}.")

    def _safety_check(self) -> dict[str, Any]:
        safe_automation = self.settings.automation_level in {"A0_READ_ONLY", "A1_RESEARCH", "A2_ALERT", "A3_ORDER_DRAFT", "A4_APPROVAL_EXECUTION"}
        if not self.settings.live_trading_enabled and not self.settings.live_execution_enabled and safe_automation:
            return check(
                "safety",
                "Execution safety",
                "ok",
                f"Live trading/execution are disabled and automation is {self.settings.automation_level}.",
            )
        return check(
            "safety",
            "Execution safety",
            "block",
            "Execution settings are outside the approved read-only/beta boundary.",
            blockers=["Disable live trading/live execution and use a safe automation level."],
            next_actions=["Set LIVE_TRADING_ENABLED=false, LIVE_EXECUTION_ENABLED=false, and automation to a safe level."],
        )

    def _count(self, query: Any) -> int:
        value = self.db.scalar(query)
        return int(value or 0)


def check(
    key: str,
    label: str,
    status: str,
    detail: str,
    *,
    blockers: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "blockers": blockers or [],
        "next_actions": next_actions or [],
    }


def stability_packet_check(key: str, label: str, status: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "evidence": evidence,
    }
