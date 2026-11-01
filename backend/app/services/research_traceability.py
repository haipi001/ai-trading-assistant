from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import Account
from app.models import DecisionGate
from app.models import InvestmentThesis
from app.models import OrderIntent
from app.models import ResearchReport
from app.models import ThesisCheckpoint
from app.services.decision_gates import DecisionGateService


class ResearchTraceabilityError(ValueError):
    pass


class ResearchTraceabilityService:
    def __init__(self, db: Session):
        self.db = db

    def review_against_thesis(
        self,
        *,
        report_id: str,
        thesis_id: str,
        user_id: str,
        decision: str,
        human_summary: str,
        confidence: float,
    ) -> dict[str, Any]:
        if decision not in {"supports", "weakens", "invalidates"}:
            raise ResearchTraceabilityError("decision must be supports, weakens, or invalidates")
        summary = human_summary.strip()
        if len(summary) < 8:
            raise ResearchTraceabilityError("human_summary must explain the review decision")
        if confidence < 0 or confidence > 1:
            raise ResearchTraceabilityError("confidence must be between 0 and 1")

        report, thesis = self._report_and_thesis(report_id, thesis_id, user_id)
        checkpoint = ThesisCheckpoint(
            thesis_id=thesis.id,
            checkpoint_type="research_evidence_review",
            observed_facts_json={
                "research_report_id": report.id,
                "data_snapshot_id": report.data_snapshot_id,
                "report_type": report.report_type,
                "report_summary": report.summary,
                "bullish_case": report.bullish_case,
                "bearish_case": report.bearish_case,
                "key_risks": report.key_risks,
                "suggested_action": report.suggested_action,
                "report_confidence": float(report.confidence or 0),
                "citation_refs": citation_refs(report),
                "human_review": summary,
                "human_decision": decision,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "execution_available": False,
            },
            supports_thesis=decision == "supports",
            weakens_thesis=decision == "weakens",
            invalidates_thesis=decision == "invalidates",
            ai_summary=f"Research report {report.id} was reviewed by a human: {summary}",
            confidence=confidence,
        )
        self.db.add(checkpoint)
        self.db.flush()
        if decision == "invalidates":
            thesis.status = "invalidated"
        elif decision == "weakens" and thesis.status == "active":
            thesis.status = "monitoring"
        elif decision == "supports" and thesis.status == "monitoring":
            thesis.status = "active"

        write_audit_log(
            self.db,
            action="research_report.reviewed_against_thesis",
            entity_type="ThesisCheckpoint",
            entity_id=checkpoint.id,
            payload_json={
                "research_report_id": report.id,
                "thesis_id": thesis.id,
                "decision": decision,
                "data_snapshot_id": report.data_snapshot_id,
                "citation_refs": citation_refs(report),
                "human_review_required": True,
                "execution_available": False,
            },
            actor_id=user_id,
        )
        self.db.commit()
        self.db.refresh(checkpoint)
        return {
            "status": "reviewed",
            "report_id": report.id,
            "thesis_id": thesis.id,
            "thesis_status": thesis.status,
            "checkpoint": checkpoint_payload(checkpoint),
            "trace": trace_payload(report, thesis, checkpoint),
            "next_action": "Create a human-controlled plan and run decision gates." if decision != "invalidates" else "Do not add exposure; review or replace the invalidated thesis.",
            "execution_available": False,
        }

    def decision_context(self, *, report_id: str, user_id: str) -> dict[str, Any]:
        report = self.db.get(ResearchReport, report_id)
        if report is None:
            raise ResearchTraceabilityError("research report not found")
        thesis_query = select(InvestmentThesis).where(InvestmentThesis.user_id == user_id)
        if report.asset_id is not None:
            thesis_query = thesis_query.where(InvestmentThesis.asset_id == report.asset_id)
        theses = list(
            self.db.scalars(
                thesis_query.order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc()).limit(100)
            ).all()
        )
        accounts = list(
            self.db.scalars(
                select(Account)
                .where(Account.live_trading_enabled.is_(False))
                .order_by(Account.mode.desc(), Account.name.asc(), Account.id.asc())
                .limit(100)
            ).all()
        )
        reviews = [self._review_checkpoint(report.id, thesis.id) for thesis in theses]
        latest_review = next((item for item in reviews if item is not None), None)
        return {
            "report_id": report.id,
            "asset_id": report.asset_id,
            "data_snapshot_id": report.data_snapshot_id,
            "eligible_theses": [
                {
                    "id": thesis.id,
                    "asset_id": thesis.asset_id,
                    "entry_reason": thesis.entry_reason,
                    "status": thesis.status,
                    "confidence": float(thesis.confidence or 0),
                }
                for thesis in theses
            ],
            "eligible_accounts": [
                {
                    "id": account.id,
                    "name": account.name,
                    "mode": account.mode,
                    "broker": account.broker,
                    "base_currency": account.base_currency,
                    "live_trading_enabled": account.live_trading_enabled,
                }
                for account in accounts
            ],
            "latest_review_checkpoint": checkpoint_payload(latest_review) if latest_review else None,
            "human_review_required": True,
            "execution_available": False,
        }

    def create_plan_and_evaluate(
        self,
        *,
        report_id: str,
        thesis_id: str,
        user_id: str,
        account_id: str,
        side: str,
        order_type: str,
        quantity: float | None,
        notional: float | None,
        limit_price: float | None,
        user_rationale: str,
        risk_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if side not in {"buy", "sell"}:
            raise ResearchTraceabilityError("side must be buy or sell")
        if order_type not in {"market", "limit"}:
            raise ResearchTraceabilityError("order_type must be market or limit")
        if not quantity and not notional:
            raise ResearchTraceabilityError("quantity or notional is required")
        if quantity is not None and quantity <= 0:
            raise ResearchTraceabilityError("quantity must be positive")
        if notional is not None and notional <= 0:
            raise ResearchTraceabilityError("notional must be positive")
        if order_type == "limit" and (limit_price is None or limit_price <= 0):
            raise ResearchTraceabilityError("positive limit_price is required for limit orders")

        report, thesis = self._report_and_thesis(report_id, thesis_id, user_id)
        account = self.db.get(Account, account_id)
        if account is None:
            raise ResearchTraceabilityError("account not found")
        checkpoint = self._review_checkpoint(report.id, thesis.id)
        if checkpoint is None:
            raise ResearchTraceabilityError("review this research report against the thesis before creating a plan")

        trace = trace_payload(report, thesis, checkpoint)
        rationale = user_rationale.strip() or (
            f"Human-reviewed research plan based on report {report.id}; thesis checkpoint {checkpoint.id}."
        )
        intent = OrderIntent(
            source_type="research_report",
            source_id=report.id,
            asset_id=thesis.asset_id,
            account_id=account.id,
            investment_thesis_id=thesis.id,
            side=side,
            order_type=order_type,
            quantity=quantity,
            notional=notional,
            limit_price=limit_price,
            rationale=rationale,
            user_rationale=rationale,
            evidence_json={
                **trace,
                "human_review_required": True,
                "plan_created_by": user_id,
                "execution_available": False,
            },
            status="created",
        )
        self.db.add(intent)
        self.db.flush()
        write_audit_log(
            self.db,
            action="research_report.plan_created",
            entity_type="OrderIntent",
            entity_id=intent.id,
            payload_json={
                "research_report_id": report.id,
                "thesis_id": thesis.id,
                "checkpoint_id": checkpoint.id,
                "data_snapshot_id": report.data_snapshot_id,
                "side": side,
                "execution_available": False,
            },
            actor_id=user_id,
        )
        self.db.commit()

        context = {
            **(risk_context or {}),
            "user_id": user_id,
            "data_snapshot_id": report.data_snapshot_id,
            "research_report_required": True,
            "quality_report_required": True,
            "thesis_conflict": checkpoint.invalidates_thesis,
            "thesis_invalidation_triggered": checkpoint.invalidates_thesis,
            "prior_user_statement": thesis.entry_reason,
            "current_action": f"{side} {thesis.asset_id}",
            "research_trace": trace,
            "execution_mode": "draft_only",
            "action": "CREATE_ORDER_DRAFT",
        }
        gates = DecisionGateService(self.db).evaluate_order(intent.id, context)
        return {
            "status": "risk_review_complete",
            "order_intent": intent_payload(intent),
            "gates": [gate_payload(gate) for gate in gates],
            "all_gates_passed": all(gate.status == "PASSED" for gate in gates),
            "trace": trace,
            "next_route": f"/?module=order_drafts&intent={intent.id}",
            "execution_available": False,
        }

    def _report_and_thesis(self, report_id: str, thesis_id: str, user_id: str) -> tuple[ResearchReport, InvestmentThesis]:
        report = self.db.get(ResearchReport, report_id)
        thesis = self.db.get(InvestmentThesis, thesis_id)
        if report is None:
            raise ResearchTraceabilityError("research report not found")
        if thesis is None or thesis.user_id != user_id:
            raise ResearchTraceabilityError("thesis not found")
        if report.asset_id is not None and report.asset_id != thesis.asset_id:
            raise ResearchTraceabilityError("research report asset does not match thesis asset")
        return report, thesis

    def _review_checkpoint(self, report_id: str, thesis_id: str) -> ThesisCheckpoint | None:
        checkpoints = list(
            self.db.scalars(
                select(ThesisCheckpoint)
                .where(
                    ThesisCheckpoint.thesis_id == thesis_id,
                    ThesisCheckpoint.checkpoint_type == "research_evidence_review",
                )
                .order_by(ThesisCheckpoint.created_at.desc(), ThesisCheckpoint.id.desc())
            ).all()
        )
        return next(
            (item for item in checkpoints if item.observed_facts_json.get("research_report_id") == report_id),
            None,
        )


def citation_refs(report: ResearchReport) -> list[str]:
    evidence = report.evidence if isinstance(report.evidence, dict) else {}
    refs: list[str] = [f"snapshot:{report.data_snapshot_id}"]
    for key in ("source_url", "url", "filing_url"):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
    for key in ("citations", "sources", "source_urls"):
        values = evidence.get(key)
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    refs.append(value.strip())
                elif isinstance(value, dict):
                    ref = value.get("url") or value.get("source_url") or value.get("snapshot_id")
                    if ref:
                        refs.append(str(ref))
    return list(dict.fromkeys(refs))[:50]


def trace_payload(report: ResearchReport, thesis: InvestmentThesis, checkpoint: ThesisCheckpoint) -> dict[str, Any]:
    return {
        "research_report_id": report.id,
        "data_snapshot_id": report.data_snapshot_id,
        "citation_refs": citation_refs(report),
        "thesis_id": thesis.id,
        "thesis_checkpoint_id": checkpoint.id,
        "checkpoint_decision": checkpoint.observed_facts_json.get("human_decision"),
        "checkpoint_confidence": float(checkpoint.confidence or 0),
    }


def checkpoint_payload(checkpoint: ThesisCheckpoint) -> dict[str, Any]:
    return {
        "id": checkpoint.id,
        "thesis_id": checkpoint.thesis_id,
        "checkpoint_type": checkpoint.checkpoint_type,
        "observed_facts_json": checkpoint.observed_facts_json,
        "supports_thesis": checkpoint.supports_thesis,
        "weakens_thesis": checkpoint.weakens_thesis,
        "invalidates_thesis": checkpoint.invalidates_thesis,
        "ai_summary": checkpoint.ai_summary,
        "confidence": float(checkpoint.confidence or 0),
        "created_at": checkpoint.created_at,
    }


def intent_payload(intent: OrderIntent) -> dict[str, Any]:
    return {
        "id": intent.id,
        "source_type": intent.source_type,
        "source_id": intent.source_id,
        "asset_id": intent.asset_id,
        "account_id": intent.account_id,
        "investment_thesis_id": intent.investment_thesis_id,
        "side": intent.side,
        "order_type": intent.order_type,
        "quantity": float(intent.quantity) if intent.quantity is not None else None,
        "notional": float(intent.notional) if intent.notional is not None else None,
        "limit_price": float(intent.limit_price) if intent.limit_price is not None else None,
        "rationale": intent.rationale,
        "evidence_json": intent.evidence_json,
        "status": intent.status,
        "created_at": intent.created_at,
    }


def gate_payload(gate: DecisionGate) -> dict[str, Any]:
    return {
        "id": gate.id,
        "gate_type": gate.gate_type,
        "status": gate.status,
        "score": float(gate.score or 0),
        "blocking_reasons_json": gate.blocking_reasons_json,
        "warnings_json": gate.warnings_json,
        "evidence_json": gate.evidence_json,
        "created_at": gate.created_at,
    }
