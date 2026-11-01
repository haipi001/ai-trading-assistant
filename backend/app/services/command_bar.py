from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset
from app.models import AuditLog
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.models import CommandQuery
from app.models import CommandResult
from app.models import CommandToolCall
from app.models import DataQualityReport
from app.models import InvestmentThesis
from app.models import MonthlyDecisionReview
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import Position
from app.models import Signal
from app.services.automation_policy import AutomationPolicyEngine
from app.services.automation_policy import AutomationPolicyNotImplementedError
from app.services.portfolio import PortfolioSummaryService


SUPPORTED_INTENTS = {
    "portfolio_summary",
    "position_lookup",
    "risk_exposure",
    "thesis_review",
    "thesis_capture",
    "market_news_summary",
    "signal_lookup",
    "behavior_pattern_review",
    "monthly_decision_review",
    "order_draft_lookup",
    "scenario_analysis",
}

EXECUTION_KEYWORDS = {
    "execute",
    "execution",
    "place order",
    "submit order",
    "send order",
    "live trade",
    "live execution",
    "market buy now",
    "market sell now",
    "下单",
    "执行交易",
    "实盘",
    "马上买入",
    "马上卖出",
    "直接买入",
    "直接卖出",
    "成交",
}


class CommandBarError(ValueError):
    pass


class CommandExecutionRejectedError(CommandBarError):
    pass


class CommandOrderIntentPolicyError(CommandBarError):
    pass


@dataclass(frozen=True)
class CommandBarRunResult:
    query: CommandQuery
    tool_calls: list[CommandToolCall]
    result: CommandResult
    order_intent: OrderIntent | None = None


class CommandBarService:
    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        *,
        user_id: str,
        raw_query: str,
        data_snapshot_id: str | None = None,
        context: dict[str, Any] | None = None,
        allow_order_intent: bool = False,
        account_id: str | None = None,
        asset_id: str | None = None,
        strategy_playbook_id: str | None = None,
        side: str | None = None,
        quantity: float | None = None,
        notional: float | None = None,
        user_rationale: str | None = None,
    ) -> CommandBarRunResult:
        normalized = normalize(raw_query)
        if is_execution_request(normalized):
            return self._reject_execution(user_id=user_id, raw_query=raw_query)

        detected_intent = detect_intent(normalized)
        required_tools = tools_for_intent(detected_intent)
        query = self._create_query(
            user_id=user_id,
            raw_query=raw_query,
            detected_intent=detected_intent,
            required_tools=required_tools,
            status="running",
        )

        tool_calls: list[CommandToolCall] = []
        for tool_name in required_tools:
            tool_output = self._run_tool(
                tool_name,
                user_id=user_id,
                raw_query=raw_query,
                data_snapshot_id=data_snapshot_id,
                context=context or {},
                account_id=account_id,
                asset_id=asset_id,
            )
            tool_calls.append(
                self._create_tool_call(
                    query.id,
                    tool_name=tool_name,
                    input_json={
                        "user_id": user_id,
                        "raw_query": raw_query,
                        "data_snapshot_id": data_snapshot_id or "unavailable",
                        "context": context or {},
                    },
                    output_json=tool_output,
                    status="completed",
                )
            )

        order_intent = None
        if allow_order_intent or looks_like_order_intent_request(normalized):
            order_intent = self._maybe_create_order_intent(
                query=query,
                user_id=user_id,
                account_id=account_id,
                asset_id=asset_id,
                strategy_playbook_id=strategy_playbook_id,
                side=side or infer_side(normalized),
                quantity=quantity,
                notional=notional,
                user_rationale=user_rationale or raw_query,
            )

        query.status = "completed"
        summary, structured = self._summarize(detected_intent, tool_calls, order_intent)
        result = self._create_result(
            query.id,
            summary=summary,
            structured_result_json=structured,
            data_sources_json=data_sources_for(detected_intent, data_snapshot_id, tool_calls),
        )
        self._write_audit_log(
            action="command_bar.query_completed",
            entity_type="CommandQuery",
            entity_id=query.id,
            payload_json={
                "user_id": user_id,
                "detected_intent": detected_intent,
                "required_tools": required_tools,
                "order_intent_id": order_intent.id if order_intent else None,
            },
        )
        self.db.commit()
        self._refresh(query, result, tool_calls, order_intent)
        return CommandBarRunResult(query=query, tool_calls=tool_calls, result=result, order_intent=order_intent)

    def list_queries(self, *, limit: int = 100) -> list[CommandQuery]:
        return list(self.db.scalars(select(CommandQuery).order_by(CommandQuery.created_at, CommandQuery.id).limit(limit)).all())

    def get_query(self, command_query_id: str) -> CommandBarRunResult:
        query = self.db.get(CommandQuery, command_query_id)
        if query is None:
            raise CommandBarError("command query not found")
        tool_calls = list(
            self.db.scalars(
                select(CommandToolCall)
                .where(CommandToolCall.command_query_id == command_query_id)
                .order_by(CommandToolCall.created_at, CommandToolCall.id)
            ).all()
        )
        result = self.db.scalar(select(CommandResult).where(CommandResult.command_query_id == command_query_id))
        if result is None:
            raise CommandBarError("command result not found")
        return CommandBarRunResult(query=query, tool_calls=tool_calls, result=result)

    def _reject_execution(self, *, user_id: str, raw_query: str) -> CommandBarRunResult:
        query = self._create_query(
            user_id=user_id,
            raw_query=raw_query,
            detected_intent="rejected_execution_request",
            required_tools=[],
            status="rejected",
        )
        result = self._create_result(
            query.id,
            summary="Execution requests are rejected. The command bar cannot execute trades.",
            structured_result_json={
                "rejected": True,
                "reason": "command_bar_cannot_execute_trades",
                "allowed_next_step": "Create a thesis, review risk, or request an order draft workflow.",
            },
            data_sources_json={"data_snapshot_id": "unavailable", "reason": "execution request rejected before tool use"},
        )
        self._write_audit_log(
            action="command_bar.execution_request_rejected",
            entity_type="CommandQuery",
            entity_id=query.id,
            payload_json={"user_id": user_id, "raw_query": raw_query},
        )
        self.db.commit()
        self._refresh(query, result, [], None)
        return CommandBarRunResult(query=query, tool_calls=[], result=result)

    def _run_tool(
        self,
        tool_name: str,
        *,
        user_id: str,
        raw_query: str,
        data_snapshot_id: str | None,
        context: dict[str, Any],
        account_id: str | None,
        asset_id: str | None,
    ) -> dict[str, Any]:
        if tool_name == "portfolio_summary_tool":
            return self._portfolio_summary(data_snapshot_id)
        if tool_name == "position_lookup_tool":
            return self._position_lookup(asset_id)
        if tool_name == "risk_exposure_tool":
            return self._risk_exposure(data_snapshot_id)
        if tool_name == "thesis_review_tool":
            return self._thesis_review(user_id=user_id, asset_id=asset_id)
        if tool_name == "thesis_capture_tool":
            return {"status": "requires_structured_capture", "message": "Use thesis capture with asset context before storing a thesis."}
        if tool_name == "market_news_summary_tool":
            return {"status": "data_unavailable", "message": "Market news data is unavailable in the current local snapshot."}
        if tool_name == "signal_lookup_tool":
            return self._signal_lookup(asset_id)
        if tool_name == "behavior_pattern_review_tool":
            return self._behavior_pattern_review(user_id)
        if tool_name == "monthly_decision_review_tool":
            return self._monthly_decision_review(user_id)
        if tool_name == "order_draft_lookup_tool":
            return self._order_draft_lookup(account_id)
        if tool_name == "scenario_analysis_tool":
            return self._scenario_analysis(raw_query=raw_query, context=context, data_snapshot_id=data_snapshot_id)
        return {"status": "data_unavailable", "message": f"Tool {tool_name} is unavailable."}

    def _maybe_create_order_intent(
        self,
        *,
        query: CommandQuery,
        user_id: str,
        account_id: str | None,
        asset_id: str | None,
        strategy_playbook_id: str | None,
        side: str,
        quantity: float | None,
        notional: float | None,
        user_rationale: str,
    ) -> OrderIntent:
        if not account_id or not asset_id:
            query.status = "blocked"
            result = self._create_result(
                query.id,
                summary="OrderIntent creation is blocked because account_id and asset_id are required.",
                structured_result_json={"blocked": True, "reason": "missing_account_or_asset"},
                data_sources_json={"data_snapshot_id": "unavailable"},
            )
            self._write_audit_log(
                action="command_bar.order_intent_blocked",
                entity_type="CommandQuery",
                entity_id=query.id,
                payload_json={"reason": "missing_account_or_asset"},
            )
            self.db.commit()
            self._refresh(query, result, [], None)
            raise CommandOrderIntentPolicyError("account_id and asset_id are required to create an OrderIntent")

        try:
            policy = AutomationPolicyEngine(self.db).get_effective_policy(
                user_id=user_id,
                account_id=account_id,
                asset_id=asset_id,
                strategy_playbook_id=strategy_playbook_id,
            )
        except AutomationPolicyNotImplementedError as exc:
            raise CommandOrderIntentPolicyError(str(exc)) from exc

        if not AutomationPolicyEngine(self.db).can_create_order_intent(policy):
            query.status = "blocked"
            result = self._create_result(
                query.id,
                summary="OrderIntent creation is blocked because AutomationPolicy is below A3_ORDER_DRAFT.",
                structured_result_json={
                    "blocked": True,
                    "reason": "automation_policy_below_a3",
                    "automation_level": policy.automation_level,
                    "policy_id": policy.id,
                },
                data_sources_json={"data_snapshot_id": "unavailable"},
            )
            self._write_audit_log(
                action="command_bar.order_intent_blocked",
                entity_type="CommandQuery",
                entity_id=query.id,
                payload_json={
                    "reason": "automation_policy_below_a3",
                    "automation_level": policy.automation_level,
                    "policy_id": policy.id,
                },
            )
            self.db.commit()
            self._refresh(query, result, [], None)
            raise CommandOrderIntentPolicyError("OrderIntent creation requires AutomationPolicy >= A3_ORDER_DRAFT")

        order_intent = OrderIntent(
            source_type="command_bar",
            source_id=query.id,
            asset_id=asset_id,
            account_id=account_id,
            strategy_playbook_id=strategy_playbook_id,
            automation_policy_id=policy.id,
            side=side,
            order_type="market",
            quantity=quantity,
            notional=notional,
            limit_price=None,
            rationale="Passive OrderIntent created by command bar; requires gates, risk checks, approval, and audit before any execution.",
            user_rationale=user_rationale,
            status="created",
        )
        self.db.add(order_intent)
        self.db.flush()
        self._write_audit_log(
            action="command_bar.order_intent_created",
            entity_type="OrderIntent",
            entity_id=order_intent.id,
            payload_json={"command_query_id": query.id, "policy_id": policy.id, "automation_level": policy.automation_level},
        )
        return order_intent

    def _portfolio_summary(self, data_snapshot_id: str | None) -> dict[str, Any]:
        current = PortfolioSummaryService(self.db).build_current()
        daily_summary = PortfolioSummaryService(self.db).build_daily_summary()
        return {
            "status": "completed",
            "data_snapshot_id": data_snapshot_id or "unavailable",
            "current": current,
            "daily_summary": daily_summary,
        }

    def _position_lookup(self, asset_id: str | None) -> dict[str, Any]:
        statement = select(Position)
        if asset_id:
            statement = statement.where(Position.asset_id == asset_id)
        positions = list(self.db.scalars(statement.order_by(Position.updated_at, Position.id)).all())
        assets = {asset.id: asset for asset in self.db.scalars(select(Asset)).all()}
        return {
            "status": "completed",
            "positions": [
                {
                    "id": position.id,
                    "account_id": position.account_id,
                    "asset_id": position.asset_id,
                    "symbol": assets[position.asset_id].symbol if position.asset_id in assets else "unknown",
                    "quantity": float(position.quantity),
                    "market_value": float(position.market_value),
                    "unrealized_pnl": float(position.unrealized_pnl),
                    "weight": float(position.weight),
                }
                for position in positions
            ],
        }

    def _risk_exposure(self, data_snapshot_id: str | None) -> dict[str, Any]:
        daily_summary = PortfolioSummaryService(self.db).build_daily_summary()
        return {
            "status": "completed",
            "data_snapshot_id": data_snapshot_id or "unavailable",
            "total_equity": daily_summary["total_equity"],
            "allocation": daily_summary["allocation"],
            "concentration_risks": daily_summary["concentration_risks"],
            "suggested_attention": daily_summary["suggested_attention"],
        }

    def _thesis_review(self, *, user_id: str, asset_id: str | None) -> dict[str, Any]:
        statement = select(InvestmentThesis).where(InvestmentThesis.user_id == user_id)
        if asset_id:
            statement = statement.where(InvestmentThesis.asset_id == asset_id)
        theses = list(self.db.scalars(statement.order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id).limit(20)).all())
        quality_summary = self._latest_data_quality(asset_id=asset_id)
        return {
            "status": "completed",
            "data_quality": quality_summary,
            "theses": [
                {
                    "id": thesis.id,
                    "asset_id": thesis.asset_id,
                    "status": thesis.status,
                    "entry_reason": thesis.entry_reason,
                    "key_drivers": thesis.key_drivers_json,
                    "invalidation_conditions": thesis.invalidation_conditions_json,
                    "confidence": float(thesis.confidence),
                }
                for thesis in theses
            ],
        }

    def _signal_lookup(self, asset_id: str | None) -> dict[str, Any]:
        statement = select(Signal)
        if asset_id:
            statement = statement.where(Signal.asset_id == asset_id)
        signals = list(self.db.scalars(statement.order_by(Signal.created_at.desc(), Signal.id).limit(20)).all())
        return {
            "status": "completed",
            "signals": [
                {
                    "id": signal.id,
                    "asset_id": signal.asset_id,
                    "signal_type": signal.signal_type,
                    "direction": signal.direction,
                    "strength": float(signal.strength),
                    "suggested_action": signal.suggested_action,
                    "confidence": float(signal.confidence),
                }
                for signal in signals
            ],
        }

    def _behavior_pattern_review(self, user_id: str) -> dict[str, Any]:
        patterns = list(
            self.db.scalars(
                select(BehaviorPattern)
                .where(BehaviorPattern.user_id == user_id)
                .order_by(BehaviorPattern.updated_at.desc(), BehaviorPattern.id)
                .limit(20)
            ).all()
        )
        return {
            "status": "completed",
            "profile": self._behavior_profile_summary(user_id),
            "patterns": [
                {
                    "id": pattern.id,
                    "pattern_type": pattern.pattern_type,
                    "description": pattern.description,
                    "severity": pattern.severity,
                    "frequency": pattern.frequency,
                    "estimated_cost": float(pattern.estimated_cost),
                }
                for pattern in patterns
            ],
        }

    def _monthly_decision_review(self, user_id: str) -> dict[str, Any]:
        reviews = list(
            self.db.scalars(
                select(MonthlyDecisionReview)
                .where(MonthlyDecisionReview.user_id == user_id)
                .order_by(MonthlyDecisionReview.period_end.desc(), MonthlyDecisionReview.id)
                .limit(12)
            ).all()
        )
        return {
            "status": "completed",
            "reviews": [
                {
                    "id": review.id,
                    "period_start": review.period_start.isoformat(),
                    "period_end": review.period_end.isoformat(),
                    "total_trades": review.total_trades,
                    "thesis_violating_trades": review.thesis_violating_trades,
                    "impulsive_trades": review.impulsive_trades,
                    "overtrading_cost": float(review.overtrading_cost),
                    "ai_summary": review.ai_summary,
                }
                for review in reviews
            ],
        }

    def _order_draft_lookup(self, account_id: str | None) -> dict[str, Any]:
        drafts = list(self.db.scalars(select(OrderDraft).order_by(OrderDraft.created_at.desc(), OrderDraft.id).limit(20)).all())
        intents = {intent.id: intent for intent in self.db.scalars(select(OrderIntent)).all()}
        if account_id:
            drafts = [draft for draft in drafts if draft.order_intent_id in intents and intents[draft.order_intent_id].account_id == account_id]
        return {
            "status": "completed",
            "order_drafts": [
                {
                    "id": draft.id,
                    "order_intent_id": draft.order_intent_id,
                    "approval_status": draft.approval_status,
                    "execution_status": draft.execution_status,
                    "risk_status": draft.risk_status,
                    "behavior_status": draft.behavior_status,
                }
                for draft in drafts
            ],
        }

    def _scenario_analysis(self, *, raw_query: str, context: dict[str, Any], data_snapshot_id: str | None) -> dict[str, Any]:
        shock_pct = float(context.get("shock_pct") or infer_shock_pct(raw_query) or -0.2)
        positions = PortfolioSummaryService(self.db).build_current()["positions"]
        impacted = []
        total_loss = 0.0
        target_symbol = infer_symbol(raw_query)
        for position in positions:
            if target_symbol and position["symbol"].lower() != target_symbol.lower():
                continue
            estimated_pnl = round(float(position["market_value"]) * shock_pct, 2)
            total_loss += estimated_pnl
            impacted.append({**position, "scenario_shock_pct": shock_pct, "estimated_pnl": estimated_pnl})
        return {
            "status": "completed",
            "data_snapshot_id": data_snapshot_id or "unavailable",
            "shock_pct": shock_pct,
            "estimated_pnl": round(total_loss, 2),
            "impacted_positions": impacted,
        }

    def _create_query(
        self,
        *,
        user_id: str,
        raw_query: str,
        detected_intent: str,
        required_tools: list[str],
        status: str,
    ) -> CommandQuery:
        query = CommandQuery(
            user_id=user_id,
            raw_query=raw_query,
            detected_intent=detected_intent,
            required_tools=required_tools,
            status=status,
        )
        self.db.add(query)
        self.db.flush()
        self._write_audit_log(
            action="command_bar.query_logged",
            entity_type="CommandQuery",
            entity_id=query.id,
            payload_json={
                "user_id": user_id,
                "detected_intent": detected_intent,
                "required_tools": required_tools,
                "status": status,
            },
        )
        return query

    def _create_tool_call(
        self,
        command_query_id: str,
        *,
        tool_name: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any],
        status: str,
    ) -> CommandToolCall:
        tool_call = CommandToolCall(
            command_query_id=command_query_id,
            tool_name=tool_name,
            input_json=input_json,
            output_json=output_json,
            status=status,
        )
        self.db.add(tool_call)
        self.db.flush()
        return tool_call

    def _create_result(
        self,
        command_query_id: str,
        *,
        summary: str,
        structured_result_json: dict[str, Any],
        data_sources_json: dict[str, Any],
    ) -> CommandResult:
        result = CommandResult(
            command_query_id=command_query_id,
            summary=summary,
            structured_result_json=structured_result_json,
            data_sources_json=data_sources_json,
        )
        self.db.add(result)
        self.db.flush()
        return result

    def _summarize(
        self,
        detected_intent: str,
        tool_calls: list[CommandToolCall],
        order_intent: OrderIntent | None,
    ) -> tuple[str, dict[str, Any]]:
        outputs = {tool_call.tool_name: tool_call.output_json for tool_call in tool_calls}
        next_steps = self._next_steps(detected_intent, outputs, order_intent)
        if detected_intent == "portfolio_summary":
            current = outputs.get("portfolio_summary_tool", {}).get("current", {})
            summary = f"Portfolio summary generated. Total equity: {current.get('total_equity', 0)}."
        elif detected_intent == "risk_exposure":
            risks = outputs.get("risk_exposure_tool", {}).get("concentration_risks", [])
            summary = f"Risk exposure reviewed. Concentration risks: {len(risks)}."
        elif detected_intent == "thesis_review":
            theses = outputs.get("thesis_review_tool", {}).get("theses", [])
            summary = f"Thesis review generated for {len(theses)} active thesis records."
        elif detected_intent == "scenario_analysis":
            scenario = outputs.get("scenario_analysis_tool", {})
            summary = f"Scenario analysis generated. Estimated PnL impact: {scenario.get('estimated_pnl', 0)}."
        else:
            summary = f"Command routed to {', '.join(outputs.keys()) or 'no tools'}."
        return summary, {
            "intent": detected_intent,
            "tool_outputs": outputs,
            "order_intent_id": order_intent.id if order_intent else None,
            "next_steps": next_steps,
        }

    def _latest_data_quality(self, *, asset_id: str | None) -> dict[str, Any]:
        statement = select(DataQualityReport).order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc())
        report = self.db.scalar(statement.limit(1))
        if report is None:
            return {"status": "unavailable", "decision_ready": False, "score": None}
        score = float(report.score)
        details = report.details_json or {}
        status = str(details.get("status") or ("healthy" if score >= 0.75 else "warning" if score >= 0.5 else "blocked"))
        return {
            "status": status,
            "decision_ready": score >= 0.75 and status not in {"stale", "failed", "blocked"},
            "score": score,
            "summary": str(details.get("summary") or f"Latest {report.metric_type} quality score is {score:.2f}."),
            "created_at": report.created_at.isoformat(),
            "source": report.source,
        }

    def _behavior_profile_summary(self, user_id: str) -> dict[str, Any]:
        pattern_count = self.db.scalar(select(func.count(BehaviorPattern.id)).where(BehaviorPattern.user_id == user_id)) or 0
        interventions = list(
            self.db.scalars(
                select(BehaviorIntervention)
                .where(BehaviorIntervention.user_id == user_id)
                .order_by(BehaviorIntervention.created_at.desc(), BehaviorIntervention.id.desc())
                .limit(50)
            ).all()
        )
        bypass_count = sum(1 for intervention in interventions if intervention.bypassed)
        block_count = sum(1 for intervention in interventions if intervention.intervention_level == "BLOCK")
        return {
            "pattern_count": int(pattern_count),
            "intervention_count": len(interventions),
            "bypassed_interventions": bypass_count,
            "block_interventions": block_count,
            "latest_intervention_level": interventions[0].intervention_level if interventions else None,
        }

    def _next_steps(
        self,
        detected_intent: str,
        outputs: dict[str, Any],
        order_intent: OrderIntent | None,
    ) -> list[dict[str, Any]]:
        if order_intent is not None:
            return [
                {
                    "label": "Run decision gates",
                    "module": "decision_gates",
                    "entity_id": order_intent.id,
                    "params": {"order_intent": order_intent.id},
                },
                {
                    "label": "Create order draft",
                    "module": "order_drafts",
                    "entity_id": order_intent.id,
                    "params": {"order_intent": order_intent.id},
                },
            ]
        if detected_intent == "thesis_review":
            data_quality = outputs.get("thesis_review_tool", {}).get("data_quality", {})
            theses = outputs.get("thesis_review_tool", {}).get("theses", [])
            focus_params = {"focus_thesis": theses[0]["id"]} if len(theses) == 1 and theses[0].get("id") else {}
            return [
                {"label": "Review thesis context", "module": "investment_logic", "params": focus_params},
                {
                    "label": "Refresh data snapshot" if not data_quality.get("decision_ready") else "Run gates with current data",
                    "module": "ai_research",
                    "status": data_quality.get("status"),
                },
            ]
        if detected_intent == "behavior_pattern_review":
            return [
                {"label": "Inspect recurring patterns", "module": "investment_logic"},
                {"label": "Open monthly review", "module": "monthly_review"},
            ]
        if detected_intent == "portfolio_summary":
            return [
                {"label": "Inspect holdings by thesis", "module": "holdings"},
                {"label": "Check risk exposure", "module": "decision_gates"},
            ]
        if detected_intent == "order_draft_lookup":
            drafts = outputs.get("order_draft_lookup_tool", {}).get("order_drafts", [])
            focus_params = {"draft": drafts[0]["id"]} if len(drafts) == 1 and drafts[0].get("id") else {}
            return [{"label": "Open order drafts", "module": "order_drafts", "params": focus_params}]
        return [{"label": "Review workspace context", "module": "overview"}]

    def _write_audit_log(self, *, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="ai-command-bar",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )

    def _refresh(
        self,
        query: CommandQuery,
        result: CommandResult,
        tool_calls: list[CommandToolCall],
        order_intent: OrderIntent | None,
    ) -> None:
        self.db.refresh(query)
        self.db.refresh(result)
        for tool_call in tool_calls:
            self.db.refresh(tool_call)
        if order_intent:
            self.db.refresh(order_intent)


def normalize(raw_query: str) -> str:
    return " ".join(raw_query.lower().strip().split())


def is_execution_request(normalized_query: str) -> bool:
    return any(keyword in normalized_query for keyword in EXECUTION_KEYWORDS)


def looks_like_order_intent_request(normalized_query: str) -> bool:
    return any(keyword in normalized_query for keyword in {"order intent", "draft buy", "draft sell", "生成订单意图", "创建订单意图"})


def detect_intent(normalized_query: str) -> str:
    if any(keyword in normalized_query for keyword in {"if ", "scenario", "跌", "涨", "如果"}):
        return "scenario_analysis"
    if any(keyword in normalized_query for keyword in {"monthly", "这个月", "月度", "复盘"}):
        return "monthly_decision_review"
    if any(keyword in normalized_query for keyword in {"thesis review", "买入逻辑", "原来的逻辑", "thesis for", "复核 thesis"}):
        return "thesis_review"
    if any(keyword in normalized_query for keyword in {"capture thesis", "记录 thesis", "捕捉 thesis", "生成 thesis"}):
        return "thesis_capture"
    if any(keyword in normalized_query for keyword in {"risk", "exposure", "风险", "敞口", "亏多少"}):
        return "risk_exposure"
    if any(keyword in normalized_query for keyword in {"position", "holding", "持仓", "仓位"}):
        return "position_lookup"
    if any(keyword in normalized_query for keyword in {"portfolio", "组合", "持仓总结", "summary"}):
        return "portfolio_summary"
    if any(keyword in normalized_query for keyword in {"news", "新闻", "market news", "市场消息"}):
        return "market_news_summary"
    if any(keyword in normalized_query for keyword in {"signal", "signals", "信号"}):
        return "signal_lookup"
    if any(keyword in normalized_query for keyword in {"behavior", "冲动", "fomo", "pattern", "行为"}):
        return "behavior_pattern_review"
    if any(keyword in normalized_query for keyword in {"order draft", "draft", "订单草稿"}):
        return "order_draft_lookup"
    return "portfolio_summary"


def tools_for_intent(intent: str) -> list[str]:
    mapping = {
        "portfolio_summary": ["portfolio_summary_tool"],
        "position_lookup": ["position_lookup_tool"],
        "risk_exposure": ["risk_exposure_tool"],
        "thesis_review": ["thesis_review_tool"],
        "thesis_capture": ["thesis_capture_tool"],
        "market_news_summary": ["market_news_summary_tool"],
        "signal_lookup": ["signal_lookup_tool"],
        "behavior_pattern_review": ["behavior_pattern_review_tool"],
        "monthly_decision_review": ["monthly_decision_review_tool"],
        "order_draft_lookup": ["order_draft_lookup_tool"],
        "scenario_analysis": ["scenario_analysis_tool"],
    }
    return mapping.get(intent, ["portfolio_summary_tool"])


def data_sources_for(intent: str, data_snapshot_id: str | None, tool_calls: list[CommandToolCall]) -> dict[str, Any]:
    uses_snapshot = intent in {"portfolio_summary", "position_lookup", "risk_exposure", "scenario_analysis", "signal_lookup"}
    return {
        "data_snapshot_id": data_snapshot_id or ("unavailable" if uses_snapshot else "not_required"),
        "tools": [tool_call.tool_name for tool_call in tool_calls],
        "structured_input_only": True,
    }


def infer_side(normalized_query: str) -> str:
    if any(keyword in normalized_query for keyword in {"sell", "卖"}):
        return "sell"
    return "buy"


def infer_symbol(raw_query: str) -> str | None:
    for token in raw_query.replace("，", " ").replace(",", " ").replace("？", " ").replace("?", " ").split():
        cleaned = token.strip().upper()
        if cleaned.isalpha() and 2 <= len(cleaned) <= 6:
            return cleaned
    return None


def infer_shock_pct(raw_query: str) -> float | None:
    normalized_query = raw_query.replace("％", "%")
    sign = -1 if any(keyword in normalized_query for keyword in {"跌", "down", "drop", "falls", "fall"}) else 1
    for token in normalized_query.replace(",", " ").replace("，", " ").split():
        if token.endswith("%"):
            try:
                return sign * abs(float(token[:-1]) / 100)
            except ValueError:
                continue
    return None
