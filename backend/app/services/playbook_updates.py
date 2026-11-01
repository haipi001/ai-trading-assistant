from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PlaybookUpdateProposal
from app.models import PostTradeReview
from app.models import StrategyPlaybook


class PlaybookUpdateError(ValueError):
    pass


class PlaybookUpdateProposalService:
    def __init__(self, db: Session):
        self.db = db

    def propose_from_post_trade_review(self, review_id: str) -> PlaybookUpdateProposal:
        review = self.db.get(PostTradeReview, review_id)
        if review is None:
            raise PlaybookUpdateError("post trade review not found")

        existing = self.db.scalar(
            select(PlaybookUpdateProposal)
            .where(
                PlaybookUpdateProposal.source_type == "post_trade_review",
                PlaybookUpdateProposal.source_id == review.id,
            )
            .limit(1)
        )
        if existing is not None:
            return existing

        draft = self.db.get(OrderDraft, review.order_draft_id)
        intent = self.db.get(OrderIntent, draft.order_intent_id) if draft is not None else None
        proposal_json = self._build_proposal(review, intent)
        proposal = PlaybookUpdateProposal(
            user_id=review.user_id,
            source_type="post_trade_review",
            source_id=review.id,
            strategy_playbook_id=intent.strategy_playbook_id if intent is not None else None,
            proposal_json=proposal_json,
            rationale=self._rationale(review, intent),
            status="pending",
            requires_user_approval=True,
        )
        self.db.add(proposal)
        self.db.flush()
        self._write_audit_log(
            action="playbook_update_proposal.created_from_post_trade_review",
            entity_type="PlaybookUpdateProposal",
            entity_id=proposal.id,
            payload_json={
                "post_trade_review_id": review.id,
                "order_draft_id": review.order_draft_id,
                "strategy_playbook_id": proposal.strategy_playbook_id,
                "requires_user_approval": True,
                "auto_applied": False,
            },
        )
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def approve(self, proposal_id: str, *, reviewer_id: str | None = None, decision_reason: str | None = None) -> PlaybookUpdateProposal:
        proposal = self._get_pending(proposal_id)
        proposal.status = "approved_pending_manual_apply"
        proposal.reviewed_by = reviewer_id
        proposal.reviewed_at = datetime.now(timezone.utc)
        self._write_audit_log(
            action="playbook_update_proposal.approved_no_auto_apply",
            entity_type="PlaybookUpdateProposal",
            entity_id=proposal.id,
            payload_json={
                "reviewer_id": reviewer_id,
                "decision_reason": decision_reason,
                "strategy_playbook_id": proposal.strategy_playbook_id,
                "auto_applied": False,
            },
        )
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def reject(self, proposal_id: str, *, reviewer_id: str | None = None, decision_reason: str | None = None) -> PlaybookUpdateProposal:
        proposal = self._get_pending(proposal_id)
        proposal.status = "rejected"
        proposal.reviewed_by = reviewer_id
        proposal.reviewed_at = datetime.now(timezone.utc)
        self._write_audit_log(
            action="playbook_update_proposal.rejected",
            entity_type="PlaybookUpdateProposal",
            entity_id=proposal.id,
            payload_json={
                "reviewer_id": reviewer_id,
                "decision_reason": decision_reason,
                "strategy_playbook_id": proposal.strategy_playbook_id,
            },
        )
        self.db.commit()
        self.db.refresh(proposal)
        return proposal

    def preview_manual_apply(
        self,
        proposal_id: str,
        *,
        target_strategy_playbook_id: str | None = None,
        edited_rule_json: dict[str, Any] | None = None,
    ) -> tuple[PlaybookUpdateProposal, StrategyPlaybook, dict[str, Any]]:
        proposal = self._get_apply_ready(proposal_id)
        playbook = self._target_playbook(proposal, target_strategy_playbook_id)
        return proposal, playbook, self._manual_apply_patch(proposal, playbook, edited_rule_json)

    def apply_manually(
        self,
        proposal_id: str,
        *,
        reviewer_id: str | None = None,
        decision_reason: str | None = None,
        target_strategy_playbook_id: str | None = None,
        edited_rule_json: dict[str, Any] | None = None,
    ) -> tuple[PlaybookUpdateProposal, StrategyPlaybook, dict[str, Any]]:
        proposal, playbook, patch_json = self.preview_manual_apply(
            proposal_id,
            target_strategy_playbook_id=target_strategy_playbook_id,
            edited_rule_json=edited_rule_json,
        )
        proposed_rules = patch_json["after"]["risk_rules_json"]["manual_review_rules"]
        playbook.risk_rules_json = patch_json["after"]["risk_rules_json"]
        playbook.requires_human_approval = True
        proposal.strategy_playbook_id = playbook.id
        proposal.status = "applied_manually"
        proposal.reviewed_by = reviewer_id or proposal.reviewed_by
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.proposal_json = {
            **proposal.proposal_json,
            "status": "applied_manually",
            "manual_application": {
                "strategy_playbook_id": playbook.id,
                "reviewer_id": reviewer_id,
                "decision_reason": decision_reason,
                "patch_json": patch_json,
                "auto_applied": False,
            },
        }
        self._write_audit_log(
            action="playbook_update_proposal.applied_manually",
            entity_type="PlaybookUpdateProposal",
            entity_id=proposal.id,
            payload_json={
                "strategy_playbook_id": playbook.id,
                "reviewer_id": reviewer_id,
                "decision_reason": decision_reason,
                "rules_count": len(proposed_rules),
                "patch_json": patch_json,
                "auto_applied": False,
                "requires_human_approval": True,
            },
        )
        self._write_audit_log(
            action="strategy_playbook.rule_patch_applied_from_review",
            entity_type="StrategyPlaybook",
            entity_id=playbook.id,
            payload_json={
                "playbook_update_proposal_id": proposal.id,
                "reviewer_id": reviewer_id,
                "decision_reason": decision_reason,
                "field": "risk_rules_json.manual_review_rules",
                "auto_applied": False,
            },
        )
        self.db.commit()
        self.db.refresh(proposal)
        self.db.refresh(playbook)
        return proposal, playbook, patch_json

    def publish_as_new_version(
        self,
        proposal_id: str,
        *,
        reviewer_id: str | None = None,
        decision_reason: str | None = None,
        publish_note: str | None = None,
    ) -> tuple[PlaybookUpdateProposal, StrategyPlaybook, StrategyPlaybook, dict[str, Any]]:
        proposal = self.db.get(PlaybookUpdateProposal, proposal_id)
        if proposal is None:
            raise PlaybookUpdateError("playbook update proposal not found")
        if proposal.status != "applied_manually":
            raise PlaybookUpdateError("playbook update proposal must be applied manually before publishing a new version")
        current_playbook = self._target_playbook(proposal, proposal.strategy_playbook_id)
        current_rules = dict(current_playbook.risk_rules_json or {})
        current_version = int(current_rules.get("playbook_version", 1))
        next_version = current_version + 1
        published_rules = {
            **current_rules,
            "playbook_version": next_version,
            "published_from_playbook_id": current_playbook.id,
            "published_from_proposal_id": proposal.id,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "publish_note": publish_note,
        }
        new_playbook = StrategyPlaybook(
            user_id=current_playbook.user_id,
            name=current_playbook.name,
            strategy_type=current_playbook.strategy_type,
            applicable_markets=current_playbook.applicable_markets,
            applicable_assets=current_playbook.applicable_assets,
            entry_conditions_json=current_playbook.entry_conditions_json,
            exit_conditions_json=current_playbook.exit_conditions_json,
            risk_rules_json=published_rules,
            automation_level=current_playbook.automation_level,
            requires_human_approval=current_playbook.requires_human_approval,
            is_active=True,
        )
        current_playbook.is_active = False
        proposal.status = "published_as_new_version"
        proposal.reviewed_by = reviewer_id or proposal.reviewed_by
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.proposal_json = {
            **proposal.proposal_json,
            "published_version": {
                "previous_playbook_id": current_playbook.id,
                "published_playbook_version": next_version,
                "publish_note": publish_note,
                "reviewer_id": reviewer_id,
                "decision_reason": decision_reason,
            },
        }
        self.db.add(new_playbook)
        self.db.flush()
        publish_metadata = {
            "previous_playbook_id": current_playbook.id,
            "published_playbook_id": new_playbook.id,
            "published_playbook_version": next_version,
            "publish_note": publish_note,
            "reviewer_id": reviewer_id,
            "decision_reason": decision_reason,
        }
        self._write_audit_log(
            action="playbook_update_proposal.published_as_new_version",
            entity_type="PlaybookUpdateProposal",
            entity_id=proposal.id,
            payload_json=publish_metadata,
        )
        self._write_audit_log(
            action="strategy_playbook.new_version_published",
            entity_type="StrategyPlaybook",
            entity_id=new_playbook.id,
            payload_json=publish_metadata,
        )
        self.db.commit()
        self.db.refresh(proposal)
        self.db.refresh(current_playbook)
        self.db.refresh(new_playbook)
        return proposal, current_playbook, new_playbook, publish_metadata

    def _get_pending(self, proposal_id: str) -> PlaybookUpdateProposal:
        proposal = self.db.get(PlaybookUpdateProposal, proposal_id)
        if proposal is None:
            raise PlaybookUpdateError("playbook update proposal not found")
        if proposal.status != "pending":
            raise PlaybookUpdateError("playbook update proposal already reviewed")
        return proposal

    def _get_apply_ready(self, proposal_id: str) -> PlaybookUpdateProposal:
        proposal = self.db.get(PlaybookUpdateProposal, proposal_id)
        if proposal is None:
            raise PlaybookUpdateError("playbook update proposal not found")
        if proposal.status != "approved_pending_manual_apply":
            raise PlaybookUpdateError("playbook update proposal must be approved before manual apply")
        return proposal

    def _target_playbook(
        self,
        proposal: PlaybookUpdateProposal,
        target_strategy_playbook_id: str | None,
    ) -> StrategyPlaybook:
        playbook_id = target_strategy_playbook_id or proposal.strategy_playbook_id
        if not playbook_id:
            raise PlaybookUpdateError("manual apply requires a target strategy playbook")
        playbook = self.db.get(StrategyPlaybook, playbook_id)
        if playbook is None:
            raise PlaybookUpdateError("target strategy playbook not found")
        if playbook.user_id != proposal.user_id:
            raise PlaybookUpdateError("target strategy playbook user does not match proposal user")
        return playbook

    def _manual_apply_patch(
        self,
        proposal: PlaybookUpdateProposal,
        playbook: StrategyPlaybook,
        edited_rule_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        existing_risk_rules = dict(playbook.risk_rules_json or {})
        manual_review_rules = list(existing_risk_rules.get("manual_review_rules") or [])
        version_history = list(existing_risk_rules.get("version_history") or [])
        if any(isinstance(rule, dict) and rule.get("source_proposal_id") == proposal.id for rule in manual_review_rules):
            raise PlaybookUpdateError("playbook update proposal is already applied to this playbook")

        suggested_rule = self._normalized_rule(proposal, edited_rule_json)
        rule_to_append = {
            **suggested_rule,
            "source": "post_trade_review_playbook_update_proposal",
            "source_proposal_id": proposal.id,
            "requires_human_approval": True,
            "auto_execution_allowed": False,
        }
        next_revision = int(existing_risk_rules.get("manual_revision", 0)) + 1
        version_entry = {
            "revision": next_revision,
            "proposal_id": proposal.id,
            "source_type": proposal.source_type,
            "source_id": proposal.source_id,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "strategy_playbook_id": playbook.id,
            "proposal_status": proposal.status,
            "rule_title": rule_to_append.get("title"),
        }
        next_risk_rules = {
            **existing_risk_rules,
            "manual_revision": next_revision,
            "manual_review_rules": [*manual_review_rules, rule_to_append],
            "version_history": [*version_history, version_entry][-20:],
        }
        return {
            "operation": "append",
            "target": "StrategyPlaybook.risk_rules_json.manual_review_rules",
            "strategy_playbook_id": playbook.id,
            "before": {
                "risk_rules_json": existing_risk_rules,
                "requires_human_approval": playbook.requires_human_approval,
            },
            "after": {
                "risk_rules_json": next_risk_rules,
                "requires_human_approval": True,
            },
            "appended_rule": rule_to_append,
            "version_entry": version_entry,
            "safety": {
                "auto_applied": False,
                "live_execution_enabled": False,
                "requires_human_approval": True,
            },
        }

    def _normalized_rule(
        self,
        proposal: PlaybookUpdateProposal,
        edited_rule_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        source_rule = edited_rule_json or proposal.proposal_json.get("suggested_rule") or {}
        if not isinstance(source_rule, dict):
            raise PlaybookUpdateError("playbook update proposal suggested_rule is invalid")
        name = str(source_rule.get("name") or "").strip()
        condition = str(source_rule.get("condition") or "").strip()
        action = str(source_rule.get("action") or "").strip()
        if not name or not condition or not action:
            raise PlaybookUpdateError("manual apply rule requires name, condition, and action")
        return {
            "name": name,
            "condition": condition,
            "action": action,
            "source_review_id": source_rule.get("source_review_id") or proposal.source_id,
        }

    def _build_proposal(self, review: PostTradeReview, intent: OrderIntent | None) -> dict[str, Any]:
        trade_summary = review.prompt_json.get("trade_summary", {}) if isinstance(review.prompt_json, dict) else {}
        review_json = review.review_json if isinstance(review.review_json, dict) else {}
        side = intent.side if intent is not None else trade_summary.get("side", "unknown")
        asset_symbol = trade_summary.get("asset_symbol", "unknown")
        lessons = [
            value
            for key, value in review_json.items()
            if isinstance(value, str) and key.lower() in {"lesson", "lessons", "mistake", "improvement", "note"}
        ]
        if not lessons:
            lessons = ["Review this trade outcome before repeating the same setup."]

        return {
            "proposal_type": "manual_playbook_rule_update",
            "target": "StrategyPlaybook",
            "status": "proposal_only",
            "safe_apply_mode": "manual_only",
            "suggested_rule": {
                "name": f"Review {asset_symbol} {side} setup before reuse",
                "condition": "Before reusing a similar setup, compare thesis alignment, gate warnings, fill quality, and review lesson.",
                "action": "Require explicit human confirmation and attach the prior post-trade review.",
                "source_review_id": review.id,
            },
            "evidence": {
                "trade_summary": trade_summary,
                "review_json": review_json,
                "lessons": lessons,
            },
            "not_implemented": "This proposal does not mutate StrategyPlaybook automatically.",
        }

    def _rationale(self, review: PostTradeReview, intent: OrderIntent | None) -> str:
        source = "completed" if review.status == "completed" else "pending"
        side = intent.side if intent is not None else "unknown"
        return (
            f"Generated from a {source} post-trade review for a {side} paper trade. "
            "It is a proposal only and requires explicit user approval before any playbook change."
        )

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
                actor_id="playbook-update-proposal-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )
