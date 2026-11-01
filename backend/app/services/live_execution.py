from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from decimal import InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Account
from app.models import Approval
from app.models import Asset
from app.models import AuditLog
from app.models import BrokerStateCheck
from app.models import Execution
from app.models import ExportArtifact
from app.models import KillSwitch
from app.models import LiveExecutionConfig
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import TradeJournalEntry
from app.services.automation_policy import LEVEL_RANK
from app.services.automation_policy import AutomationPolicyEngine


REQUIRED_EXECUTION_GATES = {"RESEARCH_GATE", "THESIS_GATE", "RISK_GATE", "BEHAVIOR_GATE", "EXECUTION_GATE"}
ZERO = Decimal("0")


class LiveExecutionError(ValueError):
    pass


class LiveExecutionNotFoundError(LiveExecutionError):
    pass


@dataclass(frozen=True)
class LiveExecutionContext:
    draft: OrderDraft
    intent: OrderIntent
    account: Account
    asset: Asset


class LiveExecutionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def list_configs(self, limit: int = 100) -> list[LiveExecutionConfig]:
        return list(
            self.db.scalars(
                select(LiveExecutionConfig)
                .order_by(LiveExecutionConfig.created_at.desc(), LiveExecutionConfig.id.desc())
                .limit(limit)
            ).all()
        )

    def create_config(self, *, user_id: str, exchange_type: str, api_key_ref: str, label: str) -> LiveExecutionConfig:
        config = LiveExecutionConfig(
            user_id=user_id,
            exchange_type=exchange_type.strip(),
            api_key_ref=api_key_ref.strip(),
            label=label.strip(),
            is_active=True,
        )
        self.db.add(config)
        self.db.flush()
        self._write_audit_log(
            action="live_execution_config.created",
            entity_type="LiveExecutionConfig",
            entity_id=config.id,
            payload_json={
                "user_id": config.user_id,
                "exchange_type": config.exchange_type,
                "api_key_ref": config.api_key_ref,
                "raw_secret_stored": False,
            },
        )
        self.db.commit()
        self.db.refresh(config)
        return config

    def disable_config(self, config_id: str) -> None:
        config = self.db.get(LiveExecutionConfig, config_id)
        if config is None:
            raise LiveExecutionNotFoundError("live execution config not found")
        config.is_active = False
        self._write_audit_log(
            action="live_execution_config.disabled",
            entity_type="LiveExecutionConfig",
            entity_id=config.id,
            payload_json={"raw_secret_stored": False},
        )
        self.db.commit()

    def broker_health_check(self, config_id: str) -> dict[str, Any]:
        config = self.db.get(LiveExecutionConfig, config_id)
        if config is None or not config.is_active:
            raise LiveExecutionNotFoundError("active live execution config not found")

        error = "No live execution adapter is configured; fail closed and perform no broker call."
        check = BrokerStateCheck(
            live_execution_config_id=config.id,
            status="blocked",
            connected=False,
            latency_ms=0,
            error=error,
            details_json={
                "adapter_mode": self.settings.live_execution_adapter_mode,
                "live_execution_enabled": self.settings.live_execution_enabled,
                "live_execution_dry_run_only": self.settings.live_execution_dry_run_only,
                "real_broker_call_performed": False,
            },
        )
        self.db.add(check)
        self.db.flush()
        self._write_audit_log(
            action="broker_state_check.fail_closed",
            entity_type="BrokerStateCheck",
            entity_id=check.id,
            payload_json=check.details_json | {"live_execution_config_id": config.id},
        )
        self.db.commit()
        return {"connected": False, "latency_ms": 0, "error": error}

    def prepare(self, order_draft_id: str) -> dict[str, Any]:
        context = self._context(order_draft_id)
        blocking_reasons: list[str] = []
        warnings: list[str] = []

        if not self.settings.live_trading_enabled:
            blocking_reasons.append("global_live_trading_disabled")
        if not self.settings.live_execution_enabled:
            blocking_reasons.append("live_execution_disabled")
        if self.settings.live_execution_adapter_mode == "disabled":
            blocking_reasons.append("live_execution_adapter_disabled")
        if self.settings.live_execution_dry_run_only:
            warnings.append("dry_run_only_mode")

        if context.account.mode != "live":
            blocking_reasons.append("account_not_live_mode")
        if not context.account.live_trading_enabled:
            blocking_reasons.append("account_live_trading_disabled")
        if context.draft.risk_status != "passed":
            blocking_reasons.append("risk_status_not_passed")
        if context.draft.behavior_status != "passed":
            blocking_reasons.append("behavior_status_not_passed")
        if context.draft.approval_status != "approved":
            blocking_reasons.append("draft_not_human_approved")
        if context.draft.execution_status in {"paper_filled", "paper_partially_filled", "live_filled", "live_blocked"}:
            blocking_reasons.append(f"draft_execution_status_{context.draft.execution_status}")

        missing_gates, failed_gates = self._gate_gaps(context.draft)
        if missing_gates:
            blocking_reasons.append(f"missing_gates:{','.join(missing_gates)}")
        if failed_gates:
            blocking_reasons.append(f"failed_gates:{','.join(failed_gates)}")

        kill_switch = KillSwitchService(self.db).check(context.account.id, context.asset.id)
        if kill_switch["blocked"]:
            blocking_reasons.append(f"kill_switch_active:{kill_switch['reason']}")

        broker_check = self._latest_broker_state_check()
        if broker_check is None or not broker_check.connected:
            blocking_reasons.append("broker_state_not_connected")

        policy_reasons = self._automation_policy_blockers(context)
        blocking_reasons.extend(policy_reasons)

        unique_blockers = dedupe(blocking_reasons)
        response = {
            "order_draft_id": context.draft.id,
            "order_intent_id": context.intent.id,
            "asset_id": context.asset.id,
            "draft_approval_status": context.draft.approval_status,
            "draft_execution_status": context.draft.execution_status,
            "passed": len(unique_blockers) == 0,
            "blocking_reasons": unique_blockers,
            "warnings": dedupe(warnings),
        }
        self._write_audit_log(
            action="live_execution.prepare_checked",
            entity_type="OrderDraft",
            entity_id=context.draft.id,
            payload_json=response | {"real_broker_call_performed": False},
        )
        self.db.commit()
        return response

    def approve(self, *, order_draft_id: str, approver_id: str, decision_reason: str | None = None) -> dict[str, Any]:
        readiness = self.prepare(order_draft_id)
        if not readiness["passed"]:
            self._write_audit_log(
                action="live_execution.approval_blocked",
                entity_type="OrderDraft",
                entity_id=order_draft_id,
                payload_json={
                    "approver_id": approver_id,
                    "decision_reason": decision_reason,
                    "blocking_reasons": readiness["blocking_reasons"],
                    "real_broker_call_performed": False,
                },
            )
            self.db.commit()
            return {"approved": False, "details": readiness}

        approval = Approval(
            order_draft_id=order_draft_id,
            status="live_approved",
            approver_id=approver_id,
            decision_reason=decision_reason,
            decided_at=datetime.now(timezone.utc),
        )
        self.db.add(approval)
        self.db.flush()
        self._write_audit_log(
            action="live_execution.approved",
            entity_type="Approval",
            entity_id=approval.id,
            payload_json={
                "order_draft_id": order_draft_id,
                "approver_id": approver_id,
                "real_broker_call_performed": False,
            },
        )
        self.db.commit()
        return {"approved": True, "details": readiness | {"approval_id": approval.id}}

    def execute(
        self,
        *,
        order_draft_id: str,
        approver_id: str,
        decision_reason: str | None = None,
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        context = self._context(order_draft_id)
        readiness = self.prepare(order_draft_id)
        blocking_reasons = list(readiness["blocking_reasons"])
        if self.settings.live_execution_dry_run_only:
            blocking_reasons.append("dry_run_only_mode")
        blocking_reasons.append("real_live_execution_not_implemented")
        blocking_reasons = dedupe(blocking_reasons)

        fill_price, price_error = self._requested_price(context.intent, force_fill_price)
        if price_error:
            blocking_reasons.append(price_error)
        requested_quantity = self._requested_quantity(context.intent, fill_price)
        rollback_plan = self._rollback_plan(context, blocking_reasons)

        execution = Execution(
            order_draft_id=context.draft.id,
            execution_mode="live",
            status="blocked",
            filled_quantity=ZERO,
            average_fill_price=fill_price if fill_price > ZERO else None,
            fill_notional=ZERO,
            fee_amount=ZERO,
            slippage_amount=ZERO,
            cash_effect=ZERO,
            requested_quantity=requested_quantity,
            cumulative_filled_quantity=ZERO,
            remaining_quantity=requested_quantity,
            proceeds_amount=ZERO,
            cost_basis_amount=ZERO,
            realized_pnl=ZERO,
        )
        self.db.add(execution)
        context.draft.execution_status = "live_blocked"
        self.db.flush()

        journal_entry = TradeJournalEntry(
            asset_id=context.asset.id,
            account_id=context.account.id,
            title=f"Blocked live execution {context.asset.symbol}",
            notes="\n".join(
                [
                    "Live execution request blocked before broker submission.",
                    "Real broker call performed: false.",
                    f"Blocking reasons: {', '.join(blocking_reasons)}",
                    f"Decision reason: {decision_reason or 'not provided'}",
                    "Rollback plan: no external order exists; keep draft blocked, review blockers, and re-run broker state checks before any retry.",
                ]
            ),
            tags_json=["live_execution_blocked", "no_live_broker_call", "rollback_plan"],
        )
        self.db.add(journal_entry)
        self.db.flush()

        self._write_audit_log(
            action="live_execution.blocked",
            entity_type="Execution",
            entity_id=execution.id,
            payload_json={
                "order_draft_id": context.draft.id,
                "approver_id": approver_id,
                "decision_reason": decision_reason,
                "blocking_reasons": blocking_reasons,
                "rollback_plan": rollback_plan,
                "real_broker_call_performed": False,
                "external_order_id": None,
                "position_updated": False,
                "cash_updated": False,
            },
        )
        self._write_audit_log(
            action="trade_journal.created_from_live_execution_blocked",
            entity_type="TradeJournalEntry",
            entity_id=journal_entry.id,
            payload_json={"execution_id": execution.id, "order_draft_id": context.draft.id},
        )
        self.db.commit()
        self.db.refresh(execution)
        self.db.refresh(context.draft)
        return {
            "order_draft_id": context.draft.id,
            "execution_id": execution.id,
            "status": execution.status,
            "filled_quantity": format_decimal(ZERO),
            "fill_price": format_decimal(fill_price),
            "blocking_reasons": blocking_reasons,
            "rollback_plan": rollback_plan,
        }

    def sandbox_run(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "sandbox-user",
        decision_reason: str | None = None,
        force_fill_price: str | None = None,
        scenario_label: str = "controlled_live_sandbox",
    ) -> dict[str, Any]:
        context = self._context(order_draft_id)
        readiness = self.prepare(order_draft_id)
        blocking_reasons = list(readiness["blocking_reasons"])
        fill_price, price_error = self._requested_price(context.intent, force_fill_price)
        if price_error:
            blocking_reasons.append(price_error)
        blocking_reasons = dedupe(blocking_reasons)
        requested_quantity = self._requested_quantity(context.intent, fill_price)
        rollback_plan = self._rollback_plan(context, blocking_reasons)
        status = "blocked" if blocking_reasons else "ready_for_dry_run"
        response = {
            "order_draft_id": context.draft.id,
            "order_intent_id": context.intent.id,
            "status": status,
            "sandbox_only": True,
            "execution_available": False,
            "real_broker_call_performed": False,
            "blocking_reasons": blocking_reasons,
            "warnings": readiness["warnings"],
            "readiness": readiness,
            "requested_order": {
                "asset_id": context.asset.id,
                "asset_symbol": context.asset.symbol,
                "account_id": context.account.id,
                "side": context.intent.side,
                "order_type": context.intent.order_type,
                "requested_quantity": format_decimal(requested_quantity),
                "requested_price": format_decimal(fill_price),
                "notional": format_decimal(to_decimal(context.intent.notional)),
                "scenario_label": scenario_label,
            },
            "broker_submission": {
                "status": "not_submitted",
                "external_order_id": None,
                "adapter_mode": self.settings.live_execution_adapter_mode,
                "dry_run_only": self.settings.live_execution_dry_run_only,
                "real_broker_call_performed": False,
            },
            "rollback_plan": rollback_plan,
        }
        self._write_audit_log(
            action="live_execution.sandbox_run",
            entity_type="OrderDraft",
            entity_id=context.draft.id,
            payload_json=response
            | {
                "approver_id": approver_id,
                "decision_reason": decision_reason,
                "draft_status_mutated": False,
                "execution_record_created": False,
            },
        )
        self.db.commit()
        return response

    def sandbox_certification(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "sandbox-certifier",
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        sandbox = self.sandbox_run(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            decision_reason="Sandbox certification preflight.",
            force_fill_price=force_fill_price,
            scenario_label="controlled_live_sandbox_certification",
        )
        blockers = list(sandbox["blocking_reasons"])
        if sandbox["broker_submission"]["status"] != "not_submitted":
            blockers.append("sandbox_must_not_submit_to_broker")
        if sandbox["real_broker_call_performed"]:
            blockers.append("sandbox_real_broker_call_detected")
        if not sandbox["rollback_plan"]:
            blockers.append("sandbox_rollback_plan_missing")
        status = "blocked" if blockers else "certified_dry_run_only"
        response = {
            "order_draft_id": order_draft_id,
            "status": status,
            "sandbox_status": sandbox["status"],
            "dry_run_only": True,
            "certification_level": "dry_run_only",
            "blockers": dedupe(blockers),
            "warnings": sandbox["warnings"],
            "rollback_plan": sandbox["rollback_plan"],
            "requested_order": sandbox["requested_order"],
            "broker_submission": sandbox["broker_submission"],
            "execution_available": False,
            "real_broker_call_allowed": False,
            "real_broker_call_performed": False,
            "external_order_id": None,
        }
        self._write_audit_log(
            action="live_execution.sandbox_certification_checked",
            entity_type="OrderDraft",
            entity_id=order_draft_id,
            payload_json=response | {"approver_id": approver_id},
        )
        self.db.commit()
        return response

    def sandbox_drill_report(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "sandbox-drill-reviewer",
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        certification = self.sandbox_certification(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            force_fill_price=force_fill_price,
        )
        scenarios = [
            {
                "key": "broker_disconnected",
                "expected_result": "blocked_before_submission",
                "covered": "broker_state_not_connected" in certification["blockers"],
            },
            {
                "key": "dry_run_only",
                "expected_result": "not_submitted",
                "covered": certification["broker_submission"]["status"] == "not_submitted",
            },
            {
                "key": "rollback_plan",
                "expected_result": "manual_no_external_order_rollback",
                "covered": bool(certification["rollback_plan"]),
            },
        ]
        blockers = list(certification["blockers"])
        if not all(item["covered"] for item in scenarios):
            blockers.append("sandbox_drill_scenario_coverage_incomplete")
        status = "blocked" if blockers else "drill_recorded"
        response = {
            "order_draft_id": order_draft_id,
            "drill_status": status,
            "sandbox_certification": certification,
            "scenarios": scenarios,
            "blockers": dedupe(blockers),
            "next_actions": [
                "Record this dry-run drill before any future sandbox adapter certification.",
                "Repeat the drill after broker state, cancel, rollback, or reconciliation code changes.",
            ],
            "execution_available": False,
            "real_broker_call_performed": False,
            "external_order_id": None,
        }
        self._write_audit_log(
            action="live_execution.sandbox_drill_reported",
            entity_type="OrderDraft",
            entity_id=order_draft_id,
            payload_json=response | {"approver_id": approver_id},
        )
        self.db.commit()
        return response

    def small_pilot_readiness(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "pilot-reviewer",
        max_notional: str = "100",
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        context = self._context(order_draft_id)
        readiness = self.prepare(order_draft_id)
        fill_price, price_error = self._requested_price(context.intent, force_fill_price)
        requested_quantity = self._requested_quantity(context.intent, fill_price)
        estimated_notional = self._estimated_notional(context.intent, requested_quantity, fill_price)
        max_notional_decimal, max_error = parse_positive_decimal(max_notional, "invalid_max_notional")
        checks = [
            self._pilot_size_check(estimated_notional, max_notional_decimal, max_error),
            self._pilot_human_approval_check(context),
            self._pilot_live_readiness_check(readiness, price_error),
            self._pilot_sandbox_boundary_check(),
            self._pilot_rollback_check(context),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        next_actions = dedupe([action for check in checks for action in check["next_actions"]])
        if any(check["status"] == "block" for check in checks):
            pilot_status = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            pilot_status = "review_required"
        else:
            pilot_status = "ready_for_manual_approval"
        rollback_plan = self._rollback_plan(context, blockers)
        response = {
            "order_draft_id": context.draft.id,
            "order_intent_id": context.intent.id,
            "pilot_status": pilot_status,
            "max_notional": format_decimal(max_notional_decimal),
            "estimated_notional": format_decimal(estimated_notional),
            "execution_available": False,
            "real_broker_call_allowed": False,
            "blockers": blockers,
            "next_actions": next_actions,
            "readiness": readiness,
            "rollback_plan": rollback_plan,
            "checks": checks,
        }
        self._write_audit_log(
            action="live_execution.small_pilot_readiness_checked",
            entity_type="OrderDraft",
            entity_id=context.draft.id,
            payload_json=response
            | {
                "approver_id": approver_id,
                "draft_status_mutated": False,
                "execution_record_created": False,
                "real_broker_call_performed": False,
            },
        )
        self.db.commit()
        return response

    def small_pilot_approval_packet(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "pilot-reviewer",
        max_notional: str = "100",
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        readiness = self.small_pilot_readiness(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            max_notional=max_notional,
            force_fill_price=force_fill_price,
        )
        sandbox = self.sandbox_certification(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            force_fill_price=force_fill_price,
        )
        blockers = dedupe(list(readiness["blockers"]) + list(sandbox["blockers"]))
        status = "blocked" if blockers else "ready_for_manual_packet_review"
        packet = {
            "order_draft_id": order_draft_id,
            "order_intent_id": readiness["order_intent_id"],
            "packet_status": status,
            "approver_id": approver_id,
            "max_notional": readiness["max_notional"],
            "estimated_notional": readiness["estimated_notional"],
            "unsigned_packet": True,
            "requires_human_signature": True,
            "signature_available": False,
            "broker_submission_status": "not_submitted",
            "external_order_id": None,
            "execution_available": False,
            "real_broker_call_allowed": False,
            "blockers": blockers,
            "next_actions": dedupe(list(readiness["next_actions"]) + sandbox["warnings"]),
            "readiness": readiness,
            "sandbox_certification": sandbox,
            "rollback_plan": readiness["rollback_plan"],
        }
        self._write_audit_log(
            action="live_execution.small_pilot_approval_packet_created",
            entity_type="OrderDraft",
            entity_id=order_draft_id,
            payload_json=packet,
        )
        self.db.commit()
        return packet

    def broker_reconciliation_plan(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "reconciliation-reviewer",
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        sandbox = self.sandbox_certification(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            force_fill_price=force_fill_price,
        )
        steps = [
            broker_reconciliation_step("external_order_state", "Capture external order state snapshot", sandbox["broker_submission"]["status"] == "not_submitted"),
            broker_reconciliation_step("idempotency_key", "Derive idempotency key before any future broker adapter call", True),
            broker_reconciliation_step("cancel_path", "Document cancel path before enabling adapter submission", bool(sandbox["rollback_plan"])),
            broker_reconciliation_step("ledger_match", "Require ledger reconciliation after sandbox or pilot evidence", False),
        ]
        blockers = list(sandbox["blockers"])
        if any(not step["covered"] for step in steps):
            blockers.append("broker_reconciliation_steps_incomplete")
        response = {
            "order_draft_id": order_draft_id,
            "plan_status": "blocked" if blockers else "ready_for_manual_reconciliation_review",
            "sandbox_certification": sandbox,
            "steps": steps,
            "blockers": dedupe(blockers),
            "next_actions": [
                "Implement broker order-state reconciliation before any real sandbox adapter submission.",
                "Keep external_order_id empty until a real sandbox broker explicitly returns one.",
            ],
            "execution_available": False,
            "real_broker_call_allowed": False,
            "external_order_id": None,
        }
        self._write_audit_log(
            action="live_execution.broker_reconciliation_plan_created",
            entity_type="OrderDraft",
            entity_id=order_draft_id,
            payload_json=response | {"approver_id": approver_id},
        )
        self.db.commit()
        return response

    def sandbox_proof_packet(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "sandbox-proof-reviewer",
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        drill = self.sandbox_drill_report(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            force_fill_price=force_fill_price,
        )
        reconciliation = self.broker_reconciliation_plan(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            force_fill_price=force_fill_price,
        )
        blockers = dedupe(list(drill["blockers"]) + list(reconciliation["blockers"]))
        status = "blocked" if blockers else "ready_for_manual_sandbox_review"
        packet = {
            "packet_type": "broker_sandbox_proof_packet",
            "order_draft_id": order_draft_id,
            "packet_status": status,
            "approver_id": approver_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "state_machine": [
                {"state": "draft_approved", "source": "OrderDraft.approval_status"},
                {"state": "prepare_checked", "source": "live_execution.prepare"},
                {"state": "sandbox_certified", "source": "live_execution.sandbox_certification"},
                {"state": "drill_recorded", "source": "live_execution.sandbox_drill_report"},
                {"state": "reconciliation_planned", "source": "live_execution.broker_reconciliation_plan"},
            ],
            "idempotency": {
                "required": True,
                "recommended_key": f"sandbox:{order_draft_id}:manual-review",
                "duplicate_request_policy": "return_existing_or_block_before_submission",
            },
            "sandbox_drill": drill,
            "broker_reconciliation": reconciliation,
            "blockers": blockers,
            "next_actions": dedupe(
                list(drill["next_actions"])
                + list(reconciliation["next_actions"])
                + [
                    "Keep this packet with the order draft before any future sandbox adapter submission.",
                    "Do not enter controlled pilot review until legal, limits, monitoring, rollback, and kill-switch evidence is complete.",
                ]
            ),
            "safe_boundary": "Sandbox proof only; no real broker submission, no wallet signing, no withdrawals, no DEX swaps, no automatic approval, no gate bypass.",
            "contains_secrets": False,
            "execution_available": False,
            "real_broker_call_allowed": False,
            "real_broker_call_performed": False,
            "production_execution_allowed": False,
            "external_order_id": None,
        }
        artifact = ExportArtifact(
            user_id=approver_id,
            export_type="broker_sandbox_proof_packet",
            format="json",
            status=status,
            payload_json=packet,
            summary_json={
                "order_draft_id": order_draft_id,
                "packet_status": status,
                "blockers": blockers,
                "execution_available": False,
                "real_broker_call_allowed": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        artifact.payload_json = packet
        self._write_audit_log(
            action="live_execution.broker_sandbox_proof_packet_created",
            entity_type="ExportArtifact",
            entity_id=artifact.id,
            payload_json=packet,
        )
        self.db.commit()
        return packet

    def small_pilot_go_no_go(
        self,
        *,
        order_draft_id: str,
        approver_id: str = "pilot-reviewer",
        max_notional: str = "100",
        force_fill_price: str | None = None,
    ) -> dict[str, Any]:
        packet = self.small_pilot_approval_packet(
            order_draft_id=order_draft_id,
            approver_id=approver_id,
            max_notional=max_notional,
            force_fill_price=force_fill_price,
        )
        decision = "NO_GO" if packet["blockers"] else "GO_FOR_MANUAL_SIGNATURE_ONLY"
        response = {
            "order_draft_id": order_draft_id,
            "decision": decision,
            "reason": "Blockers remain." if packet["blockers"] else "Manual signature packet is ready, but broker submission remains disabled.",
            "approval_packet": packet,
            "requires_human_signature": True,
            "signature_available": False,
            "broker_submission_status": "not_submitted",
            "execution_available": False,
            "real_broker_call_allowed": False,
            "external_order_id": None,
        }
        self._write_audit_log(
            action="live_execution.small_pilot_go_no_go_checked",
            entity_type="OrderDraft",
            entity_id=order_draft_id,
            payload_json=response | {"approver_id": approver_id},
        )
        self.db.commit()
        return response

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        executions = self.db.scalars(
            select(Execution)
            .where(Execution.execution_mode == "live")
            .order_by(Execution.created_at.desc(), Execution.id.desc())
            .limit(limit)
        ).all()
        entries: list[dict[str, Any]] = []
        for execution in executions:
            asset_id = ""
            draft = self.db.get(OrderDraft, execution.order_draft_id)
            intent = self.db.get(OrderIntent, draft.order_intent_id) if draft is not None else None
            if intent is not None:
                asset_id = intent.asset_id
            entries.append(
                {
                    "id": execution.id,
                    "order_draft_id": execution.order_draft_id,
                    "asset_id": asset_id,
                    "quantity": format_decimal(to_decimal(execution.requested_quantity)),
                    "price": format_decimal(to_decimal(execution.average_fill_price)),
                    "status": execution.status,
                    "created_at": execution.created_at,
                }
            )
        return entries

    def _context(self, order_draft_id: str) -> LiveExecutionContext:
        draft = self.db.get(OrderDraft, order_draft_id)
        if draft is None:
            raise LiveExecutionNotFoundError("order draft not found")
        intent = self.db.get(OrderIntent, draft.order_intent_id)
        if intent is None:
            raise LiveExecutionNotFoundError("order intent not found")
        account = self.db.get(Account, intent.account_id)
        asset = self.db.get(Asset, intent.asset_id)
        if account is None or asset is None:
            raise LiveExecutionNotFoundError("order draft account or asset not found")
        return LiveExecutionContext(draft=draft, intent=intent, account=account, asset=asset)

    def _latest_broker_state_check(self) -> BrokerStateCheck | None:
        return self.db.scalar(select(BrokerStateCheck).order_by(BrokerStateCheck.created_at.desc(), BrokerStateCheck.id.desc()).limit(1))

    def _gate_gaps(self, draft: OrderDraft) -> tuple[list[str], list[str]]:
        gate_results = draft.decision_gate_results or {}
        missing = sorted(REQUIRED_EXECUTION_GATES.difference(gate_results))
        failed = sorted(
            gate
            for gate, result in gate_results.items()
            if gate in REQUIRED_EXECUTION_GATES and isinstance(result, dict) and result.get("status") != "PASSED"
        )
        return missing, failed

    def _automation_policy_blockers(self, context: LiveExecutionContext) -> list[str]:
        policy = AutomationPolicyEngine(self.db).get_effective_policy(
            self.settings.beta_default_user_id,
            account_id=context.account.id,
            asset_id=context.asset.id,
            strategy_playbook_id=context.intent.strategy_playbook_id,
        )
        blockers: list[str] = []
        if LEVEL_RANK.get(policy.automation_level, -1) < LEVEL_RANK["A4_APPROVAL_EXECUTION"]:
            blockers.append("automation_policy_requires_a4_approval_execution")
        if "EXECUTE_LIVE" in policy.forbidden_actions or "LIVE_EXECUTION" in policy.forbidden_actions:
            blockers.append("live_execution_forbidden_by_policy")
        if policy.allowed_actions and "EXECUTE_LIVE" not in policy.allowed_actions:
            blockers.append("live_execution_not_allowed_by_policy")
        return blockers

    def _requested_price(self, intent: OrderIntent, force_fill_price: str | None = None) -> tuple[Decimal, str | None]:
        if force_fill_price:
            try:
                price = Decimal(str(force_fill_price))
            except (InvalidOperation, ValueError):
                return ZERO, "invalid_force_fill_price"
            if price <= ZERO:
                return ZERO, "invalid_force_fill_price"
            return price, None
        if intent.limit_price is not None:
            return to_decimal(intent.limit_price), None
        return ZERO, None

    def _requested_quantity(self, intent: OrderIntent, requested_price: Decimal) -> Decimal:
        quantity = to_decimal(intent.quantity)
        if quantity > ZERO:
            return quantity
        notional = to_decimal(intent.notional)
        if notional > ZERO and requested_price > ZERO:
            return notional / requested_price
        return ZERO

    def _estimated_notional(self, intent: OrderIntent, requested_quantity: Decimal, requested_price: Decimal) -> Decimal:
        notional = to_decimal(intent.notional)
        if notional > ZERO:
            return notional
        if requested_quantity > ZERO and requested_price > ZERO:
            return requested_quantity * requested_price
        return ZERO

    def _pilot_size_check(self, estimated_notional: Decimal, max_notional: Decimal, max_error: str | None) -> dict[str, Any]:
        if max_error:
            return pilot_check(
                "pilot_size",
                "Pilot notional limit",
                "block",
                "Pilot max_notional is invalid.",
                blockers=[max_error],
                next_actions=["Provide a positive max_notional for the pilot readiness check."],
                evidence={"estimated_notional": format_decimal(estimated_notional), "max_notional": format_decimal(max_notional)},
            )
        if estimated_notional <= ZERO:
            return pilot_check(
                "pilot_size",
                "Pilot notional limit",
                "block",
                "Estimated notional is unavailable or zero.",
                blockers=["pilot_estimated_notional_unavailable"],
                next_actions=["Provide notional, quantity plus force_fill_price, or a limit price before pilot review."],
                evidence={"estimated_notional": format_decimal(estimated_notional), "max_notional": format_decimal(max_notional)},
            )
        if estimated_notional > max_notional:
            return pilot_check(
                "pilot_size",
                "Pilot notional limit",
                "block",
                "Estimated notional exceeds the configured pilot limit.",
                blockers=["pilot_notional_exceeds_limit"],
                next_actions=["Reduce the draft size or raise the pilot limit only after explicit risk approval."],
                evidence={"estimated_notional": format_decimal(estimated_notional), "max_notional": format_decimal(max_notional)},
            )
        return pilot_check(
            "pilot_size",
            "Pilot notional limit",
            "ok",
            "Estimated notional is within the configured pilot limit.",
            evidence={"estimated_notional": format_decimal(estimated_notional), "max_notional": format_decimal(max_notional)},
        )

    def _pilot_human_approval_check(self, context: LiveExecutionContext) -> dict[str, Any]:
        if context.draft.approval_status == "approved":
            return pilot_check(
                "human_approval",
                "Human approval",
                "ok",
                "Draft has human approval recorded.",
                evidence={"approval_status": context.draft.approval_status},
            )
        return pilot_check(
            "human_approval",
            "Human approval",
            "block",
            f"Draft approval status is {context.draft.approval_status}.",
            blockers=["pilot_requires_approved_order_draft"],
            next_actions=["Approve or reject the order draft before pilot readiness can proceed."],
            evidence={"approval_status": context.draft.approval_status},
        )

    def _pilot_live_readiness_check(self, readiness: dict[str, Any], price_error: str | None) -> dict[str, Any]:
        blockers = list(readiness["blocking_reasons"])
        if price_error:
            blockers.append(price_error)
        blockers = dedupe(blockers)
        if blockers:
            return pilot_check(
                "live_readiness",
                "Live readiness",
                "block",
                "Live execution readiness has blocking reasons.",
                blockers=blockers,
                next_actions=["Resolve live readiness blockers, then rerun sandbox-run before any pilot approval."],
                evidence={"passed": readiness["passed"], "warnings": readiness["warnings"]},
            )
        if readiness["warnings"]:
            return pilot_check(
                "live_readiness",
                "Live readiness",
                "warn",
                "Live execution readiness has warnings.",
                next_actions=["Review readiness warnings before pilot approval."],
                evidence={"passed": readiness["passed"], "warnings": readiness["warnings"]},
            )
        return pilot_check("live_readiness", "Live readiness", "ok", "Live execution readiness passed.")

    def _pilot_sandbox_boundary_check(self) -> dict[str, Any]:
        return pilot_check(
            "sandbox_boundary",
            "Sandbox boundary",
            "ok",
            "Pilot readiness is a non-executing preflight and does not allow broker submission.",
            evidence={
                "execution_available": False,
                "real_broker_call_allowed": False,
                "live_execution_dry_run_only": self.settings.live_execution_dry_run_only,
            },
        )

    def _pilot_rollback_check(self, context: LiveExecutionContext) -> dict[str, Any]:
        return pilot_check(
            "rollback_plan",
            "Rollback plan",
            "ok",
            "Rollback plan is available and assumes no external order exists.",
            evidence={"order_draft_id": context.draft.id, "external_order_id": None},
        )

    def _rollback_plan(self, context: LiveExecutionContext, blocking_reasons: list[str]) -> dict[str, Any]:
        return {
            "external_order_id": None,
            "broker_cancel_required": False,
            "portfolio_reversal_required": False,
            "journal_entry_required": True,
            "next_steps": [
                "Confirm no broker/exchange order was submitted.",
                "Keep the order draft in live_blocked status.",
                "Resolve blocking reasons before retry.",
                "Run broker health and state checks again immediately before any future live attempt.",
            ],
            "blocking_reasons": blocking_reasons,
            "order_draft_id": context.draft.id,
            "asset_id": context.asset.id,
            "account_id": context.account.id,
        }

    def _write_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload_json: dict[str, Any],
    ) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="live-execution-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


class KillSwitchService:
    def __init__(self, db: Session):
        self.db = db

    def active(self) -> list[KillSwitch]:
        return list(
            self.db.scalars(
                select(KillSwitch)
                .where(KillSwitch.disengaged_at.is_(None))
                .order_by(KillSwitch.engaged_at.desc(), KillSwitch.id.desc())
            ).all()
        )

    def history(self, limit: int = 100) -> list[KillSwitch]:
        return list(
            self.db.scalars(
                select(KillSwitch).order_by(KillSwitch.engaged_at.desc(), KillSwitch.id.desc()).limit(limit)
            ).all()
        )

    def engage(
        self,
        *,
        reason: str,
        account_id: str | None = None,
        asset_id: str | None = None,
        engaged_by: str = "user",
    ) -> KillSwitch:
        if not reason.strip():
            raise LiveExecutionError("kill switch reason is required")
        switch = KillSwitch(
            reason=reason.strip(),
            account_id=account_id,
            asset_id=asset_id,
            engaged_by=engaged_by or "user",
        )
        self.db.add(switch)
        self.db.flush()
        self._write_audit_log(
            action="kill_switch.engaged",
            entity_type="KillSwitch",
            entity_id=switch.id,
            payload_json={
                "reason": switch.reason,
                "account_id": switch.account_id,
                "asset_id": switch.asset_id,
                "engaged_by": switch.engaged_by,
            },
        )
        self.db.commit()
        self.db.refresh(switch)
        return switch

    def disengage(
        self,
        *,
        account_id: str | None = None,
        asset_id: str | None = None,
        reason: str | None = None,
        disengaged_by: str = "user",
    ) -> bool:
        switches = [switch for switch in self.active() if self._same_scope(switch, account_id, asset_id)]
        if not switches:
            return False
        for switch in switches:
            switch.disengaged_at = datetime.now(timezone.utc)
            switch.disengage_reason = reason
            switch.disengaged_by = disengaged_by or "user"
            self._write_audit_log(
                action="kill_switch.disengaged",
                entity_type="KillSwitch",
                entity_id=switch.id,
                payload_json={
                    "reason": reason,
                    "account_id": switch.account_id,
                    "asset_id": switch.asset_id,
                    "disengaged_by": switch.disengaged_by,
                },
            )
        self.db.commit()
        return True

    def check(self, account_id: str | None = None, asset_id: str | None = None) -> dict[str, str | bool | None]:
        for switch in self.active():
            if self._blocks_scope(switch, account_id, asset_id):
                return {"blocked": True, "reason": switch.reason}
        return {"blocked": False, "reason": None}

    def _same_scope(self, switch: KillSwitch, account_id: str | None, asset_id: str | None) -> bool:
        return switch.account_id == account_id and switch.asset_id == asset_id

    def _blocks_scope(self, switch: KillSwitch, account_id: str | None, asset_id: str | None) -> bool:
        if switch.account_id is None and switch.asset_id is None:
            return True
        if switch.account_id is not None and switch.account_id == account_id:
            return True
        if switch.asset_id is not None and switch.asset_id == asset_id:
            return True
        return False

    def _write_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload_json: dict[str, Any],
    ) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="kill-switch-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


def to_decimal(value) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def parse_positive_decimal(value: str, error_code: str) -> tuple[Decimal, str | None]:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ZERO, error_code
    if parsed <= ZERO:
        return ZERO, error_code
    return parsed, None


def pilot_check(
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


def broker_reconciliation_step(key: str, label: str, covered: bool) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "covered": covered,
        "status": "ok" if covered else "block",
    }


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
