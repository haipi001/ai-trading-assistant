from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.db.base import Base
from app.models import AuditLog
from app.models import ExportArtifact
from app.models import LocalUserConfig


class PrivacyCenterError(ValueError):
    pass


class PrivacyCenterService:
    POLICY_VERSION = "2026-07-17.private-beta.v1"
    REQUEST_KEY = "privacy:data_deletion_request"
    REQUEST_CONFIRMATION = "REQUEST_MY_DATA_DELETION"
    EXECUTE_CONFIRMATION = "PERMANENTLY_DELETE_MY_DATA"
    GRACE_DAYS = 7
    SENSITIVE_FRAGMENTS = (
        "secret",
        "token",
        "password",
        "credential",
        "authorization",
        "api_key",
        "private_key",
        "webhook",
        "session",
        "reference_key",
    )

    def __init__(self, db: Session):
        self.db = db

    def status(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require_self_service(actor)
        request = self._request_record(actor.user_id)
        request_value = request.value_json if request else {}
        return {
            "policy": self.disclosure(),
            "data_inventory": self._inventory(actor.user_id),
            "deletion": {
                "status": request_value.get("status", "not_requested"),
                "requested_at": request_value.get("requested_at"),
                "scheduled_for": request_value.get("scheduled_for"),
                "can_cancel": request_value.get("status") == "pending",
                "can_execute": self._can_execute(request_value),
                "grace_period_days": self.GRACE_DAYS,
                "nonce_returned": False,
                "requires_exact_confirmation": True,
            },
            "execution_available": False,
            "generated_at": self._now(),
        }

    def disclosure(self) -> dict[str, Any]:
        return {
            "policy_version": self.POLICY_VERSION,
            "product_stage": "private_beta_candidate",
            "data_categories": [
                "identity_and_access_metadata",
                "read_only_account_and_portfolio_data",
                "investment_theses_plans_and_reviews",
                "research_and_ai_evaluation_records",
                "product_usage_feedback_and_operations_events",
            ],
            "purposes": [
                "provide_the_personal_investment_workspace",
                "maintain_data_quality_security_and_auditability",
                "measure_private_beta_activation_and_workflow_completion",
            ],
            "never_required": [
                "exchange_withdrawal_permission",
                "wallet_private_keys_or_seed_phrases",
                "automatic_trade_approval",
            ],
            "rights": ["access", "portable_export", "deletion_request", "cancel_during_grace_period"],
            "retention_summary": {
                "investment_data": "until_user_deletion_request",
                "operational_telemetry": "configured_in_data_retention_policy",
                "audit_after_deletion": "pseudonymized_minimal_receipt_only",
            },
            "risk_disclosure": "AI output is research and decision-support material, not individualized investment advice or a promise of returns.",
            "legal_review_status": "requires_qualified_counsel_before_public_launch",
            "external_processors": "must_be_listed_from_the_actual_staging_or_production_provider_inventory",
            "production_execution_allowed": False,
        }

    def export(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require_self_service(actor)
        tables: dict[str, list[dict[str, Any]]] = {}
        omitted_security_records: dict[str, int] = {}
        for table in Base.metadata.sorted_tables:
            if "user_id" not in table.c:
                continue
            rows = list(self.db.execute(select(table).where(table.c.user_id == actor.user_id)).mappings())
            if not rows:
                continue
            exported: list[dict[str, Any]] = []
            omitted = 0
            for row in rows:
                if table.name == "local_user_configs" and str(row.get("config_key") or "").startswith("auth_session:"):
                    omitted += 1
                    continue
                if table.name == "export_artifacts":
                    exported.append({
                        "id": row.get("id"),
                        "export_type": row.get("export_type"),
                        "format": row.get("format"),
                        "status": row.get("status"),
                        "summary_json": self._redact(row.get("summary_json") or {}),
                        "created_at": row.get("created_at"),
                    })
                else:
                    exported.append(self._redact(dict(row)))
            if exported:
                tables[table.name] = jsonable_encoder(exported)
            if omitted:
                omitted_security_records[table.name] = omitted
        packet = {
            "packet_type": "user_data_portability_export",
            "policy_version": self.POLICY_VERSION,
            "generated_at": self._now().isoformat(),
            "user_id": actor.user_id,
            "tables": tables,
            "record_counts": {name: len(rows) for name, rows in tables.items()},
            "omitted_security_records": omitted_security_records,
            "redaction": {
                "secret_values_included": False,
                "session_records_included": False,
                "secret_references_hashed": True,
            },
            "execution_available": False,
        }
        artifact = ExportArtifact(
            user_id=actor.user_id,
            export_type="user_data_portability_export",
            format="json",
            status="ready",
            payload_json=packet,
            summary_json={
                "table_count": len(tables),
                "record_count": sum(len(rows) for rows in tables.values()),
                "contains_secret_values": False,
                "execution_available": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        artifact.payload_json = packet
        self._audit(
            user_id=actor.user_id,
            action="privacy.data_export_created",
            entity_type="ExportArtifact",
            entity_id=artifact.id,
            payload_json=artifact.summary_json,
            actor_id=actor.user_id,
        )
        self.db.commit()
        return packet

    def request_deletion(self, *, actor: AuthenticatedUser, confirmation: str) -> dict[str, Any]:
        self._require_self_service(actor)
        if confirmation != self.REQUEST_CONFIRMATION:
            raise PrivacyCenterError("exact deletion request confirmation phrase is required")
        record = self._request_record(actor.user_id)
        if record is not None and (record.value_json or {}).get("status") == "pending":
            raise PrivacyCenterError("a data deletion request is already pending")
        nonce = secrets.token_urlsafe(32)
        requested_at = self._now()
        value = {
            "status": "pending",
            "requested_at": requested_at.isoformat(),
            "scheduled_for": (requested_at + timedelta(days=self.GRACE_DAYS)).isoformat(),
            "nonce_sha256": hashlib.sha256(nonce.encode()).hexdigest(),
            "policy_version": self.POLICY_VERSION,
            "grace_period_days": self.GRACE_DAYS,
        }
        if record is None:
            record = LocalUserConfig(
                user_id=actor.user_id,
                config_key=self.REQUEST_KEY,
                value_json=value,
                description="Pending user data deletion request. Nonce is stored only as SHA-256.",
            )
            self.db.add(record)
        else:
            record.value_json = value
        self.db.flush()
        self._audit(
            user_id=actor.user_id,
            action="privacy.data_deletion_requested",
            entity_type="LocalUserConfig",
            entity_id=record.id,
            payload_json={"scheduled_for": value["scheduled_for"], "nonce_stored_raw": False},
            actor_id=actor.user_id,
        )
        self.db.commit()
        return {
            "status": "pending",
            "requested_at": value["requested_at"],
            "scheduled_for": value["scheduled_for"],
            "verification_nonce": nonce,
            "nonce_shown_once": True,
            "next_step": "store the nonce securely or cancel and create a new request",
        }

    def cancel_deletion(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._require_self_service(actor)
        record = self._request_record(actor.user_id)
        if record is None or (record.value_json or {}).get("status") != "pending":
            raise PrivacyCenterError("no pending data deletion request")
        record.value_json = {
            **record.value_json,
            "status": "cancelled",
            "cancelled_at": self._now().isoformat(),
            "nonce_sha256": None,
        }
        self._audit(
            user_id=actor.user_id,
            action="privacy.data_deletion_cancelled",
            entity_type="LocalUserConfig",
            entity_id=record.id,
            payload_json={"nonce_invalidated": True},
            actor_id=actor.user_id,
        )
        self.db.commit()
        return {"status": "cancelled", "nonce_invalidated": True}

    def execute_deletion(self, *, actor: AuthenticatedUser, confirmation: str, nonce: str) -> dict[str, Any]:
        self._require_self_service(actor)
        if confirmation != self.EXECUTE_CONFIRMATION:
            raise PrivacyCenterError("exact permanent deletion confirmation phrase is required")
        record = self._request_record(actor.user_id)
        value = record.value_json if record else {}
        if value.get("status") != "pending":
            raise PrivacyCenterError("no pending data deletion request")
        if not nonce or not secrets.compare_digest(hashlib.sha256(nonce.encode()).hexdigest(), str(value.get("nonce_sha256") or "")):
            raise PrivacyCenterError("deletion verification nonce is invalid")
        scheduled_for = self._parse_datetime(value.get("scheduled_for"))
        if scheduled_for is None or self._now() < scheduled_for:
            raise PrivacyCenterError("data deletion grace period has not elapsed")

        pseudonym = f"deleted-{secrets.token_hex(16)}"
        deleted_counts: dict[str, int] = {}
        for table in reversed(Base.metadata.sorted_tables):
            if "user_id" not in table.c or table.name == "audit_logs":
                continue
            result = self.db.execute(delete(table).where(table.c.user_id == actor.user_id))
            if result.rowcount:
                deleted_counts[table.name] = int(result.rowcount)
        self.db.execute(
            update(AuditLog)
            .where(AuditLog.user_id == actor.user_id)
            .values(user_id=pseudonym, actor_id=pseudonym, payload_json={"pseudonymized_after_user_deletion": True})
        )
        self.db.execute(
            insert(AuditLog).values(
                id=secrets.token_hex(18),
                user_id=pseudonym,
                actor_type="privacy-system",
                actor_id=pseudonym,
                action="privacy.data_deletion_completed",
                entity_type="UserAccount",
                entity_id=pseudonym,
                payload_json={
                    "deleted_table_count": len(deleted_counts),
                    "deleted_record_count": sum(deleted_counts.values()),
                    "audit_pseudonymized": True,
                    "secret_values_held_by_application": False,
                },
                created_at=self._now(),
            )
        )
        self.db.commit()
        return {
            "status": "completed",
            "deleted_table_count": len(deleted_counts),
            "deleted_record_count": sum(deleted_counts.values()),
            "audit_pseudonymized": True,
            "sessions_revoked": "local auth session records deleted",
            "external_secret_values_deleted": False,
            "external_secret_values_note": "The application stored references only; delete provider-side secrets separately if they are no longer needed.",
            "completed_at": self._now(),
        }

    def _inventory(self, user_id: str) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for table in Base.metadata.sorted_tables:
            if "user_id" not in table.c:
                continue
            count = int(self.db.scalar(select(func.count()).select_from(table).where(table.c.user_id == user_id)) or 0)
            if count:
                counts[table.name] = count
        return {
            "tables_with_data": len(counts),
            "records": sum(counts.values()),
            "counts": counts,
            "shared_market_reference_data_excluded": True,
        }

    def _redact(self, value: Any, *, key: str = "") -> Any:
        lowered = key.lower()
        if any(fragment in lowered for fragment in self.SENSITIVE_FRAGMENTS):
            if value in (None, "", [], {}):
                return value
            digest = hashlib.sha256(str(value).encode()).hexdigest()[:16]
            return {"redacted": True, "sha256_prefix": digest}
        if isinstance(value, dict):
            return {str(child_key): self._redact(child_value, key=str(child_key)) for child_key, child_value in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._redact(item, key=key) for item in value]
        return jsonable_encoder(value)

    def _request_record(self, user_id: str) -> LocalUserConfig | None:
        return self.db.scalar(
            select(LocalUserConfig).where(
                LocalUserConfig.user_id == user_id,
                LocalUserConfig.config_key == self.REQUEST_KEY,
            ).limit(1)
        )

    def _audit(self, *, user_id: str, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any], actor_id: str) -> None:
        self.db.add(AuditLog(
            user_id=user_id,
            actor_type="user",
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json,
        ))

    def _can_execute(self, value: dict[str, Any]) -> bool:
        scheduled = self._parse_datetime(value.get("scheduled_for"))
        return bool(value.get("status") == "pending" and scheduled and self._now() >= scheduled)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _require_self_service(actor: AuthenticatedUser) -> None:
        if "read" not in actor.permissions:
            raise PrivacyCenterError("authenticated self-service access is required")
