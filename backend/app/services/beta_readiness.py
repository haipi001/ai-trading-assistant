from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.core.config import get_settings
from app.models import AuditLog
from app.models import DataSourceConnection
from app.models import ExportArtifact
from app.models import OperationalEvent
from app.models import SecretReference
from app.models import UserAccount
from app.models.core import utc_now
from app.schemas.core import contains_secret_config_key
from app.services.data_catalog import DataCatalogService
from app.services.daily_use import DailyUseService
from app.services.ledger import InvestmentLedgerService
from app.services.ops_readiness import OpsReadinessService


class BetaReadinessError(ValueError):
    pass


ALLOWED_EVENT_SEVERITIES = {"info", "warning", "error", "critical"}
ALLOWED_EVENT_STATUSES = {"open", "acknowledged", "resolved", "closed"}


class BetaReadinessService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def whoami(self, current_user: AuthenticatedUser) -> dict[str, Any]:
        self._ensure_user(current_user)
        return self._whoami_payload(current_user)

    def access_check(self, *, current_user: AuthenticatedUser, permission: str) -> dict[str, Any]:
        allowed = permission in current_user.permissions
        return {
            "permission": permission,
            "allowed": allowed,
            "user_id": current_user.user_id,
            "role": current_user.role,
            "reason": "permission granted" if allowed else "permission denied for current beta role",
        }

    def list_users(self, *, limit: int = 100) -> list[UserAccount]:
        return list(
            self.db.scalars(
                select(UserAccount)
                .order_by(UserAccount.updated_at.desc(), UserAccount.id.desc())
                .limit(limit)
            ).all()
        )

    def upsert_user(self, **payload: Any) -> UserAccount:
        if contains_secret_config_key(payload.get("onboarding_state_json") or {}):
            raise BetaReadinessError("onboarding_state_json must not contain inline secrets")
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            raise BetaReadinessError("user_id is required")
        role = normalize_role(str(payload.get("role") or "viewer"))
        permissions = payload.get("permissions_json") or ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"])
        user = self.db.scalar(select(UserAccount).where(UserAccount.user_id == user_id).limit(1))
        if user is None:
            user = UserAccount(
                user_id=user_id,
                display_name=str(payload.get("display_name") or user_id),
                role=role,
                status=str(payload.get("status") or "active"),
                permissions_json=permissions,
                onboarding_state_json=payload.get("onboarding_state_json") or {},
            )
            self.db.add(user)
            action = "user_account.created"
        else:
            user.display_name = str(payload.get("display_name") or user.display_name)
            user.role = role
            user.status = str(payload.get("status") or user.status)
            user.permissions_json = permissions
            user.onboarding_state_json = payload.get("onboarding_state_json") or user.onboarding_state_json
            action = "user_account.updated"
        self.db.flush()
        self._audit(
            action,
            "UserAccount",
            user.id,
            {"user_id": user.user_id, "role": user.role, "status": user.status, "execution_available": False},
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def list_secret_references(self, *, user_id: str | None = None, limit: int = 100) -> list[SecretReference]:
        query = select(SecretReference)
        if user_id:
            query = query.where(SecretReference.user_id == user_id)
        return list(
            self.db.scalars(
                query.order_by(SecretReference.updated_at.desc(), SecretReference.id.desc()).limit(limit)
            ).all()
        )

    def create_secret_reference(self, *, current_user: AuthenticatedUser, **payload: Any) -> SecretReference:
        metadata_json = payload.get("metadata_json") or {}
        if contains_secret_config_key(metadata_json):
            raise BetaReadinessError("metadata_json must not contain inline secrets")
        reference_key = str(payload.get("reference_key") or "").strip()
        if not reference_key:
            raise BetaReadinessError("reference_key is required")
        user_id = str(payload.get("user_id") or current_user.user_id)
        reference = self.db.scalar(
            select(SecretReference)
            .where(SecretReference.user_id == user_id, SecretReference.reference_key == reference_key)
            .limit(1)
        )
        if reference is None:
            reference = SecretReference(
                user_id=user_id,
                reference_key=reference_key,
                provider=str(payload.get("provider") or "unknown"),
                scope=str(payload.get("scope") or "read_only"),
                storage_backend=str(payload.get("storage_backend") or "env_or_local_secret_store"),
                status=str(payload.get("status") or "active"),
                metadata_json=metadata_json,
            )
            self.db.add(reference)
            action = "secret_reference.created"
        else:
            reference.provider = str(payload.get("provider") or reference.provider)
            reference.scope = str(payload.get("scope") or reference.scope)
            reference.storage_backend = str(payload.get("storage_backend") or reference.storage_backend)
            reference.status = str(payload.get("status") or reference.status)
            reference.metadata_json = metadata_json
            action = "secret_reference.updated"
        self.db.flush()
        self._audit(
            action,
            "SecretReference",
            reference.id,
            {
                "user_id": reference.user_id,
                "reference_key": reference.reference_key,
                "provider": reference.provider,
                "contains_secret": False,
                "execution_available": False,
            },
        )
        self.db.commit()
        self.db.refresh(reference)
        return reference

    def list_events(
        self,
        *,
        severity: str | None = None,
        status: str | None = None,
        search_query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = select(OperationalEvent)
        if severity:
            query = query.where(OperationalEvent.severity == severity)
        if status:
            query = query.where(OperationalEvent.status == status)
        if search_query:
            search = f"%{search_query.strip()}%"
            query = query.where(
                OperationalEvent.message.ilike(search)
                | OperationalEvent.event_type.ilike(search)
                | OperationalEvent.source.ilike(search)
                | OperationalEvent.request_id.ilike(search)
            )
        events = list(
            self.db.scalars(
                query.order_by(OperationalEvent.created_at.desc(), OperationalEvent.id.desc()).limit(limit)
            ).all()
        )
        return [self._operational_event_read_payload(event) for event in events]

    def _operational_event_read_payload(self, event: OperationalEvent) -> dict[str, Any]:
        payload_json = event.payload_json if isinstance(event.payload_json, dict) else {}
        original_severity = str(event.severity or "info")
        original_status = str(event.status or "open")
        severity = original_severity if original_severity in ALLOWED_EVENT_SEVERITIES else "warning"
        status = original_status if original_status in ALLOWED_EVENT_STATUSES else "open"
        if severity != original_severity or status != original_status or payload_json is not event.payload_json:
            payload_json = {
                **payload_json,
                "event_normalized_for_admin_search": True,
                "original_severity": original_severity,
                "original_status": original_status,
            }
        return {
            "id": event.id,
            "user_id": event.user_id,
            "event_type": str(event.event_type or "operational_event"),
            "severity": severity,
            "source": str(event.source or "system"),
            "message": str(event.message or "Operational event recorded."),
            "status": status,
            "request_id": event.request_id,
            "payload_json": payload_json,
            "created_at": event.created_at or utc_now(),
        }

    def create_event(self, *, current_user: AuthenticatedUser, **payload: Any) -> OperationalEvent:
        if contains_secret_config_key(payload.get("payload_json") or {}):
            raise BetaReadinessError("payload_json must not contain inline secrets")
        event = OperationalEvent(
            user_id=payload.get("user_id") or current_user.user_id,
            event_type=str(payload.get("event_type") or "manual_event"),
            severity=str(payload.get("severity") or "info"),
            source=str(payload.get("source") or "beta_api"),
            message=str(payload.get("message") or ""),
            status=str(payload.get("status") or "open"),
            request_id=payload.get("request_id"),
            payload_json=payload.get("payload_json") or {},
        )
        self.db.add(event)
        self.db.flush()
        self._audit(
            "operational_event.created",
            "OperationalEvent",
            event.id,
            {"event_type": event.event_type, "severity": event.severity, "source": event.source},
        )
        self.db.commit()
        self.db.refresh(event)
        return event

    def create_backup_manifest(self, *, current_user: AuthenticatedUser) -> ExportArtifact:
        artifact = DailyUseService(self.db).create_backup_manifest(user_id=current_user.user_id)
        event = OperationalEvent(
            user_id=current_user.user_id,
            event_type="backup_manifest.created",
            severity="info",
            source="beta_readiness",
            message="Read-only beta backup manifest generated.",
            status="resolved",
            payload_json={"artifact_id": artifact.id, "execution_available": False},
        )
        self.db.add(event)
        self._audit(
            "beta_backup_manifest.created",
            "ExportArtifact",
            artifact.id,
            {"user_id": current_user.user_id, "execution_available": False},
        )
        self.db.commit()
        return artifact

    def readiness(self, *, current_user: AuthenticatedUser) -> dict[str, Any]:
        self._ensure_user(current_user, audit_seen=False)
        now = datetime.now(timezone.utc)
        checks = [
            self._auth_check(),
            self._user_isolation_check(),
            self._permissions_check(current_user),
            self._secret_reference_check(),
            self._backup_check(now=now, user_id=current_user.user_id),
            self._privacy_check(user_id=current_user.user_id),
            self._support_check(user_id=current_user.user_id),
            self._observability_check(),
            self._error_reporting_check(),
            self._deployment_check(),
            self._ci_cd_check(),
            self._safety_check(),
            self._automation_check(),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        return {
            "environment": self.settings.environment,
            "deployment_target": self.settings.deployment_target,
            "checked_at": now,
            "beta_ready": not blockers,
            "execution_available": False,
            "blockers": blockers,
            "checklist": checks,
        }

    def external_launch_report(self, *, current_user: AuthenticatedUser) -> dict[str, Any]:
        self._ensure_user(current_user, audit_seen=False)
        checked_at = datetime.now(timezone.utc)
        beta_report = self.readiness(current_user=current_user)
        ops_report = OpsReadinessService(self.db).stability_report(user_id=current_user.user_id)
        data_trust_report = DataCatalogService(self.db).trust_report(decision_scope="daily_review")
        ledger_preflight = InvestmentLedgerService(self.db).preflight(user_id=current_user.user_id)

        checks = [
            launch_check(
                "beta_readiness",
                "Beta readiness",
                status_from_beta_report(beta_report),
                "Beta access, user permissions, backup, observability, deployment, and safety checks.",
                blockers=beta_report["blockers"],
                next_actions=actions_from_checks(beta_report["checklist"]),
                evidence={
                    "beta_ready": beta_report["beta_ready"],
                    "check_count": len(beta_report["checklist"]),
                    "blocked_checks": [item["key"] for item in beta_report["checklist"] if item["status"] == "block"],
                    "warn_checks": [item["key"] for item in beta_report["checklist"] if item["status"] == "warn"],
                },
            ),
            launch_check(
                "ops_stability",
                "Ops stability",
                ops_report["overall_status"],
                "Database, Redis, freshness, backup, restore drill, CI, production target, deployment, and safety checks.",
                blockers=ops_report["blockers"],
                next_actions=actions_from_checks(ops_report["checks"]),
                evidence={
                    "overall_status": ops_report["overall_status"],
                    "check_count": len(ops_report["checks"]),
                    "commands": ops_report["commands"],
                },
            ),
            launch_check(
                "data_trust",
                "Daily review data trust",
                status_from_data_trust(data_trust_report["overall_status"]),
                f"Daily review data trust is {data_trust_report['overall_status']}.",
                blockers=[blocker for item in data_trust_report["items"] for blocker in item["blockers"]],
                next_actions=data_trust_report["recommended_actions"],
                evidence={
                    "decision_scope": data_trust_report["decision_scope"],
                    "overall_status": data_trust_report["overall_status"],
                    "trusted_count": data_trust_report["trusted_count"],
                    "review_only_count": data_trust_report["review_only_count"],
                    "blocked_count": data_trust_report["blocked_count"],
                },
            ),
            launch_check(
                "ledger_preflight",
                "Ledger preflight",
                ledger_preflight["status"],
                f"Ledger preflight is {ledger_preflight['status']}.",
                blockers=[check["summary"] for check in ledger_preflight["checks"] if check["status"] == "block"],
                next_actions=ledger_preflight["next_actions"],
                evidence={
                    "can_sync": ledger_preflight["can_sync"],
                    "can_reconcile": ledger_preflight["can_reconcile"],
                    "ledger_entries_count": ledger_preflight["ledger_entries_count"],
                    "positions_count": ledger_preflight["positions_count"],
                    "paper_executions_count": ledger_preflight["paper_executions_count"],
                    "data_trust_status": ledger_preflight["data_trust_status"],
                },
            ),
            launch_check(
                "release_controls",
                "Release controls",
                release_controls_status(self.settings),
                "External beta release controls are derived from auth, live execution flags, and automation level.",
                blockers=release_control_blockers(self.settings),
                next_actions=release_control_next_actions(self.settings),
                evidence=self._release_controls(),
            ),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        if any(check["status"] == "block" for check in checks):
            launch_status = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            launch_status = "conditional"
        else:
            launch_status = "ready"
        return {
            "environment": self.settings.environment,
            "deployment_target": self.settings.deployment_target,
            "checked_at": checked_at,
            "launch_status": launch_status,
            "beta_ready": beta_report["beta_ready"],
            "ops_status": ops_report["overall_status"],
            "data_trust_status": data_trust_report["overall_status"],
            "ledger_status": ledger_preflight["status"],
            "execution_available": False,
            "live_execution_available": False,
            "blockers": blockers,
            "next_actions": unique_actions(action for check in checks for action in check["next_actions"]),
            "release_controls": self._release_controls(),
            "required_manual_steps": [
                "Run ./scripts/regression_check.sh against the exact beta build.",
                "Create a fresh backup manifest and record a restore drill event.",
                "Verify beta auth, secret references, monitoring, deployment, and rollback metadata.",
                "Confirm live trading and live execution remain disabled for external beta.",
            ],
            "checks": checks,
        }

    def release_control_report(self, *, current_user: AuthenticatedUser) -> dict[str, Any]:
        self._ensure_user(current_user, audit_seen=False)
        checked_at = datetime.now(timezone.utc)
        beta_report = self.readiness(current_user=current_user)
        launch_report = self.external_launch_report(current_user=current_user)
        checks = [
            release_gate(
                "auth",
                "Auth gate",
                "ok" if self.settings.beta_auth_required and self.settings.beta_access_token_sha256 else "block",
                blockers=[] if self.settings.beta_auth_required and self.settings.beta_access_token_sha256 else ["beta_auth_not_fully_configured"],
                next_actions=["Configure beta auth and token hash before release."]
                if not (self.settings.beta_auth_required and self.settings.beta_access_token_sha256)
                else [],
                evidence={
                    "auth_required": self.settings.beta_auth_required,
                    "token_configured": bool(self.settings.beta_access_token_sha256),
                },
            ),
            release_gate(
                "secrets",
                "Secret reference gate",
                "ok" if any(item["key"] == "secret_references" and item["status"] == "ok" for item in beta_report["checklist"]) else "warn",
                next_actions=["Register metadata-only secret references for credentialed read-only sources."],
                evidence={"secret_reference_check": next((item for item in beta_report["checklist"] if item["key"] == "secret_references"), {})},
            ),
            release_gate(
                "backup",
                "Backup gate",
                "ok" if any(item["key"] == "backup" and item["status"] == "ok" for item in beta_report["checklist"]) else "warn",
                next_actions=["Create a fresh beta backup manifest and restore drill before release."],
                evidence={"backup_check": next((item for item in beta_report["checklist"] if item["key"] == "backup"), {})},
            ),
            release_gate(
                "safety_locks",
                "Safety locks",
                "ok" if not release_control_blockers(self.settings) else "block",
                blockers=release_control_blockers(self.settings),
                next_actions=release_control_next_actions(self.settings),
                evidence=self._release_controls(),
            ),
            release_gate(
                "launch_report",
                "External launch report",
                "block" if launch_report["launch_status"] == "blocked" else "warn" if launch_report["launch_status"] == "conditional" else "ok",
                blockers=launch_report["blockers"],
                next_actions=launch_report["next_actions"],
                evidence={
                    "launch_status": launch_report["launch_status"],
                    "ops_status": launch_report["ops_status"],
                    "data_trust_status": launch_report["data_trust_status"],
                    "ledger_status": launch_report["ledger_status"],
                },
            ),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        if any(check["status"] == "block" for check in checks):
            status = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            status = "conditional"
        else:
            status = "ready"
        return {
            "user_id": current_user.user_id,
            "checked_at": checked_at,
            "release_status": status,
            "can_invite_external_users": status == "ready",
            "execution_available": False,
            "live_execution_available": False,
            "blockers": unique_actions(blockers),
            "next_actions": unique_actions(action for check in checks for action in check["next_actions"]),
            "checks": checks,
        }

    def invitation_packet(self, *, current_user: AuthenticatedUser) -> dict[str, Any]:
        self._ensure_user(current_user, audit_seen=False)
        checked_at = datetime.now(timezone.utc)
        release = self.release_control_report(current_user=current_user)
        users = self.list_users(limit=200)
        active_users = [user for user in users if user.status == "active"]
        checks = [
            release_gate(
                "release_controls",
                "Release controls",
                "block" if release["release_status"] == "blocked" else "warn" if release["release_status"] == "conditional" else "ok",
                blockers=release["blockers"],
                next_actions=release["next_actions"],
                evidence={"release_status": release["release_status"]},
            ),
            release_gate(
                "user_roster",
                "Beta user roster",
                "ok" if active_users else "warn",
                next_actions=["Create or verify at least one active beta user before sharing access."]
                if not active_users
                else [],
                evidence={"active_user_count": len(active_users), "total_user_count": len(users)},
            ),
            release_gate(
                "manual_invitation_boundary",
                "Manual invitation boundary",
                "ok",
                evidence={
                    "auto_invites_sent": 0,
                    "email_delivery_available": False,
                    "deployment_triggered": False,
                    "execution_available": False,
                },
            ),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        if any(check["status"] == "block" for check in checks):
            status = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            status = "manual_review_required"
        else:
            status = "ready_for_manual_invites"
        return {
            "user_id": current_user.user_id,
            "checked_at": checked_at,
            "packet_status": status,
            "can_send_automatic_invites": False,
            "manual_invite_ready": status == "ready_for_manual_invites",
            "blockers": unique_actions(blockers),
            "next_actions": unique_actions(
                [action for check in checks for action in check["next_actions"]]
                + ["Invite users manually only after recording rollback and support ownership."]
            ),
            "release_control_report": release,
            "checks": checks,
            "execution_available": False,
            "deployment_triggered": False,
        }

    def _whoami_payload(self, current_user: AuthenticatedUser) -> dict[str, Any]:
        return {
            "user_id": current_user.user_id,
            "role": current_user.role,
            "permissions": current_user.permissions,
            "auth_required": self.settings.beta_auth_required,
            "token_configured": bool(self.settings.beta_access_token_sha256),
            "execution_available": False,
        }

    def _release_controls(self) -> dict[str, Any]:
        return {
            "auth_required": self.settings.beta_auth_required,
            "token_configured": bool(self.settings.beta_access_token_sha256),
            "live_trading_enabled": self.settings.live_trading_enabled,
            "live_execution_enabled": self.settings.live_execution_enabled,
            "live_execution_dry_run_only": self.settings.live_execution_dry_run_only,
            "live_execution_adapter_mode": self.settings.live_execution_adapter_mode,
            "automation_level": self.settings.automation_level,
            "external_llm_calls_enabled": self.settings.external_llm_calls_enabled,
            "environment": self.settings.environment,
            "deployment_target": self.settings.deployment_target,
        }

    def _ensure_user(self, current_user: AuthenticatedUser, *, audit_seen: bool = True) -> UserAccount:
        user = self.db.scalar(select(UserAccount).where(UserAccount.user_id == current_user.user_id).limit(1))
        now = datetime.now(timezone.utc)
        if user is None:
            user = UserAccount(
                user_id=current_user.user_id,
                display_name=current_user.user_id,
                role=current_user.role,
                status="active",
                permissions_json=current_user.permissions,
                onboarding_state_json={"created_by": "beta_auth_context", "execution_available": False},
                last_seen_at=now,
            )
            self.db.add(user)
            action = "user_account.created_from_auth_context"
        else:
            user.role = current_user.role
            user.permissions_json = current_user.permissions
            user.last_seen_at = now
            action = "user_account.seen"
        self.db.flush()
        if action != "user_account.seen" or audit_seen:
            self._audit(
                action,
                "UserAccount",
                user.id,
                {"user_id": user.user_id, "role": user.role, "execution_available": False},
            )
        self.db.commit()
        self.db.refresh(user)
        return user

    def _auth_check(self) -> dict[str, Any]:
        if self.settings.beta_auth_required and self.settings.beta_access_token_sha256:
            return check(
                "auth",
                "Beta access token",
                "ok",
                "Beta API requires a configured access token hash.",
            )
        if self.settings.beta_auth_required and not self.settings.beta_access_token_sha256:
            return check(
                "auth",
                "Beta access token",
                "block",
                "Auth is required, but no beta access token hash is configured.",
                blockers=["Configure BETA_ACCESS_TOKEN_SHA256 before external beta access."],
                next_actions=["Set BETA_ACCESS_TOKEN_SHA256 to a SHA-256 hash of the beta access token."],
            )
        return check(
            "auth",
            "Beta access token",
            "block",
            "Beta auth is disabled; this is acceptable for local use, but blocks external beta readiness.",
            blockers=["Enable beta auth before inviting external users."],
            next_actions=["Set BETA_AUTH_REQUIRED=true and configure BETA_ACCESS_TOKEN_SHA256."],
        )

    def _user_isolation_check(self) -> dict[str, Any]:
        total_users = self._count(select(func.count()).select_from(UserAccount))
        active_users = self._count(select(func.count()).select_from(UserAccount).where(UserAccount.status == "active"))
        if active_users > 0:
            return check(
                "user_isolation",
                "User records",
                "ok",
                f"{active_users} active beta user record(s) are available.",
            )
        return check(
            "user_isolation",
            "User records",
            "warn",
            f"No active beta users found out of {total_users} total records.",
            next_actions=["Open /beta/whoami once with the intended beta user headers or create a user record."],
        )

    def _permissions_check(self, current_user: AuthenticatedUser) -> dict[str, Any]:
        if current_user.permissions:
            return check(
                "permissions",
                "Role permissions",
                "ok",
                f"Current role {current_user.role} has {len(current_user.permissions)} permission(s).",
            )
        return check(
            "permissions",
            "Role permissions",
            "block",
            f"Current role {current_user.role} has no permissions.",
            blockers=["Current beta role has no permissions."],
            next_actions=["Use owner/admin/operator/viewer, or add explicit role permissions."],
        )

    def _secret_reference_check(self) -> dict[str, Any]:
        secret_refs = self._count(select(func.count()).select_from(SecretReference))
        credentialed_sources = self._count(
            select(func.count())
            .select_from(DataSourceConnection)
            .where(DataSourceConnection.credentials_ref.is_not(None))
        )
        if secret_refs:
            return check(
                "secret_references",
                "Secret references",
                "ok",
                f"{secret_refs} secret reference(s) registered; only metadata is stored.",
            )
        if credentialed_sources:
            return check(
                "secret_references",
                "Secret references",
                "warn",
                f"{credentialed_sources} data source(s) reference credentials, but no beta secret references are registered.",
                next_actions=["Register metadata-only secret references for each credentialed read-only data source."],
            )
        return check(
            "secret_references",
            "Secret references",
            "ok",
            "No credentialed source requires a secret reference yet.",
        )

    def _backup_check(self, *, now: datetime, user_id: str) -> dict[str, Any]:
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
                "No local backup manifest exists for the current beta user.",
                next_actions=["Create a backup manifest from the beta settings panel."],
            )
        created_at = artifact.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at >= now - timedelta(days=7):
            return check(
                "backup",
                "Backup manifest",
                "ok",
                f"Latest local backup manifest is fresh: {created_at.isoformat()}.",
            )
        return check(
            "backup",
            "Backup manifest",
            "warn",
            f"Latest local backup manifest is older than 7 days: {created_at.isoformat()}.",
            next_actions=["Create a fresh local backup manifest before beta onboarding."],
        )

    def _privacy_check(self, *, user_id: str) -> dict[str, Any]:
        artifact = self.db.scalar(
            select(ExportArtifact)
            .where(
                ExportArtifact.user_id == user_id,
                ExportArtifact.export_type == "user_data_portability_export",
                ExportArtifact.status == "ready",
            )
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        if artifact is None:
            return check(
                "privacy_self_service",
                "Privacy export and deletion",
                "warn",
                "Privacy policy, portable export, and guarded deletion are implemented but the current user has not exercised an export.",
                blockers=["privacy_export_not_exercised"],
                next_actions=["Download and inspect one redacted user-data export from Settings before a beta invitation."],
            )
        return check(
            "privacy_self_service",
            "Privacy export and deletion",
            "ok",
            f"Portable export exercised with credential-free artifact {artifact.id}; deletion remains user-confirmed with a seven-day grace period.",
        )

    def _support_check(self, *, user_id: str) -> dict[str, Any]:
        event = self.db.scalar(
            select(OperationalEvent)
            .where(OperationalEvent.user_id == user_id, OperationalEvent.event_type == "support.ticket")
            .order_by(OperationalEvent.created_at.desc(), OperationalEvent.id.desc())
            .limit(1)
        )
        if event is None:
            return check(
                "beta_support_loop",
                "Beta support and feedback loop",
                "warn",
                "The support queue and state machine are implemented, but this user has not exercised the flow.",
                blockers=["beta_support_flow_not_exercised"],
                next_actions=["Submit one non-sensitive test issue from Settings and move it through triage to resolution."],
            )
        return check(
            "beta_support_loop",
            "Beta support and feedback loop",
            "ok" if event.status in {"resolved", "closed"} else "warn",
            f"Latest support ticket is tracked with status {event.status}.",
            blockers=[] if event.status in {"resolved", "closed"} else ["beta_support_ticket_not_resolved"],
            next_actions=[] if event.status in {"resolved", "closed"} else ["Assign and resolve the open support ticket before beta onboarding."],
        )

    def _observability_check(self) -> dict[str, Any]:
        audit_logs = self._count(select(func.count()).select_from(AuditLog))
        events = self._count(select(func.count()).select_from(OperationalEvent))
        if audit_logs:
            return check(
                "observability",
                "Audit and ops trail",
                "ok",
                f"{audit_logs} audit log(s) and {events} operational event(s) are available.",
            )
        return check(
            "observability",
            "Audit and ops trail",
            "warn",
            "No audit logs exist yet.",
            next_actions=["Run the demo flow or create a beta operational event to confirm write path."],
        )

    def _error_reporting_check(self) -> dict[str, Any]:
        if self.settings.error_reporting_enabled:
            return check(
                "error_reporting",
                "Error reporting",
                "ok",
                "External error reporting is marked as enabled.",
            )
        return check(
            "error_reporting",
            "Error reporting",
            "warn",
            "External error reporting is not enabled; local operational events are available as a fallback.",
            next_actions=["Wire a production error reporting provider before wider beta."],
        )

    def _deployment_check(self) -> dict[str, Any]:
        target = self.settings.deployment_target
        if self.settings.environment.lower() == "local" or target.lower() == "local":
            return check(
                "deployment",
                "Deployment target",
                "warn",
                f"Running in {self.settings.environment}/{target}; suitable for local validation only.",
                next_actions=["Deploy a beta environment with managed secrets, logs, backups, and rollback path."],
            )
        return check(
            "deployment",
            "Deployment target",
            "ok",
            f"Deployment target is {target}.",
        )

    def _ci_cd_check(self) -> dict[str, Any]:
        root = Path(__file__).resolve().parents[3]
        regression_script = root / "scripts" / "regression_check.sh"
        workflows_dir = root / ".github" / "workflows"
        if regression_script.exists() and workflows_dir.exists():
            return check(
                "ci_cd",
                "Regression and CI",
                "ok",
                "Regression script and GitHub workflow directory are present.",
            )
        if regression_script.exists():
            return check(
                "ci_cd",
                "Regression and CI",
                "warn",
                "Regression script exists, but no GitHub workflow directory was found.",
                next_actions=["Add CI wiring before external beta."],
            )
        return check(
            "ci_cd",
            "Regression and CI",
            "warn",
            "No regression script was found.",
            next_actions=["Add a repeatable beta regression script and CI workflow."],
        )

    def _safety_check(self) -> dict[str, Any]:
        if not self.settings.live_trading_enabled:
            return check(
                "safety",
                "Live trading lock",
                "ok",
                "Live trading is disabled and execution_available remains false.",
            )
        return check(
            "safety",
            "Live trading lock",
            "block",
            "Live trading is enabled, which is outside the beta readiness safety boundary.",
            blockers=["Disable LIVE_TRADING_ENABLED for beta readiness."],
            next_actions=["Set LIVE_TRADING_ENABLED=false before any beta deployment."],
        )

    def _automation_check(self) -> dict[str, Any]:
        level = self.settings.automation_level
        safe_levels = {"A0_READ_ONLY", "A1_RESEARCH", "A2_ALERT", "A3_ORDER_DRAFT", "A4_APPROVAL_EXECUTION"}
        if level in safe_levels:
            return check(
                "automation",
                "Automation boundary",
                "ok",
                f"Automation level is {level}; live execution is still unavailable.",
            )
        return check(
            "automation",
            "Automation boundary",
            "block",
            f"Automation level {level} is not recognized as a safe beta level.",
            blockers=["Automation level is outside the approved beta boundary."],
            next_actions=["Use A0_READ_ONLY, A1_RESEARCH, A2_ALERT, A3_ORDER_DRAFT, or A4_APPROVAL_EXECUTION."],
        )

    def _audit(self, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        write_audit_log(
            self.db,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json,
            actor_id="phase5-beta-readiness-service",
        )

    def _count(self, query: Any) -> int:
        value = self.db.scalar(query)
        return int(value or 0)


def normalize_role(role: str) -> str:
    return role if role in ROLE_PERMISSIONS else "viewer"


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


def launch_check(
    key: str,
    label: str,
    status: str,
    detail: str,
    *,
    blockers: list[str] | None = None,
    next_actions: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "blockers": blockers or [],
        "next_actions": next_actions or [],
        "evidence": evidence or {},
    }


def release_gate(
    key: str,
    label: str,
    status: str,
    *,
    blockers: list[str] | None = None,
    next_actions: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "blockers": blockers or [],
        "next_actions": next_actions or [],
        "evidence": evidence or {},
    }


def status_from_beta_report(report: dict[str, Any]) -> str:
    if report["blockers"]:
        return "block"
    if any(item["status"] == "warn" for item in report["checklist"]):
        return "warn"
    return "ok"


def status_from_data_trust(status: str) -> str:
    if status == "trusted":
        return "ok"
    if status == "review_only":
        return "warn"
    return "block"


def actions_from_checks(checks: list[dict[str, Any]]) -> list[str]:
    return unique_actions(action for check in checks for action in check.get("next_actions", []))


def release_controls_status(settings: Any) -> str:
    blockers = release_control_blockers(settings)
    if blockers:
        return "block"
    if settings.environment.lower() == "local" or settings.deployment_target.lower() == "local":
        return "warn"
    return "ok"


def release_control_blockers(settings: Any) -> list[str]:
    blockers: list[str] = []
    if not settings.beta_auth_required or not settings.beta_access_token_sha256:
        blockers.append("External beta requires auth and a configured beta token hash.")
    if settings.live_trading_enabled or settings.live_execution_enabled:
        blockers.append("Live trading and live execution must remain disabled for external beta.")
    if settings.automation_level not in {"A0_READ_ONLY", "A1_RESEARCH", "A2_ALERT", "A3_ORDER_DRAFT", "A4_APPROVAL_EXECUTION"}:
        blockers.append("Automation level is outside the approved external beta boundary.")
    return blockers


def release_control_next_actions(settings: Any) -> list[str]:
    actions: list[str] = []
    if not settings.beta_auth_required or not settings.beta_access_token_sha256:
        actions.append("Set BETA_AUTH_REQUIRED=true and configure BETA_ACCESS_TOKEN_SHA256 before inviting external users.")
    if settings.live_trading_enabled or settings.live_execution_enabled:
        actions.append("Set LIVE_TRADING_ENABLED=false and LIVE_EXECUTION_ENABLED=false for external beta.")
    if settings.automation_level not in {"A0_READ_ONLY", "A1_RESEARCH", "A2_ALERT", "A3_ORDER_DRAFT", "A4_APPROVAL_EXECUTION"}:
        actions.append("Use a safe automation level before beta release.")
    if settings.environment.lower() == "local" or settings.deployment_target.lower() == "local":
        actions.append("Deploy to a managed beta target before external invitations.")
    return actions


def unique_actions(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result
