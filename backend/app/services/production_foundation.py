from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from urllib.request import Request
from urllib.request import urlopen

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.core.config import Settings
from app.core.config import get_settings
from app.core.observability import ObservabilityUnavailable
from app.core.observability import RedisRequestMetrics
from app.core.secrets import SecretManagerResolver
from app.models import AuditLog
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import DataSourceConnection
from app.models import ExportArtifact
from app.models import InvestmentLedgerEntry
from app.models import LocalUserConfig
from app.models import OperationalEvent
from app.models import ProductionReadinessTarget
from app.models import SecretReference
from app.models import UserAccount
from app.schemas.core import contains_secret_config_key


class ProductionFoundationError(ValueError):
    pass


class ManagedAuthService:
    def __init__(self, db: Session, settings: Settings | None = None, *, transport: Any | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.secret_resolver = SecretManagerResolver(self.settings)
        self.transport = transport or self._userinfo_request

    def login(self, access_token: str) -> dict[str, Any]:
        if not self.settings.oidc_userinfo_url or not self.settings.oidc_issuer or not self.settings.oidc_client_id:
            raise ProductionFoundationError("OIDC issuer, client id, and userinfo URL must be configured")
        claims = self.transport(access_token)
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise ProductionFoundationError("OIDC userinfo response is missing sub")
        issuer = claims.get("iss")
        if issuer and str(issuer).rstrip("/") != self.settings.oidc_issuer.rstrip("/"):
            raise ProductionFoundationError("OIDC issuer mismatch")
        audience = claims.get("aud")
        if audience and self.settings.oidc_client_id not in ([audience] if isinstance(audience, str) else audience):
            raise ProductionFoundationError("OIDC audience mismatch")
        role = str(claims.get(self.settings.oidc_role_claim) or "viewer").lower()
        if role not in ROLE_PERMISSIONS:
            role = "viewer"
        user = self.db.scalar(select(UserAccount).where(UserAccount.user_id == subject).limit(1))
        if user is None:
            if self.settings.managed_auth_invitation_required:
                raise ProductionFoundationError("a valid invitation is required")
            user = UserAccount(
                user_id=subject,
                display_name=str(claims.get("name") or claims.get("preferred_username") or subject),
                role=role,
                status="active",
                permissions_json=ROLE_PERMISSIONS[role],
                onboarding_state_json={"identity_provider": self.settings.oidc_issuer, "email_verified": bool(claims.get("email_verified"))},
            )
            self.db.add(user)
        else:
            if user.status in {"revoked", "suspended"}:
                raise ProductionFoundationError("user access is revoked or suspended")
            # An invitation is the authority for the eventual role. Identity-provider
            # claims must not silently escalate an invited account before acceptance.
            if user.status != "invited":
                user.role = role
                user.permissions_json = ROLE_PERMISSIONS[role]
            role = "viewer" if user.status == "invited" else user.role
            user.last_seen_at = now()
        self.db.flush()
        token, jti, expires_at = self._issue_session(subject, role)
        self._audit("managed_auth.session_created", "UserAccount", user.id, {"user_id": subject, "role": role, "jti": jti})
        self.db.commit()
        return {
            "session_token": token,
            "token_type": "Bearer",
            "expires_at": expires_at,
            "user": {"user_id": subject, "role": role, "permissions": ROLE_PERMISSIONS[role], "status": user.status},
        }

    def authenticate(self, token: str) -> AuthenticatedUser:
        payload = self._verify_session(token)
        jti = str(payload["jti"])
        record = self.db.scalar(
            select(LocalUserConfig)
            .where(LocalUserConfig.user_id == payload["sub"], LocalUserConfig.config_key == f"auth_session:{jti}")
            .limit(1)
        )
        if record is None or record.value_json.get("status") != "active":
            raise ProductionFoundationError("session is revoked or unknown")
        role = str(payload.get("role") or "viewer")
        return AuthenticatedUser(
            user_id=str(payload["sub"]),
            role=role,
            permissions=ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"]),
            auth_required=True,
            token_configured=True,
        )

    def revoke(self, token: str) -> dict[str, Any]:
        payload = self._verify_session(token)
        record = self.db.scalar(
            select(LocalUserConfig)
            .where(LocalUserConfig.user_id == payload["sub"], LocalUserConfig.config_key == f"auth_session:{payload['jti']}")
            .limit(1)
        )
        if record:
            record.value_json = {**record.value_json, "status": "revoked", "revoked_at": now().isoformat()}
        self._audit("managed_auth.session_revoked", "LocalUserConfig", str(payload["jti"]), {"user_id": payload["sub"]})
        self.db.commit()
        return {"status": "revoked", "execution_available": False}

    def _issue_session(self, user_id: str, role: str) -> tuple[str, str, datetime]:
        if not self.settings.auth_session_secret_ref:
            raise ProductionFoundationError("AUTH_SESSION_SECRET_REF is required")
        signing_key = self.secret_resolver.resolve(self.settings.auth_session_secret_ref).value.encode("utf-8")
        jti = secrets.token_urlsafe(18)
        expires_at = now() + timedelta(seconds=self.settings.auth_session_ttl_seconds)
        payload = {"sub": user_id, "role": role, "jti": jti, "exp": int(expires_at.timestamp()), "iss": "ai-trading-os"}
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(signing_key, encoded.encode(), hashlib.sha256).hexdigest()
        token = f"atos1.{encoded}.{signature}"
        self.db.add(
            LocalUserConfig(
                user_id=user_id,
                config_key=f"auth_session:{jti}",
                value_json={"status": "active", "role": role, "expires_at": expires_at.isoformat(), "token_sha256": hashlib.sha256(token.encode()).hexdigest()},
                description="Managed OIDC session metadata; no provider access token is stored.",
            )
        )
        return token, jti, expires_at

    def _verify_session(self, token: str) -> dict[str, Any]:
        if not self.settings.auth_session_secret_ref:
            raise ProductionFoundationError("AUTH_SESSION_SECRET_REF is required")
        try:
            prefix, encoded, signature = token.split(".", 2)
            if prefix != "atos1":
                raise ValueError
            signing_key = self.secret_resolver.resolve(self.settings.auth_session_secret_ref).value.encode("utf-8")
            expected = hmac.new(signing_key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        except Exception as exc:
            raise ProductionFoundationError("invalid managed session") from exc
        if int(payload.get("exp") or 0) <= int(now().timestamp()):
            raise ProductionFoundationError("managed session expired")
        return payload

    def _userinfo_request(self, access_token: str) -> dict[str, Any]:
        request = Request(
            str(self.settings.oidc_userinfo_url),
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.settings.external_api_timeout_seconds) as response:
                payload = json.loads(response.read().decode())
        except Exception as exc:
            raise ProductionFoundationError("OIDC userinfo request failed") from exc
        if not isinstance(payload, dict):
            raise ProductionFoundationError("OIDC userinfo returned invalid JSON")
        return payload

    def _audit(self, action: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> None:
        write_audit_log(self.db, action=action, entity_type=entity_type, entity_id=entity_id, payload_json={**payload, "execution_available": False}, actor_id="managed-auth")


class ProductionFoundationService:
    PILOT_GATES = ("legal", "limits", "monitoring", "rollback", "kill_switch", "allowlist", "operations")
    ACCEPTANCE_STAGES = (
        "real_data_verification",
        "research_evidence",
        "auth_and_secrets",
        "production_operations",
        "commercial_loop",
        "broker_sandbox",
        "controlled_pilot",
        "release_quality",
    )
    RETENTION_POLICY_KEY = "production:data_retention_policy"
    RETENTION_CONFIRMATION = "DELETE_EXPIRED_OPERATIONAL_TELEMETRY"
    DEFAULT_RETENTION_POLICY = {
        "enabled": False,
        "observability_days": 90,
        "notification_delivery_days": 365,
        "audit_days": 2555,
        "audit_mode": "immutable_no_application_delete",
        "investment_data_mode": "retain_until_user_deletion_request",
    }

    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.secret_resolver = SecretManagerResolver(self.settings)

    def verify_secret_reference(self, *, user_id: str, reference: str, purpose: str) -> dict[str, Any]:
        try:
            verified = self.secret_resolver.verify(reference)
        except ValueError as exc:
            item = self.db.scalar(select(SecretReference).where(SecretReference.user_id == user_id, SecretReference.reference_key == reference).limit(1))
            if item is not None:
                item.status = "invalid"
                item.metadata_json = {
                    **(item.metadata_json or {}),
                    "last_verification_failed_at": now().isoformat(),
                    "last_verification_error_class": exc.__class__.__name__,
                    "contains_secret": False,
                }
                self._audit("secret_reference.verification_failed", "SecretReference", item.id, {"reference": reference, "purpose": purpose, "error_class": exc.__class__.__name__})
                self.db.commit()
            raise ProductionFoundationError("secret reference verification failed") from exc
        item = self.db.scalar(select(SecretReference).where(SecretReference.user_id == user_id, SecretReference.reference_key == reference).limit(1))
        if item is None:
            item = SecretReference(user_id=user_id, reference_key=reference, provider=verified["backend"], scope=purpose, storage_backend=verified["backend"], status="active", metadata_json={})
            self.db.add(item)
        item.last_verified_at = now()
        item.status = "active"
        item.metadata_json = {**item.metadata_json, "purpose": purpose, "version": verified.get("version"), "rotation_verified_at": now().isoformat(), "contains_secret": False}
        self.db.flush()
        self._audit("secret_reference.verified", "SecretReference", item.id, {"reference": reference, "backend": verified["backend"], "purpose": purpose})
        self.db.commit()
        return verified

    def readiness(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require(actor, "readiness:read")
        restore_drills = int(self.db.scalar(select(func.count()).select_from(OperationalEvent).where(OperationalEvent.event_type.like("%restore%"))) or 0)
        secret_refs = int(self.db.scalar(select(func.count()).select_from(SecretReference).where(SecretReference.user_id == actor.user_id, SecretReference.last_verified_at.is_not(None))) or 0)
        eval_cases = int(self.db.scalar(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.export_type == "research_eval_case")) or 0)
        eval_results = int(self.db.scalar(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.export_type == "research_eval_result")) or 0)
        retention_policy = self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key == self.RETENTION_POLICY_KEY).limit(1))
        checks = {
            "managed_auth_configured": bool(self.settings.managed_auth_required and self.settings.oidc_issuer and self.settings.oidc_userinfo_url and self.settings.auth_session_secret_ref),
            "secret_manager_verified": secret_refs > 0,
            "external_llm_allowlisted": bool(self.settings.external_llm_calls_enabled and self.settings.openai_api_key_ref and f"openai:{self.settings.openai_model}" in self.settings.llm_provider_allowlist),
            "long_term_eval_dataset": eval_cases > 0 and eval_results > 0,
            "monitoring_configured": bool(self.settings.error_reporting_enabled),
            "restore_drill_recorded": restore_drills > 0,
            "retention_policy_enabled": bool(retention_policy and (retention_policy.value_json or {}).get("enabled")),
            "sandbox_broker_configured": bool(self.settings.sandbox_broker_base_url and self.settings.sandbox_broker_token_ref),
        }
        blockers = [key for key, passed in checks.items() if not passed]
        return {
            "status": "ready_for_controlled_review" if not blockers else "blocked",
            "checks": checks,
            "blockers": blockers,
            "metrics": {"verified_secret_references": secret_refs, "eval_cases": eval_cases, "eval_results": eval_results, "restore_drills": restore_drills},
            "pilot": self.pilot_readiness(actor=actor),
            "production_execution_allowed": False,
            "generated_at": now(),
        }

    def acceptance_program(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        """Return the evidence-backed eight-stage path to a human pilot review."""
        self._require(actor, "readiness:read")
        supplemental = {
            item.config_key.removeprefix("acceptance_evidence:"): item.value_json
            for item in self.db.scalars(
                select(LocalUserConfig).where(
                    LocalUserConfig.user_id == actor.user_id,
                    LocalUserConfig.config_key.like("acceptance_evidence:%"),
                )
            ).all()
        }

        binance_connection = self.db.scalar(
            select(DataSourceConnection)
            .where(DataSourceConnection.provider == "binance_spot_readonly")
            .order_by(DataSourceConnection.created_at.desc(), DataSourceConnection.id.desc())
            .limit(1)
        )
        binance_artifact = self.db.scalar(
            select(ExportArtifact)
            .where(
                ExportArtifact.user_id == actor.user_id,
                ExportArtifact.export_type == "binance_readonly_private_evidence",
            )
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        binance_payload = binance_artifact.payload_json if binance_artifact else {}
        binance_proofs = binance_payload.get("proof_checks") or {}
        binance_snapshot_id = (binance_payload.get("sync_result") or {}).get("snapshot_id")
        binance_quality = self.db.scalar(
            select(DataQualityReport).where(DataQualityReport.data_snapshot_id == binance_snapshot_id).limit(1)
        ) if binance_snapshot_id else None

        verified_secret_refs = int(self.db.scalar(
            select(func.count()).select_from(SecretReference).where(
                SecretReference.user_id == actor.user_id,
                SecretReference.last_verified_at.is_not(None),
            )
        ) or 0)
        eval_cases = int(self.db.scalar(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.export_type == "research_eval_case")) or 0)
        eval_results = int(self.db.scalar(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.export_type == "research_eval_result")) or 0)
        active_users = int(self.db.scalar(select(func.count()).select_from(UserAccount).where(UserAccount.status == "active")) or 0)
        active_sessions = int(self.db.scalar(select(func.count()).select_from(LocalUserConfig).where(LocalUserConfig.config_key.like("auth_session:%"))) or 0)
        restore_drills = int(self.db.scalar(select(func.count()).select_from(OperationalEvent).where(OperationalEvent.event_type.like("%restore%"))) or 0)
        verified_ops_targets = int(self.db.scalar(
            select(func.count()).select_from(ProductionReadinessTarget).where(
                ProductionReadinessTarget.user_id == actor.user_id,
                ProductionReadinessTarget.required.is_(True),
                ProductionReadinessTarget.status == "verified",
            )
        ) or 0)
        invitations = int(self.db.scalar(select(func.count()).select_from(UserAccount).where(UserAccount.status == "invited")) or 0)
        activation_events = int(self.db.scalar(select(func.count()).select_from(OperationalEvent).where(OperationalEvent.event_type.like("activation.%"))) or 0)
        pricing = self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key == "pricing_admin").limit(1))
        data_rooms = int(self.db.scalar(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.user_id == actor.user_id, ExportArtifact.export_type == "permissioned_data_room")) or 0)
        sandbox_reconciliations = int(self.db.scalar(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.user_id == actor.user_id, ExportArtifact.export_type == "broker_sandbox_reconciliation", ExportArtifact.status == "reconciled")) or 0)
        retention_policy = self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key == self.RETENTION_POLICY_KEY).limit(1))
        pilot = self.pilot_readiness(actor=actor)

        raw_stages = [
            ("real_data_verification", "Real Binance Read-Only Verification", {
                "readonly_connection": bool(binance_connection and binance_connection.credentials_ref),
                "private_sync_snapshot": bool(binance_snapshot_id and self.db.get(DataSnapshot, binance_snapshot_id)),
                "quality_report": binance_quality is not None,
                "permission_screenshot": bool(binance_proofs.get("permission_screenshot_recorded")),
                "withdrawal_disabled_proof": bool(binance_proofs.get("withdrawal_disabled_proof_recorded")),
                "audit_packet": bool(binance_artifact and binance_artifact.status == "ready"),
            }, "Run the private Binance read-only verifier with a withdrawal-disabled key and retain the redacted packet."),
            ("research_evidence", "Allowlisted LLM And Long-Term Eval", {
                "external_llm_enabled": bool(self.settings.external_llm_calls_enabled),
                "model_allowlisted": f"openai:{self.settings.openai_model}" in self.settings.llm_provider_allowlist,
                "secret_reference_configured": bool(self.settings.openai_api_key_ref),
                "eval_cases_recorded": eval_cases > 0,
                "eval_results_recorded": eval_results > 0,
            }, "Run the structured-output eval suite against the allowlisted model and retain versioned results."),
            ("auth_and_secrets", "Managed Auth, RBAC And Secret Rotation", {
                "managed_auth_enforced": bool(self.settings.managed_auth_required),
                "oidc_configured": bool(self.settings.oidc_issuer and self.settings.oidc_userinfo_url and self.settings.oidc_client_id),
                "signed_sessions_configured": bool(self.settings.auth_session_secret_ref),
                "managed_identity_seen": active_users > 0 and active_sessions > 0,
                "secret_reference_verified": verified_secret_refs > 0,
            }, "Complete a managed OIDC login and secret rotation verification in the private environment."),
            ("production_operations", "Monitoring, SLO, Backup And Restore", {
                "error_reporting_enabled": bool(self.settings.error_reporting_enabled),
                "restore_drill_recorded": restore_drills > 0,
                "required_ops_target_verified": verified_ops_targets > 0,
                "retention_policy_enabled": bool(retention_policy and (retention_policy.value_json or {}).get("enabled")),
            }, "Verify monitoring targets and attach a successful backup/restore drill to the release record."),
            ("commercial_loop", "Invitation, Activation, Pricing And Data Room", {
                "invitation_recorded": invitations > 0,
                "activation_event_recorded": activation_events > 0,
                "pricing_configured": pricing is not None,
                "permissioned_data_room": data_rooms > 0,
            }, "Complete an invitation-to-activation rehearsal and verify data-room download authorization."),
            ("broker_sandbox", "Broker Sandbox And Ledger Reconciliation", {
                "sandbox_endpoint_configured": bool(self.settings.sandbox_broker_base_url),
                "sandbox_secret_reference": bool(self.settings.sandbox_broker_token_ref),
                "broker_ledger_reconciled": sandbox_reconciliations > 0,
            }, "Submit one approved draft to a real broker sandbox and reconcile broker state to the ledger."),
            ("controlled_pilot", "Controlled Pilot Evidence Gates", dict(pilot["gates"]), "Verify every legal and operational gate, then request a separate human go/no-go review."),
            ("release_quality", "Cross-Browser, Failure-Path And Release Quality", {
                "cross_browser_evidence": bool(supplemental.get("release_quality", {}).get("cross_browser_verified")),
                "failure_path_evidence": bool(supplemental.get("release_quality", {}).get("failure_paths_verified")),
                "accessibility_evidence": bool(supplemental.get("release_quality", {}).get("accessibility_verified")),
                "visual_regression_evidence": bool(supplemental.get("release_quality", {}).get("visual_regression_verified")),
            }, "Run the CI release-quality suite and record its immutable artifact reference."),
        ]

        stages = []
        for index, (key, title, checks, next_action) in enumerate(raw_stages, start=1):
            passed = sum(1 for value in checks.values() if value)
            total = len(checks)
            status = "verified" if passed == total else "in_progress" if passed else "blocked"
            stages.append({
                "stage_no": index,
                "key": key,
                "title": title,
                "status": status,
                "progress_pct": round(passed / total * 100) if total else 0,
                "checks": checks,
                "blockers": [name for name, value in checks.items() if not value],
                "next_action": next_action,
                "supplemental_evidence": supplemental.get(key),
            })
        verified = sum(1 for stage in stages if stage["status"] == "verified")
        current = next((stage for stage in stages if stage["status"] != "verified"), None)
        return {
            "status": "ready_for_human_small_pilot_review" if verified == len(stages) else "blocked",
            "overall_progress_pct": round(sum(stage["progress_pct"] for stage in stages) / len(stages)),
            "verified_stages": verified,
            "total_stages": len(stages),
            "current_stage": current,
            "stages": stages,
            "human_small_pilot_review_allowed": verified == len(stages) and bool(pilot["all_evidence_verified"]),
            "pilot_approved": False,
            "production_execution_allowed": False,
            "generated_at": now(),
        }

    def external_evidence_packet(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require(actor, "readiness:read")
        acceptance = self.acceptance_program(actor=actor)
        readiness = self.readiness(actor=actor)
        stages = acceptance["stages"]
        missing = [
            {
                "stage_key": stage["key"],
                "stage_no": stage["stage_no"],
                "title": stage["title"],
                "blockers": stage["blockers"],
                "next_action": stage["next_action"],
            }
            for stage in stages
            if stage["blockers"]
        ]
        packet = {
            "packet_type": "production_external_evidence_packet",
            "user_id": actor.user_id,
            "generated_at": now().isoformat(),
            "status": acceptance["status"],
            "overall_progress_pct": acceptance["overall_progress_pct"],
            "verified_stages": acceptance["verified_stages"],
            "total_stages": acceptance["total_stages"],
            "current_stage": acceptance["current_stage"],
            "stages": stages,
            "missing_evidence": missing,
            "readiness_checks": readiness["checks"],
            "readiness_blockers": readiness["blockers"],
            "pilot": acceptance.get("pilot") or readiness.get("pilot"),
            "human_small_pilot_review_allowed": acceptance["human_small_pilot_review_allowed"],
            "pilot_approved": False,
            "contains_secrets": False,
            "external_evidence_required": True,
            "production_execution_allowed": False,
            "safe_boundaries": [
                "不会自动实盘",
                "不会 wallet signing",
                "不会 withdrawal",
                "不会 DEX swap",
                "不会自动审批",
                "不会绕过 gates",
                "预检、模拟、说明文档或本地 UI 不能替代真实外部实证",
            ],
        }
        artifact = ExportArtifact(
            user_id=actor.user_id,
            export_type="production_external_evidence_packet",
            format="json",
            status=acceptance["status"],
            payload_json=packet,
            summary_json={
                "overall_progress_pct": acceptance["overall_progress_pct"],
                "verified_stages": acceptance["verified_stages"],
                "total_stages": acceptance["total_stages"],
                "missing_evidence_count": len(missing),
                "contains_secrets": False,
                "production_execution_allowed": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        artifact.payload_json = packet
        self._audit("production_acceptance.external_evidence_packet_created", "ExportArtifact", artifact.id, artifact.summary_json)
        self.db.commit()
        return packet

    def record_acceptance_evidence(self, *, actor: AuthenticatedUser, stage_key: str, evidence: dict[str, Any]) -> dict[str, Any]:
        self._require(actor, "readiness:write")
        if stage_key not in self.ACCEPTANCE_STAGES:
            raise ProductionFoundationError("unsupported acceptance stage")
        if contains_secret_config_key(evidence):
            raise ProductionFoundationError("acceptance evidence must not contain secrets")
        required = {"artifact_ref", "reviewer", "verified_at"}
        if not required.issubset(evidence) or not all(evidence.get(key) for key in required):
            raise ProductionFoundationError("acceptance evidence requires artifact_ref, reviewer, and verified_at")
        item = self._upsert_config(actor.user_id, f"acceptance_evidence:{stage_key}", {
            **evidence,
            "stage_key": stage_key,
            "supplemental_only": True,
            "production_execution_allowed": False,
        })
        self._audit("production_acceptance.evidence_recorded", "LocalUserConfig", item.id, {"stage_key": stage_key, "reviewer": evidence["reviewer"]})
        self.db.commit()
        return item.value_json

    def record_invitation(self, *, actor: AuthenticatedUser, invitee_id: str, role: str = "viewer") -> dict[str, Any]:
        self._require(actor, "users:write")
        if not invitee_id.strip():
            raise ProductionFoundationError("invitee_id is required")
        if role not in ROLE_PERMISSIONS:
            raise ProductionFoundationError("unsupported invite role")
        code = secrets.token_urlsafe(24)
        user = self.db.scalar(select(UserAccount).where(UserAccount.user_id == invitee_id).limit(1))
        if user is None:
            user = UserAccount(user_id=invitee_id, display_name=invitee_id, role=role, status="invited", permissions_json=ROLE_PERMISSIONS[role], onboarding_state_json={})
            self.db.add(user)
            self.db.flush()
        issued_at = now()
        expires_at = issued_at + timedelta(hours=max(1, self.settings.invitation_ttl_hours))
        user.role = role
        user.permissions_json = ROLE_PERMISSIONS[role]
        user.status = "invited"
        user.onboarding_state_json = {
            **user.onboarding_state_json,
            "invite_code_sha256": hashlib.sha256(code.encode()).hexdigest(),
            "invited_at": issued_at.isoformat(),
            "invite_expires_at": expires_at.isoformat(),
            "invite_attempts": 0,
            "invited_by": actor.user_id,
            "accepted_at": None,
            "revoked_at": None,
        }
        self._audit("traction.invite_created", "UserAccount", user.id, {"invitee_id": invitee_id, "role": role})
        self.db.commit()
        return {"invitee_id": invitee_id, "role": role, "status": "invited", "invite_code": code, "shown_once": True, "expires_at": expires_at}

    def invitation_status(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        user = self.db.scalar(select(UserAccount).where(UserAccount.user_id == actor.user_id).limit(1))
        if user is None:
            return {"user_id": actor.user_id, "status": "not_invited", "onboarding_required": False}
        state = dict(user.onboarding_state_json or {})
        return {
            "user_id": user.user_id,
            "role": user.role,
            "status": user.status,
            "expires_at": state.get("invite_expires_at"),
            "onboarding_required": user.status == "invited",
            "accepted_at": state.get("accepted_at"),
        }

    def list_invitations(self, *, actor: AuthenticatedUser, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        self._require(actor, "users:read")
        if actor.role not in {"owner", "admin", "operator"}:
            raise ProductionFoundationError("invitation queue requires an operator role")
        allowed_statuses = {"invited", "active", "expired", "revoked"}
        if status and status not in allowed_statuses:
            raise ProductionFoundationError("unsupported invitation status")
        rows = list(
            self.db.scalars(
                select(UserAccount)
                .where(UserAccount.status.in_(allowed_statuses))
                .order_by(UserAccount.updated_at.desc(), UserAccount.id.desc())
                .limit(max(1, min(limit, 500)))
                .execution_options(tenant_scope_bypass=True)
            ).all()
        )
        items: list[dict[str, Any]] = []
        counts = {key: 0 for key in allowed_statuses}
        current_time = now()
        for user in rows:
            state = dict(user.onboarding_state_json or {})
            effective_status = user.status
            expires_raw = state.get("invite_expires_at")
            if effective_status == "invited" and expires_raw:
                try:
                    if datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00")) <= current_time:
                        effective_status = "expired"
                except ValueError:
                    effective_status = "expired"
            counts[effective_status] += 1
            if status and effective_status != status:
                continue
            items.append({
                "invitee_id": user.user_id,
                "display_name": user.display_name,
                "role": user.role,
                "status": effective_status,
                "invited_at": state.get("invited_at"),
                "expires_at": expires_raw,
                "accepted_at": state.get("accepted_at"),
                "revoked_at": state.get("revoked_at"),
                "attempts": int(state.get("invite_attempts") or 0),
                "locked": bool(state.get("invite_locked_at")),
            })
        return {"items": items, "counts": counts, "total": sum(counts.values()), "raw_codes_included": False, "external_messages_sent": False}

    def accept_invitation(self, *, actor: AuthenticatedUser, code: str) -> dict[str, Any]:
        user = self.db.scalar(select(UserAccount).where(UserAccount.user_id == actor.user_id).limit(1))
        if user is None or user.status != "invited":
            raise ProductionFoundationError("active invitation not found")
        state = dict(user.onboarding_state_json or {})
        expected = str(state.get("invite_code_sha256") or "")
        expires_raw = str(state.get("invite_expires_at") or "")
        attempts = int(state.get("invite_attempts") or 0)
        max_attempts = max(1, self.settings.invitation_max_attempts)
        try:
            expires_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProductionFoundationError("invitation is invalid") from exc
        if expires_at <= now():
            user.status = "expired"
            user.onboarding_state_json = {**state, "invite_code_sha256": None, "expired_at": now().isoformat()}
            self._audit("traction.invite_expired", "UserAccount", user.id, {"invitee_id": user.user_id})
            self.db.commit()
            raise ProductionFoundationError("invitation has expired")
        if attempts >= max_attempts:
            raise ProductionFoundationError("invitation is locked")
        supplied = hashlib.sha256(code.strip().encode()).hexdigest()
        if not expected or not hmac.compare_digest(expected, supplied):
            attempts += 1
            locked = attempts >= max_attempts
            user.onboarding_state_json = {**state, "invite_attempts": attempts, "invite_locked_at": now().isoformat() if locked else None}
            self._audit("traction.invite_accept_failed", "UserAccount", user.id, {"invitee_id": user.user_id, "attempts": attempts, "locked": locked})
            self.db.commit()
            raise ProductionFoundationError("invitation code is invalid or locked")
        accepted_at = now()
        user.status = "active"
        user.onboarding_state_json = {
            **state,
            "invite_code_sha256": None,
            "accepted_at": accepted_at.isoformat(),
            "invite_attempts": attempts,
            "invite_locked_at": None,
        }
        self.db.add(OperationalEvent(user_id=user.user_id, event_type="activation.invite_accepted", severity="info", source="traction", message="Invitation accepted", status="closed", payload_json={"verified_business_event": True, "execution_available": False}))
        self._audit("traction.invite_accepted", "UserAccount", user.id, {"invitee_id": user.user_id, "role": user.role})
        self.db.commit()
        return {**self.invitation_status(actor=actor), "next_route": "/settings", "execution_available": False}

    def revoke_invitation(self, *, actor: AuthenticatedUser, invitee_id: str) -> dict[str, Any]:
        self._require(actor, "users:write")
        user = self.db.scalar(select(UserAccount).where(UserAccount.user_id == invitee_id).limit(1))
        if user is None or user.status != "invited":
            raise ProductionFoundationError("active invitation not found")
        state = dict(user.onboarding_state_json or {})
        user.status = "revoked"
        user.onboarding_state_json = {**state, "invite_code_sha256": None, "revoked_at": now().isoformat(), "revoked_by": actor.user_id}
        self._audit("traction.invite_revoked", "UserAccount", user.id, {"invitee_id": invitee_id})
        self.db.commit()
        return {"invitee_id": invitee_id, "status": "revoked", "execution_available": False}

    def record_activation(self, *, actor: AuthenticatedUser, event_name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = {"invite_accepted", "onboarding_completed", "daily_open", "first_drilldown", "first_thesis", "first_plan", "weekly_return"}
        if event_name not in allowed:
            raise ProductionFoundationError("unsupported activation event")
        metadata = metadata or {}
        if contains_secret_config_key(metadata):
            raise ProductionFoundationError("activation metadata must not contain secrets")
        event = OperationalEvent(user_id=actor.user_id, event_type=f"activation.{event_name}", severity="info", source="manual_activation", message=f"Supplemental activation note: {event_name}", status="closed", payload_json={**metadata, "verified_business_event": False, "supplemental_only": True})
        self.db.add(event)
        self.db.commit()
        return {"event_id": event.id, "event_name": event_name, "recorded_at": event.created_at, "verified_business_event": False, "supplemental_only": True}

    def activation_funnel(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require(actor, "users:read")
        rows = self.db.execute(
            select(OperationalEvent.event_type, func.count(func.distinct(OperationalEvent.user_id)))
            .where(OperationalEvent.event_type.like("activation.%"), OperationalEvent.source.in_(["traction", "daily_use"]))
            .group_by(OperationalEvent.event_type)
        ).all()
        counts = {str(key).removeprefix("activation."): int(count) for key, count in rows}
        return {"counts": counts, "counting_unit": "distinct_users_with_verified_business_events", "manual_events_excluded": True, "generated_at": now(), "execution_available": False}

    def set_pricing(self, *, actor: AuthenticatedUser, config: dict[str, Any]) -> dict[str, Any]:
        self._require(actor, "readiness:write")
        if contains_secret_config_key(config):
            raise ProductionFoundationError("pricing config must not contain secrets")
        item = self._upsert_config(actor.user_id, "pricing_admin", {**config, "billing_enabled": False, "updated_at": now().isoformat()})
        self._audit("traction.pricing_updated", "LocalUserConfig", item.id, {"billing_enabled": False})
        self.db.commit()
        return item.value_json

    def create_data_room(self, *, actor: AuthenticatedUser) -> ExportArtifact:
        self._require(actor, "readiness:write")
        artifact = ExportArtifact(
            user_id=actor.user_id,
            export_type="permissioned_data_room",
            format="json",
            status="ready",
            payload_json={"generated_at": now().isoformat(), "sections": ["architecture", "safety", "tests", "readiness", "evidence"], "redacted": True, "execution_available": False},
            summary_json={"owner_user_id": actor.user_id, "required_permission": "readiness:read"},
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        self._audit("traction.data_room_created", "ExportArtifact", artifact.id, {"user_id": actor.user_id})
        self.db.commit()
        return artifact

    def get_data_room(self, *, actor: AuthenticatedUser, artifact_id: str) -> dict[str, Any]:
        self._require(actor, "readiness:read")
        artifact = self.db.get(ExportArtifact, artifact_id)
        if artifact is None or artifact.export_type != "permissioned_data_room":
            raise ProductionFoundationError("data room artifact not found")
        if actor.role not in {"owner", "admin"} and artifact.user_id != actor.user_id:
            raise ProductionFoundationError("data room access denied")
        self._audit("traction.data_room_downloaded", "ExportArtifact", artifact.id, {"user_id": actor.user_id})
        self.db.commit()
        return {"id": artifact.id, "payload": artifact.payload_json, "summary": artifact.summary_json}

    def commercial_loop_rehearsal_packet(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require(actor, "readiness:write")
        invitee_id = f"local-beta-{secrets.token_hex(4)}"
        invitation = self.record_invitation(actor=actor, invitee_id=invitee_id, role="viewer")
        activation = self.record_activation(
            actor=actor,
            event_name="invite_accepted",
            metadata={"source": "commercial_loop_rehearsal", "execution_available": False},
        )
        pricing = self.set_pricing(
            actor=actor,
            config={
                "plan": "private_beta",
                "monthly_price": 49,
                "currency": "USD",
                "billing_provider": "stripe_sandbox_only",
                "usage_limits": {
                    "research_reports_per_month": 50,
                    "data_room_downloads_per_month": 10,
                    "workspace_users": 1,
                },
            },
        )
        data_room = self.create_data_room(actor=actor)
        downloaded = self.get_data_room(actor=actor, artifact_id=data_room.id)
        funnel = self.activation_funnel(actor=actor)
        redacted_invitation = {
            "invitee_id": invitation["invitee_id"],
            "role": invitation["role"],
            "status": invitation["status"],
            "shown_once": invitation["shown_once"],
            "invite_code_redacted": True,
        }
        packet = {
            "packet_type": "commercial_loop_rehearsal_packet",
            "user_id": actor.user_id,
            "generated_at": now().isoformat(),
            "packet_status": "ready_for_manual_review",
            "steps": [
                {"key": "invite_created", "status": "done", "evidence": redacted_invitation},
                {"key": "supplemental_activation_note_recorded", "status": "done", "evidence": activation},
                {"key": "pricing_configured", "status": "done", "evidence": pricing},
                {"key": "data_room_created", "status": "done", "evidence": {"artifact_id": data_room.id, "status": data_room.status}},
                {"key": "data_room_download_authorized", "status": "done", "evidence": {"artifact_id": downloaded["id"], "redacted": downloaded["payload"].get("redacted") is True}},
            ],
            "activation_funnel": funnel,
            "data_room_artifact_id": data_room.id,
            "contains_secrets": False,
            "email_sent": False,
            "stripe_live_billing_enabled": False,
            "billing_enabled": False,
            "external_user_access_granted": False,
            "execution_available": False,
            "production_execution_allowed": False,
            "safe_boundary": "Local commercial rehearsal only; no external email, no live Stripe charge, no production account access, no trading execution.",
            "next_actions": [
                "Replace this rehearsal with a real email provider dry-run before external beta invites.",
                "Connect Stripe Sandbox and verify plan entitlements before paid beta.",
                "Review data-room watermark, expiry, and download audit before sharing outside the local environment.",
            ],
        }
        packet = jsonable_encoder(packet)
        artifact = ExportArtifact(
            user_id=actor.user_id,
            export_type="commercial_loop_rehearsal_packet",
            format="json",
            status=packet["packet_status"],
            payload_json=packet,
            summary_json={
                "data_room_artifact_id": data_room.id,
                "contains_secrets": False,
                "email_sent": False,
                "stripe_live_billing_enabled": False,
                "execution_available": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        artifact.payload_json = packet
        self._audit("traction.commercial_loop_rehearsal_packet_created", "ExportArtifact", artifact.id, artifact.summary_json)
        self.db.commit()
        return packet

    def slo_report(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require(actor, "events:read")
        try:
            report = RedisRequestMetrics(self.settings).snapshot(window_hours=24)
        except ObservabilityUnavailable:
            report = {
                "status": "unavailable",
                "window_hours": 24,
                "reason": "request_metrics_store_unavailable",
                "sample_sufficient": False,
                "real_request_metrics": False,
            }
        return {**report, "execution_available": False}

    def retention_status(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require(actor, "readiness:read")
        record = self.db.scalar(
            select(LocalUserConfig).where(
                LocalUserConfig.user_id == actor.user_id,
                LocalUserConfig.config_key == self.RETENTION_POLICY_KEY,
            ).limit(1)
        )
        policy = {**self.DEFAULT_RETENTION_POLICY, **((record.value_json or {}) if record else {})}
        candidates = self._retention_candidates(actor.user_id, policy)
        return {
            "status": "configured" if record else "not_configured",
            "policy": policy,
            "preview": candidates,
            "destructive_action_requires_confirmation": True,
            "confirmation_phrase": self.RETENTION_CONFIRMATION,
            "protected_data": [
                "audit_logs",
                "investment_records",
                "account_snapshots",
                "ledger_and_reconciliation",
                "restore_and_acceptance_evidence",
                "activation_and_beta_metrics",
            ],
            "production_execution_allowed": False,
            "generated_at": now(),
        }

    def configure_retention(self, *, actor: AuthenticatedUser, payload: dict[str, Any]) -> dict[str, Any]:
        self._require(actor, "readiness:write")
        if contains_secret_config_key(payload):
            raise ProductionFoundationError("retention policy must not contain secrets")
        try:
            observability_days = int(payload.get("observability_days", 90))
            notification_days = int(payload.get("notification_delivery_days", 365))
            audit_days = int(payload.get("audit_days", 2555))
        except (TypeError, ValueError) as exc:
            raise ProductionFoundationError("retention periods must be whole days") from exc
        if not 30 <= observability_days <= 3650:
            raise ProductionFoundationError("observability retention must be between 30 and 3650 days")
        if not 365 <= notification_days <= 3650:
            raise ProductionFoundationError("notification delivery retention must be between 365 and 3650 days")
        if not 365 <= audit_days <= 3650:
            raise ProductionFoundationError("audit retention must be between 365 and 3650 days")
        policy = {
            "enabled": bool(payload.get("enabled", False)),
            "observability_days": observability_days,
            "notification_delivery_days": notification_days,
            "audit_days": audit_days,
            "audit_mode": "immutable_no_application_delete",
            "investment_data_mode": "retain_until_user_deletion_request",
            "configured_at": now().isoformat(),
            "configured_by": actor.user_id,
        }
        item = self._upsert_config(actor.user_id, self.RETENTION_POLICY_KEY, policy)
        self._audit(
            "production.retention_policy_configured",
            "LocalUserConfig",
            item.id,
            {
                "enabled": policy["enabled"],
                "observability_days": observability_days,
                "notification_delivery_days": notification_days,
                "audit_days": audit_days,
            },
        )
        self.db.commit()
        return self.retention_status(actor=actor)

    def apply_retention(self, *, actor: AuthenticatedUser, confirmation: str) -> dict[str, Any]:
        self._require(actor, "readiness:write")
        if confirmation != self.RETENTION_CONFIRMATION:
            raise ProductionFoundationError("exact retention confirmation phrase is required")
        record = self.db.scalar(
            select(LocalUserConfig).where(
                LocalUserConfig.user_id == actor.user_id,
                LocalUserConfig.config_key == self.RETENTION_POLICY_KEY,
            ).limit(1)
        )
        if record is None or not bool((record.value_json or {}).get("enabled")):
            raise ProductionFoundationError("retention policy must be configured and enabled")
        policy = {**self.DEFAULT_RETENTION_POLICY, **record.value_json}
        preview = self._retention_candidates(actor.user_id, policy)
        deleted = {}
        for category in ("observability", "notification_delivery"):
            ids = preview[category]["candidate_ids"]
            if ids:
                self.db.execute(delete(OperationalEvent).where(OperationalEvent.id.in_(ids)))
            deleted[category] = len(ids)
        run_at = now()
        record.value_json = {
            **record.value_json,
            "last_run_at": run_at.isoformat(),
            "last_run_deleted": deleted,
            "last_run_status": "completed",
        }
        self._audit(
            "production.retention_applied",
            "LocalUserConfig",
            record.id,
            {"deleted": deleted, "protected_data_deleted": False},
        )
        self.db.commit()
        return {
            "status": "completed",
            "deleted": deleted,
            "protected_data_deleted": False,
            "audit_logs_deleted": 0,
            "investment_records_deleted": 0,
            "completed_at": run_at,
        }

    def _retention_candidates(self, user_id: str, policy: dict[str, Any]) -> dict[str, Any]:
        categories = {
            "observability": {
                "days": int(policy["observability_days"]),
                "event_types": ("observability.slo_breached",),
                "terminal_statuses": ("resolved", "closed"),
            },
            "notification_delivery": {
                "days": int(policy["notification_delivery_days"]),
                "event_types": ("notification.webhook_delivery", "notification.webhook_test", "notification_dry_run"),
                "terminal_statuses": ("delivered", "resolved", "failed", "closed"),
            },
        }
        result: dict[str, Any] = {}
        for category, config in categories.items():
            cutoff = now() - timedelta(days=config["days"])
            ids = list(self.db.scalars(
                select(OperationalEvent.id).where(
                    OperationalEvent.user_id == user_id,
                    OperationalEvent.status.in_(config["terminal_statuses"]),
                    OperationalEvent.event_type.in_(config["event_types"]),
                    OperationalEvent.created_at < cutoff,
                ).order_by(OperationalEvent.created_at, OperationalEvent.id)
            ).all())
            result[category] = {
                "retention_days": config["days"],
                "cutoff": cutoff.isoformat(),
                "eligible_count": len(ids),
                "candidate_ids": ids,
            }
        result["total_eligible"] = sum(value["eligible_count"] for value in result.values())
        return result

    def record_pilot_evidence(self, *, actor: AuthenticatedUser, gate: str, evidence: dict[str, Any]) -> dict[str, Any]:
        self._require(actor, "readiness:write")
        if gate not in self.PILOT_GATES:
            raise ProductionFoundationError("unsupported pilot evidence gate")
        if contains_secret_config_key(evidence):
            raise ProductionFoundationError("pilot evidence must not contain secrets")
        required = {"artifact_ref", "reviewer", "verified_at"}
        if not required.issubset(evidence) or not all(evidence.get(key) for key in required):
            raise ProductionFoundationError("pilot evidence requires artifact_ref, reviewer, and verified_at")
        item = self._upsert_config(actor.user_id, f"pilot_evidence:{gate}", {**evidence, "gate": gate, "verified": True, "execution_available": False})
        self._audit("controlled_pilot.evidence_verified", "LocalUserConfig", item.id, {"gate": gate, "reviewer": evidence["reviewer"]})
        self.db.commit()
        return item.value_json

    def pilot_readiness(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require(actor, "readiness:read")
        records = {
            item.config_key.removeprefix("pilot_evidence:"): item.value_json
            for item in self.db.scalars(select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key.like("pilot_evidence:%"))).all()
        }
        checks = {gate: bool(records.get(gate, {}).get("verified")) for gate in self.PILOT_GATES}
        all_passed = all(checks.values())
        return {"gates": checks, "evidence": records, "all_evidence_verified": all_passed, "human_small_pilot_review_allowed": all_passed, "pilot_approved": False, "production_execution_allowed": False, "requires_separate_human_go_no_go": True}

    def _upsert_config(self, user_id: str, key: str, value: dict[str, Any]) -> LocalUserConfig:
        item = self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == key).limit(1))
        if item is None:
            item = LocalUserConfig(user_id=user_id, config_key=key, value_json=value, description="Production foundation configuration.")
            self.db.add(item)
        else:
            item.value_json = value
        self.db.flush()
        return item

    def _require(self, actor: AuthenticatedUser, permission: str) -> None:
        if permission not in actor.permissions:
            raise ProductionFoundationError(f"missing permission: {permission}")

    def _audit(self, action: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> None:
        write_audit_log(self.db, action=action, entity_type=entity_type, entity_id=entity_id, payload_json={**payload, "execution_available": False}, actor_id="production-foundation")


def now() -> datetime:
    return datetime.now(timezone.utc)
