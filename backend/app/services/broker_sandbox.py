from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.broker_sandbox import HttpSandboxBrokerAdapter
from app.api.domain import write_audit_log
from app.core.auth import AuthenticatedUser
from app.models import ExportArtifact
from app.models import InvestmentLedgerEntry
from app.models import LocalUserConfig
from app.models import OrderDraft


class BrokerSandboxProofError(ValueError):
    pass


class BrokerSandboxProofService:
    def __init__(self, db: Session, *, adapter: HttpSandboxBrokerAdapter | None = None):
        self.db = db
        self.adapter = adapter

    def submit(self, *, actor: AuthenticatedUser, order_draft_id: str, idempotency_key: str) -> dict[str, Any]:
        if "trade:submit" not in actor.permissions:
            raise BrokerSandboxProofError("missing permission: trade:submit")
        self._operator(actor)
        draft = self.db.get(OrderDraft, order_draft_id)
        if draft is None:
            raise BrokerSandboxProofError("order draft not found")
        if draft.approval_status != "approved":
            raise BrokerSandboxProofError("sandbox submission requires an approved order draft")
        existing = self.db.scalar(
            select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key == f"sandbox_order:{idempotency_key}").limit(1)
        )
        if existing:
            return existing.value_json
        adapter = self.adapter or HttpSandboxBrokerAdapter()
        response = adapter.submit(
            {"client_order_id": order_draft_id, "order_draft_id": order_draft_id, "mode": "sandbox"},
            idempotency_key=idempotency_key,
        )
        external_order_id = str(response.get("id") or response.get("order_id") or "").strip()
        if not external_order_id:
            raise BrokerSandboxProofError("sandbox broker response is missing order id")
        value = {
            "order_draft_id": order_draft_id,
            "external_order_id": external_order_id,
            "idempotency_key": idempotency_key,
            "state": str(response.get("status") or "submitted_sandbox"),
            "sandbox": True,
            "production_execution_allowed": False,
            "submitted_at": now().isoformat(),
        }
        item = LocalUserConfig(user_id=actor.user_id, config_key=f"sandbox_order:{idempotency_key}", value_json=value, description="Sandbox broker order linkage.")
        self.db.add(item)
        self._audit("broker_sandbox.order_submitted", "OrderDraft", order_draft_id, value)
        self.db.commit()
        return value

    def reconcile(self, *, actor: AuthenticatedUser, idempotency_key: str) -> dict[str, Any]:
        self._operator(actor)
        item = self.db.scalar(
            select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key == f"sandbox_order:{idempotency_key}").limit(1)
        )
        if item is None:
            raise BrokerSandboxProofError("sandbox order linkage not found")
        adapter = self.adapter or HttpSandboxBrokerAdapter()
        broker = adapter.order(str(item.value_json["external_order_id"]))
        external_order_id = str(item.value_json["external_order_id"])
        ledger_quantity = float(
            self.db.scalar(
                select(func.coalesce(func.sum(InvestmentLedgerEntry.quantity_delta), 0)).where(
                    InvestmentLedgerEntry.user_id == actor.user_id,
                    InvestmentLedgerEntry.source_type == "broker_sandbox",
                    InvestmentLedgerEntry.source_id == external_order_id,
                )
            )
            or 0
        )
        broker_quantity = float(broker.get("filled_quantity") or broker.get("filled_qty") or 0)
        quantity_delta = round(broker_quantity - ledger_quantity, 10)
        state_match = str(broker.get("status") or "unknown") == str(item.value_json.get("state") or "unknown")
        status = "reconciled" if quantity_delta == 0 and state_match else "break_detected"
        packet = {
            "status": status,
            "order_draft_id": item.value_json["order_draft_id"],
            "external_order_id": external_order_id,
            "broker_state": broker.get("status"),
            "local_state": item.value_json.get("state"),
            "broker_filled_quantity": broker_quantity,
            "ledger_quantity": ledger_quantity,
            "quantity_delta": quantity_delta,
            "state_match": state_match,
            "auto_repair_performed": False,
            "production_execution_allowed": False,
            "checked_at": now().isoformat(),
        }
        artifact = ExportArtifact(user_id=actor.user_id, export_type="broker_sandbox_reconciliation", format="json", status=status, payload_json=packet, summary_json={"idempotency_key": idempotency_key}, file_path=None)
        self.db.add(artifact)
        self.db.flush()
        self._audit("broker_sandbox.reconciled", "ExportArtifact", artifact.id, packet)
        self.db.commit()
        return {**packet, "artifact_id": artifact.id}

    def _operator(self, actor: AuthenticatedUser) -> None:
        if actor.role not in {"owner", "admin", "operator"}:
            raise BrokerSandboxProofError("sandbox operations require owner, admin, or operator role")

    def _audit(self, action: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> None:
        write_audit_log(self.db, action=action, entity_type=entity_type, entity_id=entity_id, payload_json={**payload, "execution_available": False}, actor_id="broker-sandbox")


def now() -> datetime:
    return datetime.now(timezone.utc)
