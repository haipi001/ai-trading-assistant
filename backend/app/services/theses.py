import json
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError
from pydantic import field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import AIProvider
from app.ai import DeepSeekProvider
from app.ai import MockAIProvider
from app.ai import OpenAIProvider
from app.core.auth import AuthenticatedUser
from app.ai.prompts import PromptTemplateLoader
from app.models import Asset
from app.models import AuditLog
from app.models import InvestmentThesis
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PlaybookUpdateProposal
from app.models import Position
from app.models import PostTradeReview
from app.models import ThesisCheckpoint
from app.models import ThesisViolation
from app.services.human_control import HumanControlService
from app.services.data_catalog import DataCatalogService


CheckpointStatus = Literal["SUPPORTS_THESIS", "WEAKENS_THESIS", "INVALIDATES_THESIS", "DATA_INSUFFICIENT"]


class InvalidThesisOutputError(ValueError):
    pass


class ThesisNotFoundError(ValueError):
    pass


class AssetNotFoundError(ValueError):
    pass


class ThesisCaptureAIOutput(BaseModel):
    entry_reason: str
    key_drivers: list[str] = Field(min_length=1)
    invalidation_conditions: list[str] = Field(min_length=1)
    expected_horizon: str
    target_condition: str
    max_loss_tolerance_pct: float = Field(ge=0, le=1)
    position_plan: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)

    @field_validator("entry_reason", "expected_horizon", "target_condition")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class ThesisMonitorAIOutput(BaseModel):
    checkpoint_status: CheckpointStatus
    observed_facts: dict[str, Any] = Field(default_factory=dict)
    ai_summary: str
    confidence: float = Field(ge=0, le=1)

    @field_validator("ai_summary")
    @classmethod
    def require_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ai_summary must not be empty")
        return value


class ThesisViolationMessageAIOutput(BaseModel):
    violation_type: str
    message: str
    explanation: str
    intervention_level: Literal["SILENT_RECORD", "SOFT_WARNING", "HARD_CONFIRM", "BLOCK"]


class ThesisCaptureService:
    def __init__(
        self,
        db: Session,
        *,
        prompt_loader: PromptTemplateLoader | None = None,
        provider: AIProvider | None = None,
        actor: AuthenticatedUser | None = None,
    ):
        self.db = db
        self.prompt_loader = prompt_loader or PromptTemplateLoader()
        self.provider = provider or MockAIProvider()
        self.actor = actor

    def capture(
        self,
        *,
        user_id: str,
        asset_id: str,
        user_rationale: str,
        intended_action: str,
        current_position: dict[str, Any],
        market_context: dict[str, Any],
        data_snapshot_id: str,
        account_id: str | None = None,
        position_id: str | None = None,
        strategy_playbook_id: str | None = None,
        provider_name: str = "mock",
    ) -> InvestmentThesis:
        DataCatalogService(self.db).require_trusted_snapshot(
            data_snapshot_id,
            decision_scope="thesis_capture",
        )
        asset = self._require_asset(asset_id)
        resolved_asset_id = asset.id
        input_facts = {
            "user_id": user_id,
            "asset_id": resolved_asset_id,
            "asset_ref": asset_id,
            "symbol": asset.symbol,
            "account_id": account_id,
            "position_id": position_id,
            "strategy_playbook_id": strategy_playbook_id,
            "data_snapshot_id": data_snapshot_id,
            "user_rationale": user_rationale,
            "intended_action": intended_action,
            "current_position": current_position,
            "market_context": market_context,
        }
        prompt_template = self.prompt_loader.load("thesis_capture")

        try:
            raw_output = self._generate_capture_output(provider_name, input_facts, prompt_template)
            validated = self._validate_capture_output(raw_output)
        except InvalidThesisOutputError as exc:
            self._write_audit_log(
                action="investment_thesis.invalid_output_rejected",
                entity_type="InvestmentThesis",
                entity_id=asset_id,
                payload_json={"provider": provider_name, "error": str(exc), "input_facts": input_facts},
            )
            self.db.commit()
            raise

        thesis = InvestmentThesis(
            user_id=user_id,
            asset_id=resolved_asset_id,
            account_id=account_id,
            position_id=position_id,
            strategy_playbook_id=strategy_playbook_id,
            data_snapshot_id=data_snapshot_id,
            entry_reason=validated.entry_reason,
            key_drivers_json={"items": validated.key_drivers},
            invalidation_conditions_json={"items": validated.invalidation_conditions},
            expected_horizon=validated.expected_horizon,
            target_condition=validated.target_condition,
            max_loss_tolerance_pct=validated.max_loss_tolerance_pct,
            position_plan_json=validated.position_plan,
            confidence=validated.confidence,
            source=f"{provider_name}_ai_thesis_capture",
            status="active",
        )
        self.db.add(thesis)
        self.db.flush()
        self._write_audit_log(
            action="investment_thesis.captured",
            entity_type="InvestmentThesis",
            entity_id=thesis.id,
            payload_json={"provider": provider_name, "input_facts": input_facts},
        )
        self.db.commit()
        self.db.refresh(thesis)
        return thesis

    def _generate_capture_output(self, provider_name: str, input_facts: dict[str, Any], prompt_template: str) -> str:
        provider = self._selected_provider(provider_name)
        method = getattr(provider, "generate_thesis_capture", None)
        if method is None:
            raise InvalidThesisOutputError(f"provider does not support thesis capture: {provider_name}")
        return method(input_facts=input_facts, prompt_template=prompt_template)

    def _selected_provider(self, provider_name: str) -> AIProvider:
        if self.provider and provider_name == "mock":
            return self.provider
        if provider_name == "openai":
            return OpenAIProvider()
        if provider_name == "deepseek":
            return DeepSeekProvider()
        if provider_name == "configured":
            if self.actor is None:
                raise InvalidThesisOutputError("configured provider requires an authenticated user")
            return HumanControlService(self.db).configured_ai_provider(actor=self.actor)
        if provider_name == "mock":
            return MockAIProvider()
        raise InvalidThesisOutputError(f"unsupported AI provider: {provider_name}")

    def _validate_capture_output(self, raw_output: str | dict[str, Any]) -> ThesisCaptureAIOutput:
        payload = self._parse_json(raw_output)
        try:
            return ThesisCaptureAIOutput.model_validate(payload)
        except ValidationError as exc:
            raise InvalidThesisOutputError(f"AI thesis capture output failed schema validation: {exc}") from exc

    def _require_asset(self, asset_id: str) -> Asset:
        asset = self.db.scalar(select(Asset).where(Asset.id == asset_id))
        if asset is None:
            asset = self.db.scalar(
                select(Asset)
                .where(Asset.symbol == asset_id)
                .order_by(Asset.updated_at.desc(), Asset.id.desc())
                .limit(1)
            )
        if asset is None:
            raise AssetNotFoundError(f"asset not found: {asset_id}")
        return asset

    def _parse_json(self, raw_output: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise InvalidThesisOutputError("AI provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise InvalidThesisOutputError("AI provider output must be a JSON object")
        return payload

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
                actor_id="thesis-capture-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


class ThesisMonitorService:
    def __init__(
        self,
        db: Session,
        *,
        prompt_loader: PromptTemplateLoader | None = None,
        provider: AIProvider | None = None,
        actor: AuthenticatedUser | None = None,
    ):
        self.db = db
        self.prompt_loader = prompt_loader or PromptTemplateLoader()
        self.provider = provider or MockAIProvider()
        self.actor = actor

    def monitor(
        self,
        *,
        thesis_id: str,
        new_facts: dict[str, Any],
        news: list[dict[str, Any]],
        price_movement: dict[str, Any],
        earnings_data: dict[str, Any],
        technical_signals: list[dict[str, Any]],
        onchain_signals: list[dict[str, Any]],
        data_snapshot_id: str,
        provider_name: str = "mock",
    ) -> ThesisCheckpoint:
        DataCatalogService(self.db).require_trusted_snapshot(
            data_snapshot_id,
            decision_scope="thesis_monitor",
        )
        thesis = self._require_thesis(thesis_id)
        input_facts = {
            "thesis": {
                "id": thesis.id,
                "entry_reason": thesis.entry_reason,
                "key_drivers": thesis.key_drivers_json,
                "invalidation_conditions": thesis.invalidation_conditions_json,
                "max_loss_tolerance_pct": float(thesis.max_loss_tolerance_pct),
                "status": thesis.status,
            },
            "new_facts": new_facts,
            "news": news,
            "price_movement": price_movement,
            "earnings_data": earnings_data,
            "technical_signals": technical_signals,
            "onchain_signals": onchain_signals,
            "data_snapshot_id": data_snapshot_id,
        }
        prompt_template = self.prompt_loader.load("thesis_monitor")

        try:
            raw_output = self._generate_monitor_output(provider_name, input_facts, prompt_template)
            validated = self._validate_monitor_output(raw_output)
        except InvalidThesisOutputError as exc:
            self._write_audit_log(
                action="thesis_checkpoint.invalid_output_rejected",
                entity_type="InvestmentThesis",
                entity_id=thesis_id,
                payload_json={"provider": provider_name, "error": str(exc), "input_facts": input_facts},
            )
            self.db.commit()
            raise

        checkpoint = ThesisCheckpoint(
            thesis_id=thesis_id,
            data_snapshot_id=data_snapshot_id,
            checkpoint_type=validated.checkpoint_status,
            observed_facts_json=validated.observed_facts,
            supports_thesis=validated.checkpoint_status == "SUPPORTS_THESIS",
            weakens_thesis=validated.checkpoint_status == "WEAKENS_THESIS",
            invalidates_thesis=validated.checkpoint_status == "INVALIDATES_THESIS",
            ai_summary=validated.ai_summary,
            confidence=validated.confidence,
        )
        self.db.add(checkpoint)
        self.db.flush()
        self._write_audit_log(
            action="thesis_checkpoint.created",
            entity_type="ThesisCheckpoint",
            entity_id=checkpoint.id,
            payload_json={"provider": provider_name, "checkpoint_status": validated.checkpoint_status},
        )
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    def create_violation_message(
        self,
        *,
        thesis_id: str,
        user_id: str,
        current_action: str,
        related_order_intent_id: str | None = None,
        prior_user_statement: str | None = None,
        intervention_level: str = "HARD_CONFIRM",
        provider_name: str = "mock",
    ) -> tuple[ThesisViolation, ThesisViolationMessageAIOutput]:
        thesis = self._require_thesis(thesis_id)
        input_facts = {
            "thesis_id": thesis_id,
            "current_action": current_action,
            "prior_user_statement": prior_user_statement or thesis.entry_reason,
            "intervention_level": intervention_level,
        }
        prompt_template = self.prompt_loader.load("thesis_violation_message")

        try:
            raw_output = self._generate_violation_message_output(provider_name, input_facts, prompt_template)
            validated = self._validate_violation_message_output(raw_output)
        except InvalidThesisOutputError as exc:
            self._write_audit_log(
                action="thesis_violation.invalid_output_rejected",
                entity_type="InvestmentThesis",
                entity_id=thesis_id,
                payload_json={"provider": provider_name, "error": str(exc), "input_facts": input_facts},
            )
            self.db.commit()
            raise

        violation = ThesisViolation(
            thesis_id=thesis_id,
            user_id=user_id,
            related_order_intent_id=related_order_intent_id,
            violation_type=validated.violation_type,
            prior_user_statement=prior_user_statement or thesis.entry_reason,
            current_action=current_action,
            explanation=validated.explanation,
            intervention_level=validated.intervention_level,
            resolved_status="open",
        )
        self.db.add(violation)
        self.db.flush()
        self._write_audit_log(
            action="thesis_violation.created",
            entity_type="ThesisViolation",
            entity_id=violation.id,
            payload_json={"message": validated.message, "provider": provider_name},
        )
        self.db.commit()
        self.db.refresh(violation)
        return violation, validated

    def list_checkpoints(self, thesis_id: str, *, limit: int = 100) -> list[ThesisCheckpoint]:
        self._require_thesis(thesis_id)
        return list(
            self.db.scalars(
                select(ThesisCheckpoint)
                .where(ThesisCheckpoint.thesis_id == thesis_id)
                .order_by(ThesisCheckpoint.created_at, ThesisCheckpoint.id)
                .limit(limit)
            ).all()
        )

    def list_events(self, thesis_id: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        thesis_ids = [thesis_id] if thesis_id else list(
            self.db.scalars(select(InvestmentThesis.id).order_by(InvestmentThesis.updated_at.desc())).all()
        )
        events: list[dict[str, Any]] = []
        for current_thesis_id in thesis_ids:
            thesis = self._require_thesis(current_thesis_id)
            events.extend(self._capture_events_for(thesis))
        events.sort(key=lambda item: self._normalize_event_time(item["event_time"]), reverse=True)
        return events[:limit]

    def create_event(
        self,
        *,
        thesis_id: str,
        event_type: str,
        title: str,
        description: str = "",
        source: str = "manual_workspace",
        event_time: datetime | None = None,
        impact_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        thesis = self._require_thesis(thesis_id)
        event_id = str(uuid4())
        event_time_value = event_time or datetime.now(timezone.utc)
        payload = {
            "id": event_id,
            "thesis_id": thesis.id,
            "event_type": event_type,
            "title": title,
            "description": description,
            "source": source,
            "event_time": event_time_value.isoformat(),
            "impact_json": impact_json or {},
        }
        self.db.add(
            AuditLog(
                actor_type="user",
                actor_id=source,
                action="thesis_event.created",
                entity_type="ThesisEvent",
                entity_id=event_id,
                payload_json=payload,
            )
        )
        self.db.commit()
        return {
            **payload,
            "event_time": event_time_value,
        }

    def build_context(self, thesis_id: str) -> dict[str, Any]:
        thesis = self._require_thesis(thesis_id)
        latest_checkpoint = self.db.scalar(
            select(ThesisCheckpoint)
            .where(ThesisCheckpoint.thesis_id == thesis_id)
            .order_by(ThesisCheckpoint.created_at.desc(), ThesisCheckpoint.id.desc())
            .limit(1)
        )
        open_violations = list(
            self.db.scalars(
                select(ThesisViolation)
                .where(ThesisViolation.thesis_id == thesis_id, ThesisViolation.resolved_status == "open")
                .order_by(ThesisViolation.created_at.desc(), ThesisViolation.id.desc())
            ).all()
        )
        position_statement = select(Position).where(Position.asset_id == thesis.asset_id)
        if thesis.account_id:
            position_statement = position_statement.where(Position.account_id == thesis.account_id)
        linked_positions = list(self.db.scalars(position_statement).all())
        linked_intents = list(
            self.db.scalars(
                select(OrderIntent)
                .where(OrderIntent.investment_thesis_id == thesis_id)
                .order_by(OrderIntent.created_at.desc(), OrderIntent.id.desc())
                .limit(20)
            ).all()
        )
        intent_ids = [intent.id for intent in linked_intents]
        linked_drafts = list(
            self.db.scalars(
                select(OrderDraft)
                .where(OrderDraft.order_intent_id.in_(intent_ids) if intent_ids else False)
                .order_by(OrderDraft.created_at.desc(), OrderDraft.id.desc())
            ).all()
        ) if intent_ids else []
        draft_ids = [draft.id for draft in linked_drafts]
        linked_reviews = list(
            self.db.scalars(
                select(PostTradeReview)
                .where(PostTradeReview.order_draft_id.in_(draft_ids) if draft_ids else False)
                .order_by(PostTradeReview.updated_at.desc(), PostTradeReview.id.desc())
            ).all()
        ) if draft_ids else []
        review_ids = [review.id for review in linked_reviews]
        linked_proposals = list(
            self.db.scalars(
                select(PlaybookUpdateProposal)
                .where(
                    PlaybookUpdateProposal.source_type == "post_trade_review",
                    PlaybookUpdateProposal.source_id.in_(review_ids) if review_ids else False,
                )
                .order_by(PlaybookUpdateProposal.updated_at.desc(), PlaybookUpdateProposal.id.desc())
            ).all()
        ) if review_ids else []
        recent_events = self.list_events(thesis_id, limit=10)
        health_status = self._health_status(thesis, latest_checkpoint, open_violations)
        return {
            "thesis_id": thesis.id,
            "health_status": health_status,
            "summary": self._context_summary(
                thesis,
                health_status,
                latest_checkpoint,
                len(open_violations),
                len(linked_reviews),
                len(linked_proposals),
            ),
            "latest_checkpoint": latest_checkpoint,
            "open_violation_count": len(open_violations),
            "linked_positions": [
                {
                    "id": position.id,
                    "account_id": position.account_id,
                    "asset_id": position.asset_id,
                    "quantity": float(position.quantity),
                    "market_value": float(position.market_value),
                    "unrealized_pnl": float(position.unrealized_pnl),
                }
                for position in linked_positions
            ],
            "linked_order_intents": [
                {
                    "id": intent.id,
                    "side": intent.side,
                    "status": intent.status,
                    "created_at": intent.created_at,
                }
                for intent in linked_intents
            ],
            "linked_order_drafts": [
                {
                    "id": draft.id,
                    "order_intent_id": draft.order_intent_id,
                    "approval_status": draft.approval_status,
                    "execution_status": draft.execution_status,
                    "created_at": draft.created_at,
                }
                for draft in linked_drafts
            ],
            "linked_post_trade_reviews": [
                {
                    "id": review.id,
                    "order_draft_id": review.order_draft_id,
                    "status": review.status,
                    "created_at": review.created_at,
                    "updated_at": review.updated_at,
                }
                for review in linked_reviews
            ],
            "linked_playbook_proposals": [
                {
                    "id": proposal.id,
                    "strategy_playbook_id": proposal.strategy_playbook_id,
                    "status": proposal.status,
                    "rationale": proposal.rationale,
                    "reviewed_at": proposal.reviewed_at,
                    "created_at": proposal.created_at,
                }
                for proposal in linked_proposals
            ],
            "recent_events": recent_events,
        }

    def _generate_monitor_output(self, provider_name: str, input_facts: dict[str, Any], prompt_template: str) -> str:
        provider = self._selected_provider(provider_name)
        method = getattr(provider, "generate_thesis_monitor", None)
        if method is None:
            raise InvalidThesisOutputError(f"provider does not support thesis monitor: {provider_name}")
        return method(input_facts=input_facts, prompt_template=prompt_template)

    def _generate_violation_message_output(self, provider_name: str, input_facts: dict[str, Any], prompt_template: str) -> str:
        provider = self._selected_provider(provider_name)
        method = getattr(provider, "generate_thesis_violation_message", None)
        if method is None:
            raise InvalidThesisOutputError(f"provider does not support thesis violation messaging: {provider_name}")
        return method(input_facts=input_facts, prompt_template=prompt_template)

    def _selected_provider(self, provider_name: str) -> AIProvider:
        if self.provider and provider_name == "mock":
            return self.provider
        if provider_name == "openai":
            return OpenAIProvider()
        if provider_name == "deepseek":
            return DeepSeekProvider()
        if provider_name == "configured":
            if self.actor is None:
                raise InvalidThesisOutputError("configured provider requires an authenticated user")
            return HumanControlService(self.db).configured_ai_provider(actor=self.actor)
        if provider_name == "mock":
            return MockAIProvider()
        raise InvalidThesisOutputError(f"unsupported AI provider: {provider_name}")

    def _validate_monitor_output(self, raw_output: str | dict[str, Any]) -> ThesisMonitorAIOutput:
        payload = self._parse_json(raw_output)
        try:
            return ThesisMonitorAIOutput.model_validate(payload)
        except ValidationError as exc:
            raise InvalidThesisOutputError(f"AI thesis monitor output failed schema validation: {exc}") from exc

    def _validate_violation_message_output(self, raw_output: str | dict[str, Any]) -> ThesisViolationMessageAIOutput:
        payload = self._parse_json(raw_output)
        try:
            return ThesisViolationMessageAIOutput.model_validate(payload)
        except ValidationError as exc:
            raise InvalidThesisOutputError(f"AI thesis violation output failed schema validation: {exc}") from exc

    def _require_thesis(self, thesis_id: str) -> InvestmentThesis:
        thesis = self.db.scalar(select(InvestmentThesis).where(InvestmentThesis.id == thesis_id))
        if thesis is None:
            raise ThesisNotFoundError(f"thesis not found: {thesis_id}")
        return thesis

    def _parse_json(self, raw_output: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise InvalidThesisOutputError("AI provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise InvalidThesisOutputError("AI provider output must be a JSON object")
        return payload

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
                actor_id="thesis-monitor-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )

    def _capture_events_for(self, thesis: InvestmentThesis) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [
            {
                "id": f"thesis-capture:{thesis.id}",
                "thesis_id": thesis.id,
                "event_type": "THESIS_CAPTURED",
                "title": "Thesis captured",
                "description": thesis.entry_reason,
                "source": thesis.source,
                "event_time": thesis.created_at,
                "impact_json": {"status": thesis.status, "confidence": float(thesis.confidence)},
            }
        ]
        checkpoints = list(
            self.db.scalars(
                select(ThesisCheckpoint)
                .where(ThesisCheckpoint.thesis_id == thesis.id)
                .order_by(ThesisCheckpoint.created_at.desc(), ThesisCheckpoint.id.desc())
                .limit(20)
            ).all()
        )
        events.extend(
            {
                "id": f"checkpoint:{checkpoint.id}",
                "thesis_id": thesis.id,
                "event_type": checkpoint.checkpoint_type,
                "title": checkpoint.checkpoint_type.replace("_", " ").title(),
                "description": checkpoint.ai_summary or "Checkpoint recorded.",
                "source": "thesis_monitor",
                "event_time": checkpoint.created_at,
                "impact_json": checkpoint.observed_facts_json,
            }
            for checkpoint in checkpoints
        )
        violations = list(
            self.db.scalars(
                select(ThesisViolation)
                .where(ThesisViolation.thesis_id == thesis.id)
                .order_by(ThesisViolation.created_at.desc(), ThesisViolation.id.desc())
                .limit(20)
            ).all()
        )
        events.extend(
            {
                "id": f"violation:{violation.id}",
                "thesis_id": thesis.id,
                "event_type": violation.violation_type,
                "title": "Thesis violation",
                "description": violation.explanation,
                "source": "thesis_violation",
                "event_time": violation.created_at,
                "impact_json": {
                    "intervention_level": violation.intervention_level,
                    "resolved_status": violation.resolved_status,
                },
            }
            for violation in violations
        )
        manual_events = list(
            self.db.scalars(
                select(AuditLog)
                .where(AuditLog.action == "thesis_event.created")
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(100)
            ).all()
        )
        for event in manual_events:
            payload = event.payload_json or {}
            if payload.get("thesis_id") != thesis.id:
                continue
            event_time_raw = payload.get("event_time")
            event_time = (
                self._normalize_event_time(datetime.fromisoformat(event_time_raw))
                if isinstance(event_time_raw, str)
                else self._normalize_event_time(event.created_at)
            )
            events.append(
                {
                    "id": str(payload.get("id") or event.id),
                    "thesis_id": thesis.id,
                    "event_type": str(payload.get("event_type") or "MANUAL_EVENT"),
                    "title": str(payload.get("title") or "Manual event"),
                    "description": str(payload.get("description") or ""),
                    "source": str(payload.get("source") or "manual_workspace"),
                    "event_time": event_time,
                    "impact_json": payload.get("impact_json") or {},
                }
            )
        return events

    def _health_status(
        self,
        thesis: InvestmentThesis,
        latest_checkpoint: ThesisCheckpoint | None,
        open_violations: list[ThesisViolation],
    ) -> str:
        if thesis.status == "invalidated":
            return "invalidated"
        if open_violations:
            return "violated"
        if latest_checkpoint and (latest_checkpoint.weakens_thesis or latest_checkpoint.invalidates_thesis):
            return "needs_review"
        return "healthy"

    def _context_summary(
        self,
        thesis: InvestmentThesis,
        health_status: str,
        latest_checkpoint: ThesisCheckpoint | None,
        open_violation_count: int,
        review_count: int,
        proposal_count: int,
    ) -> str:
        if health_status == "invalidated":
            return "This thesis is invalidated and should not justify new risk until replaced."
        if health_status == "violated":
            return f"This thesis has {open_violation_count} open violation(s) and requires explicit explanation before reuse."
        if health_status == "needs_review":
            checkpoint_name = latest_checkpoint.checkpoint_type if latest_checkpoint else "CHECKPOINT"
            return f"The latest checkpoint ({checkpoint_name}) weakened this thesis. Review before adding or reusing it."
        if proposal_count > 0:
            return f"This thesis already produced {proposal_count} playbook proposal(s), so its review loop is actively shaping strategy rules."
        if review_count > 0:
            return "This thesis is linked to completed workflow artifacts and can be reviewed through the decision loop."
        return f"This thesis is active and currently supports the recorded {thesis.expected_horizon} plan."

    def _normalize_event_time(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
