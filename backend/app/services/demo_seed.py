from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log as write_domain_audit_log
from app.api.self_logic import write_audit_log as write_self_logic_audit_log
from app.models import Account
from app.models import Asset
from app.models import AutomationPolicy
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import DecisionGate
from app.models import Execution
from app.models import InvestmentConstitution
from app.models import InvestmentThesis
from app.models import MonthlyDecisionReview
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PortfolioSnapshot
from app.models import Position
from app.models import PostTradeReview
from app.models import ResearchReport
from app.models import RiskBudget
from app.models import StrategyPlaybook
from app.models import WorkflowState
from app.services.data_sources import DataSourceService
from app.services.decision_gates import DecisionGateService
from app.services.monthly_reviews import MonthlyDecisionReviewService
from app.services.paper_execution import PaperExecutionService
from app.services.portfolio import PortfolioSnapshotService
from app.services.risk import RiskEngineService
from app.services.workflows import WorkflowEngine

DEMO_USER_ID = "demo-user"
DEMO_ACCOUNT_NAME = "demo_primary_paper_account"
DEMO_PENDING_SOURCE_ID = "demo:pending-approval"
DEMO_REVIEW_SOURCE_ID = "demo:review-sample"
DEMO_REJECTED_SOURCE_ID = "demo:execution-rejected"
DEMO_BLOCKED_SOURCE_ID = "demo:gate-blocked"
DEMO_DATA_WARNING_SOURCE = "demo_seed_warning"
DEMO_AUTOMATION_LEVEL = "A3_ORDER_DRAFT"


@dataclass(frozen=True)
class DemoStepStatus:
    key: str
    module: str
    label: str
    status: str
    detail: str
    action_label: str
    action_detail: str
    blockers: list[str]


@dataclass(frozen=True)
class DemoStatusPayload:
    seeded: bool
    last_data_update_at: datetime | None
    data_quality_status: str
    global_risk_status: str
    automation_level: str
    current_workflow_stage: str
    next_workflow_stage: str | None
    counts: dict[str, int]
    steps: list[DemoStepStatus]


class DemoSeedService:
    def __init__(self, db: Session):
        self.db = db

    def seed(self) -> DemoStatusPayload:
        data_service = DataSourceService(self.db)
        data_service.ensure_default_connections()
        data_service.ensure_readonly_account_placeholders()
        market_snapshot = self._ensure_market_data_snapshot(data_service)
        low_quality_snapshot = self._ensure_low_quality_snapshot()
        self._ensure_low_quality_sample(low_quality_snapshot.id if low_quality_snapshot else None)

        account = self._ensure_account()
        aapl = self._ensure_asset(
            symbol="AAPL",
            name="Apple Inc.",
            asset_type="stock",
            market="US",
            venue="NASDAQ",
            currency="USD",
        )
        nvda = self._ensure_asset(
            symbol="NVDA",
            name="NVIDIA Corp.",
            asset_type="stock",
            market="US",
            venue="NASDAQ",
            currency="USD",
        )
        spy = self._ensure_asset(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            asset_type="etf",
            market="US",
            venue="NYSEARCA",
            currency="USD",
        )

        self._ensure_position(account, aapl, quantity=12, average_cost=180, market_price=225.12)
        self._ensure_position(account, nvda, quantity=4, average_cost=1120, market_price=1095.40)
        self._ensure_position(account, spy, quantity=6, average_cost=520.10, market_price=531.55)
        # The walkthrough's 100k Paper portfolio must be backed by an explicit
        # simulated cash ledger, not by risk request fields claiming equity.
        invested = sum((Decimal(str(p.market_value)) for p in self.db.scalars(
            select(Position).where(Position.account_id == account.id)).all()), Decimal("0"))
        PaperExecutionService(self.db)._get_or_create_cash_position(
            account, seed_if_missing=max(Decimal("0"), Decimal("100000") - invested))
        self.db.commit()
        self._ensure_portfolio_snapshot()

        constitution = self._ensure_constitution()
        playbook = self._ensure_playbook()
        self._ensure_risk_budget(constitution, account)
        thesis = self._ensure_thesis(account, aapl, playbook)
        self._ensure_thesis(account, nvda, playbook)
        self._ensure_thesis(account, spy, playbook)
        policy = self._ensure_automation_policy(account, aapl, playbook)
        nvda_policy = self._ensure_automation_policy(account, nvda, playbook)
        self._ensure_research_report(snapshot_id=market_snapshot.id if market_snapshot else "demo-snapshot", asset=nvda)
        self._ensure_research_report(snapshot_id=market_snapshot.id if market_snapshot else "demo-snapshot", asset=aapl)

        pending_intent = self._ensure_order_intent(
            source_id=DEMO_PENDING_SOURCE_ID,
            account=account,
            asset=aapl,
            thesis=thesis,
            playbook=playbook,
            policy=policy,
            side="buy",
            order_type="limit",
            quantity=2,
            notional=450.24,
            limit_price=225.12,
            rationale="Demo approval path: thesis-backed paper entry for the official walkthrough.",
            user_rationale="Walk the gated paper workflow before any live execution exists.",
        )
        pending_draft = self._ensure_passing_draft(
            order_intent=pending_intent,
            snapshot_id=market_snapshot.id if market_snapshot else "demo-snapshot",
            current_position_pct=0.06,
            order_position_pct=0.02,
            exchange_pct=0.05,
        )
        self._ensure_workflow_path(pending_intent.id, "USER_APPROVAL_REQUIRED")

        review_intent = self._ensure_order_intent(
            source_id=DEMO_REVIEW_SOURCE_ID,
            account=account,
            asset=aapl,
            thesis=thesis,
            playbook=playbook,
            policy=policy,
            side="buy",
            order_type="market",
            quantity=1,
            notional=225.12,
            limit_price=None,
            rationale="Demo review sample: already executed paper trade for journal and monthly review.",
            user_rationale="Keep one finished sample trade for journal and review demos.",
        )
        review_draft = self._ensure_passing_draft(
            order_intent=review_intent,
            snapshot_id=market_snapshot.id if market_snapshot else "demo-snapshot",
            current_position_pct=0.03,
            order_position_pct=0.01,
            exchange_pct=0.05,
        )
        self._ensure_approved(review_draft, approver_id="demo-approver", reason="Seeded paper review sample.")
        review_record = self._ensure_paper_execution(
            review_draft,
            fill_price=225.12,
            fill_quantity=1,
            approver_id="demo-approver",
            reason="Seeded paper review sample.",
        )
        self._ensure_completed_review(review_record, note="Seeded completed post-trade review for demo journal.")
        self._ensure_workflow_path(review_intent.id, "POST_TRADE_REVIEWED")

        rejected_intent = self._ensure_order_intent(
            source_id=DEMO_REJECTED_SOURCE_ID,
            account=account,
            asset=nvda,
            thesis=None,
            playbook=playbook,
            policy=nvda_policy,
            side="sell",
            order_type="limit",
            quantity=1,
            notional=1095.40,
            limit_price=1095.40,
            rationale="Demo rejected execution sample for the execution blocker state.",
            user_rationale="Operator rejected this sample to preserve the core thesis.",
        )
        rejected_draft = self._ensure_passing_draft(
            order_intent=rejected_intent,
            snapshot_id=market_snapshot.id if market_snapshot else "demo-snapshot",
            current_position_pct=0.11,
            order_position_pct=0.01,
            exchange_pct=0.05,
        )
        self._ensure_behavior_pattern_and_intervention(rejected_intent)
        self._ensure_rejected(rejected_draft, approver_id="risk-committee", reason="Seeded rejected sample for execution blocker demo.")
        self._ensure_workflow_path(rejected_intent.id, "REJECTED")

        blocked_intent = self._ensure_order_intent(
            source_id=DEMO_BLOCKED_SOURCE_ID,
            account=account,
            asset=nvda,
            thesis=None,
            playbook=playbook,
            policy=nvda_policy,
            side="buy",
            order_type="market",
            quantity=1,
            notional=1095.40,
            limit_price=None,
            rationale="",
            user_rationale=None,
        )
        self._ensure_blocked_gates(blocked_intent)
        self._ensure_workflow_path(blocked_intent.id, "BLOCKED")

        self._ensure_monthly_review_sample()
        self.db.commit()
        return self.build_status()

    def build_status(self) -> DemoStatusPayload:
        positions = list(self.db.scalars(select(Position)).all())
        assets = {asset.id: asset for asset in self.db.scalars(select(Asset)).all()}
        theses = list(self.db.scalars(select(InvestmentThesis)).all())
        drafts = list(self.db.scalars(select(OrderDraft)).all())
        reviews = list(self.db.scalars(select(PostTradeReview)).all())
        monthly_reviews = list(self.db.scalars(select(MonthlyDecisionReview)).all())
        quality_reports = list(
            self.db.scalars(select(DataQualityReport).order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc())).all()
        )
        snapshots = list(
            self.db.scalars(select(DataSnapshot).order_by(DataSnapshot.as_of.desc(), DataSnapshot.id.desc())).all()
        )
        policies = list(self.db.scalars(select(AutomationPolicy).where(AutomationPolicy.is_active.is_(True))).all())

        holding_asset_ids = {
            position.asset_id
            for position in positions
            if assets.get(position.asset_id) and assets[position.asset_id].asset_type.lower() not in {"cash", "stablecoin"}
        }
        active_thesis_asset_ids = {
            thesis.asset_id
            for thesis in theses
            if thesis.status == "active"
        }
        missing_thesis_holdings = len(holding_asset_ids - active_thesis_asset_ids)
        blocked_gate_intents = len(self._blocked_gate_intents())
        rejected_drafts = sum(1 for draft in drafts if draft.approval_status == "rejected")
        low_quality_reports = sum(1 for report in quality_reports if float(report.score or 0) < 0.8)
        pending_reviews = sum(1 for review in reviews if review.status != "completed")
        approved_waiting_paper = sum(
            1 for draft in drafts if draft.approval_status == "approved" and draft.execution_status != "paper_filled"
        )
        paper_filled = sum(1 for draft in drafts if draft.execution_status == "paper_filled")
        official_draft = self._official_demo_draft()
        official_review = self.db.scalar(
            select(PostTradeReview).where(PostTradeReview.order_draft_id == official_draft.id).limit(1)
        ) if official_draft is not None else None

        latest_quality = quality_reports[0] if quality_reports else None
        if latest_quality is None:
            data_quality_status = "missing"
        elif float(latest_quality.score or 0) < 0.5:
            data_quality_status = "blocked"
        elif float(latest_quality.score or 0) < 0.8:
            data_quality_status = "warning"
        else:
            data_quality_status = "ok"

        official_gate_status = "complete" if official_draft is not None else ("warning" if active_thesis_asset_ids else "missing")
        if official_draft is not None and official_draft.approval_status == "rejected":
            global_risk_status = "blocked"
        elif missing_thesis_holdings > 0 or official_gate_status != "complete":
            global_risk_status = "warning"
        else:
            global_risk_status = "healthy"

        current_workflow_stage = self._current_workflow_stage(
            data_snapshots=snapshots,
            theses=theses,
            official_draft=official_draft,
            official_review=official_review,
        )
        next_workflow_stage = self._next_workflow_stage(current_workflow_stage)
        automation_level = policies[0].automation_level if policies else "A0_READ_ONLY"

        counts = {
            "holdings": len(holding_asset_ids),
            "theses": len(active_thesis_asset_ids),
            "drafts": len(drafts),
            "approved_drafts": sum(1 for draft in drafts if draft.approval_status == "approved"),
            "paper_filled_drafts": paper_filled,
            "pending_reviews": pending_reviews,
            "monthly_reviews": len(monthly_reviews),
            "missing_thesis_holdings": missing_thesis_holdings,
            "blocked_gate_intents": blocked_gate_intents,
            "rejected_drafts": rejected_drafts,
            "low_quality_reports": low_quality_reports,
        }

        steps = [
            DemoStepStatus(
                key="import_data",
                module="data_sources",
                label="Import data",
                status="complete" if snapshots else "missing",
                detail="Read-only data connections created and quote snapshots imported." if snapshots else "Run demo import first.",
                action_label="Review data quality" if snapshots else "Run demo seed",
                action_detail=(
                    "Open data sources and inspect the latest read-only snapshot before trusting downstream gates."
                    if snapshots
                    else "Seed the official walkthrough to create read-only data, holdings, thesis, gates, drafts, and review samples."
                ),
                blockers=[] if snapshots else ["no_data_snapshot"],
            ),
            DemoStepStatus(
                key="holdings",
                module="holdings",
                label="Holdings",
                status="complete" if holding_asset_ids else "missing",
                detail=(
                    f"{len(holding_asset_ids)} tracked holding(s); all official demo holdings have thesis coverage."
                    if holding_asset_ids and missing_thesis_holdings == 0
                    else f"{len(holding_asset_ids)} tracked holding(s); {missing_thesis_holdings} still lack thesis coverage."
                ),
                action_label="Review thesis coverage" if holding_asset_ids else "Import holdings",
                action_detail="Open holdings and confirm each non-cash position has an active thesis before drafting orders.",
                blockers=[f"{missing_thesis_holdings}_holding_thesis_missing"] if missing_thesis_holdings else [],
            ),
            DemoStepStatus(
                key="thesis",
                module="investment_logic",
                label="Thesis",
                status="complete" if active_thesis_asset_ids else "missing",
                detail=f"{len(active_thesis_asset_ids)} active thesis record(s) linked to the demo portfolio.",
                action_label="Open thesis workspace" if active_thesis_asset_ids else "Create thesis",
                action_detail="Review entry reasons, invalidation conditions, and current thesis status before allowing gates.",
                blockers=[] if active_thesis_asset_ids else ["active_thesis_missing"],
            ),
            DemoStepStatus(
                key="gates",
                module="decision_gates",
                label="Decision gates",
                status="complete" if official_draft is not None else "missing",
                detail="Official happy-path gates are passing for the walkthrough draft." if official_draft is not None else "Generate the official draft to validate all five gates.",
                action_label="Inspect gate chain" if official_draft is not None else "Run gates",
                action_detail="Review Research, Thesis, Risk, Behavior, and Execution gates plus the preserved blocked sample.",
                blockers=[f"{blocked_gate_intents}_blocked_gate_sample"] if blocked_gate_intents else [],
            ),
            DemoStepStatus(
                key="draft",
                module="order_drafts",
                label="Draft",
                status="complete" if official_draft is not None else "missing",
                detail="The official walkthrough draft is ready in the execution workspace." if official_draft is not None else "Create the official walkthrough draft after gates pass.",
                action_label="Open draft" if official_draft is not None else "Create draft",
                action_detail="Inspect the draft, linked thesis, gate output, risk check, and approval state before taking action.",
                blockers=[] if official_draft is not None else ["official_draft_missing"],
            ),
            DemoStepStatus(
                key="approve",
                module="order_drafts",
                label="Approve",
                status="ready" if official_draft is not None and official_draft.approval_status == "pending" else "complete",
                detail=(
                    "Approve the pending official demo draft to continue the walkthrough."
                    if official_draft is not None and official_draft.approval_status == "pending"
                    else "The official walkthrough draft has already been approved."
                ),
                action_label="Approve draft" if official_draft is not None and official_draft.approval_status == "pending" else "Review approval",
                action_detail="Human approval is required before any paper fill; live execution remains unavailable.",
                blockers=[] if official_draft is not None else ["official_draft_missing"],
            ),
            DemoStepStatus(
                key="paper_execute",
                module="order_drafts",
                label="Paper execute",
                status="ready" if official_draft is not None and official_draft.approval_status == "approved" and official_draft.execution_status != "paper_filled" else ("complete" if official_draft is not None and official_draft.execution_status == "paper_filled" else "pending"),
                detail=(
                    "An approved official draft is waiting for paper execution."
                    if official_draft is not None and official_draft.approval_status == "approved" and official_draft.execution_status != "paper_filled"
                    else "The official walkthrough already includes a paper execution record."
                    if official_draft is not None and official_draft.execution_status == "paper_filled"
                    else "Approve the official draft first, then execute it in paper mode."
                ),
                action_label=(
                    "Paper fill draft"
                    if official_draft is not None and official_draft.approval_status == "approved" and official_draft.execution_status != "paper_filled"
                    else "Review paper fill"
                    if official_draft is not None and official_draft.execution_status == "paper_filled"
                    else "Approve first"
                ),
                action_detail="Paper fill updates simulated cash/position state and creates a post-trade review prompt.",
                blockers=(
                    ["approval_required"]
                    if official_draft is not None and official_draft.approval_status == "pending"
                    else ["official_draft_missing"]
                    if official_draft is None
                    else []
                ),
            ),
            DemoStepStatus(
                key="journal",
                module="trade_journal",
                label="Journal",
                status="complete" if official_review is not None and official_review.status == "completed" else ("ready" if official_review is not None else "pending"),
                detail=(
                    "The official walkthrough trade has already been journaled and reviewed."
                    if official_review is not None and official_review.status == "completed"
                    else "The official walkthrough trade is ready for journal review."
                    if official_review is not None
                    else "Paper-execute the official draft first, then review it in the journal."
                ),
                action_label="Complete review" if official_review is not None and official_review.status != "completed" else "Open journal",
                action_detail="Close the review loop before using the trade as evidence for monthly review or playbook changes.",
                blockers=[] if official_review is not None else ["paper_execution_required"],
            ),
            DemoStepStatus(
                key="monthly_review",
                module="monthly_review",
                label="Monthly review",
                status="complete" if official_review is not None and official_review.status == "completed" and monthly_reviews else ("ready" if official_review is not None and official_review.status == "completed" else "pending"),
                detail=(
                    "A monthly review sample is ready once the official trade review is complete."
                    if monthly_reviews and official_review is not None and official_review.status == "completed"
                    else "Generate the monthly decision review after the official journal step."
                ),
                action_label=(
                    "Generate review"
                    if official_review is not None and official_review.status == "completed" and not monthly_reviews
                    else "Open monthly review"
                ),
                action_detail="Use completed journal evidence to summarize decision quality and suggest manual playbook updates.",
                blockers=(
                    ["journal_review_required"]
                    if official_review is None or official_review.status != "completed"
                    else []
                ),
            ),
        ]

        return DemoStatusPayload(
            seeded=bool(holding_asset_ids or theses or drafts),
            last_data_update_at=snapshots[0].as_of if snapshots else None,
            data_quality_status=data_quality_status,
            global_risk_status=global_risk_status,
            automation_level=automation_level,
            current_workflow_stage=current_workflow_stage,
            next_workflow_stage=next_workflow_stage,
            counts=counts,
            steps=steps,
        )

    def _ensure_market_data_snapshot(self, data_service: DataSourceService) -> DataSnapshot | None:
        latest = self.db.scalar(
            select(DataSnapshot)
            .where(DataSnapshot.snapshot_type == "market_quotes")
            .order_by(DataSnapshot.as_of.desc(), DataSnapshot.id.desc())
            .limit(1)
        )
        if latest is not None:
            return latest

        connection = next(
            (
                item
                for item in data_service.list_connections()
                if item.provider == "mock_market_data"
            ),
            None,
        )
        if connection is None:
            return None

        result = data_service.import_quotes(
            connection.id,
            symbols=["AAPL", "NVDA", "SPY"],
            asset_type="stock",
            market="US",
            currency="USD",
        )
        return result.snapshot

    def _ensure_low_quality_snapshot(self) -> DataSnapshot:
        existing = self.db.scalar(
            select(DataSnapshot)
            .where(DataSnapshot.snapshot_type == "demo_low_quality_market_quotes")
            .limit(1)
        )
        if existing is not None:
            return existing

        snapshot = DataSnapshot(
            snapshot_type="demo_low_quality_market_quotes",
            as_of=datetime.now(timezone.utc),
            data_json={
                "quotes": [
                    {"symbol": "AAPL", "source": "demo_seed"},
                    {"symbol": "NVDA", "source": "demo_seed"},
                ],
                "skipped": [
                    {"symbol": "DEMO_BAD_SYMBOL", "error": "symbol_not_found"},
                    {"symbol": "DEMO_DELAYED", "error": "timestamp_stale"},
                ],
            },
            metadata_json={
                "mode": "read_only",
                "source_type": "market_data",
                "demo_seed": True,
                "purpose": "data_quality_blocker_sample",
                "symbols_requested": ["AAPL", "NVDA", "DEMO_BAD_SYMBOL", "DEMO_DELAYED"],
            },
        )
        self.db.add(snapshot)
        self.db.flush()
        write_domain_audit_log(
            self.db,
            action="demo_seed.low_quality_snapshot_created",
            entity_type="DataSnapshot",
            entity_id=snapshot.id,
            payload_json={"snapshot_type": snapshot.snapshot_type},
            actor_id="demo-seed",
        )
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def _ensure_low_quality_sample(self, snapshot_id: str | None) -> DataQualityReport:
        existing = self.db.scalar(
            select(DataQualityReport)
            .where(DataQualityReport.source == DEMO_DATA_WARNING_SOURCE)
            .limit(1)
        )
        if existing is not None:
            if snapshot_id is not None and existing.data_snapshot_id != snapshot_id:
                existing.data_snapshot_id = snapshot_id
                self.db.add(existing)
                write_domain_audit_log(
                    self.db,
                    action="demo_seed.data_quality_warning_relinked",
                    entity_type="DataQualityReport",
                    entity_id=existing.id,
                    payload_json={"source": existing.source, "snapshot_id": snapshot_id},
                    actor_id="demo-seed",
                )
                self.db.commit()
                self.db.refresh(existing)
            return existing

        report = DataQualityReport(
            data_snapshot_id=snapshot_id,
            source=DEMO_DATA_WARNING_SOURCE,
            metric_type="quote_import_completeness",
            score=Decimal("0.55"),
            details_json={
                "requested": 4,
                "imported": 2,
                "skipped": ["DEMO_BAD_SYMBOL", "DEMO_DELAYED"],
                "note": "Seeded warning sample for the data-quality blocker demo.",
            },
        )
        self.db.add(report)
        self.db.flush()
        write_domain_audit_log(
            self.db,
            action="demo_seed.data_quality_warning_created",
            entity_type="DataQualityReport",
            entity_id=report.id,
            payload_json={"source": report.source, "score": float(report.score)},
            actor_id="demo-seed",
        )
        self.db.commit()
        self.db.refresh(report)
        return report

    def _ensure_account(self) -> Account:
        existing = self.db.scalar(select(Account).where(Account.name == DEMO_ACCOUNT_NAME).limit(1))
        if existing is not None:
            return existing

        account = Account(
            name=DEMO_ACCOUNT_NAME,
            account_type="brokerage",
            broker="demo_seed",
            base_currency="USD",
            mode="paper",
            live_trading_enabled=False,
        )
        self.db.add(account)
        self.db.flush()
        write_domain_audit_log(
            self.db,
            action="demo_seed.account_created",
            entity_type="Account",
            entity_id=account.id,
            payload_json={"name": account.name},
            actor_id="demo-seed",
        )
        self.db.commit()
        self.db.refresh(account)
        return account

    def _ensure_asset(
        self,
        *,
        symbol: str,
        name: str,
        asset_type: str,
        market: str,
        venue: str,
        currency: str,
    ) -> Asset:
        existing = self.db.scalar(select(Asset).where(Asset.symbol == symbol).limit(1))
        if existing is not None:
            existing.name = name
            existing.asset_type = asset_type
            existing.market = market
            existing.venue = venue
            existing.currency = currency
            existing.tradable = True
            existing.manual_enabled = True
            existing.auto_enabled = False
            existing.risk_level = "medium"
            self.db.commit()
            self.db.refresh(existing)
            return existing

        asset = Asset(
            symbol=symbol,
            name=name,
            asset_type=asset_type,
            market=market,
            venue=venue,
            currency=currency,
            tradable=True,
            manual_enabled=True,
            auto_enabled=False,
            risk_level="medium",
        )
        self.db.add(asset)
        self.db.flush()
        write_domain_audit_log(
            self.db,
            action="demo_seed.asset_created",
            entity_type="Asset",
            entity_id=asset.id,
            payload_json={"symbol": asset.symbol},
            actor_id="demo-seed",
        )
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def _ensure_position(
        self,
        account: Account,
        asset: Asset,
        *,
        quantity: float,
        average_cost: float,
        market_price: float,
    ) -> Position:
        existing = self.db.scalar(
            select(Position).where(Position.account_id == account.id, Position.asset_id == asset.id).limit(1)
        )
        market_value = Decimal(str(quantity)) * Decimal(str(market_price))
        unrealized_pnl = (Decimal(str(market_price)) - Decimal(str(average_cost))) * Decimal(str(quantity))
        weight = 0.0

        if existing is None:
            position = Position(
                account_id=account.id,
                asset_id=asset.id,
                quantity=quantity,
                average_cost=average_cost,
                market_price=market_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=0,
                weight=weight,
            )
            self.db.add(position)
            self.db.flush()
            write_domain_audit_log(
                self.db,
                action="demo_seed.position_created",
                entity_type="Position",
                entity_id=position.id,
                payload_json={"asset_id": asset.id, "quantity": quantity},
                actor_id="demo-seed",
            )
            self.db.commit()
            self.db.refresh(position)
            return position

        existing.quantity = quantity
        existing.average_cost = average_cost
        existing.market_price = market_price
        existing.market_value = market_value
        existing.unrealized_pnl = unrealized_pnl
        self.db.commit()
        self.db.refresh(existing)
        return existing

    def _ensure_portfolio_snapshot(self) -> PortfolioSnapshot:
        existing = self.db.scalar(select(PortfolioSnapshot).order_by(PortfolioSnapshot.created_at.desc()).limit(1))
        if existing is not None:
            return existing
        return PortfolioSnapshotService(self.db).create_snapshot()

    def _ensure_constitution(self) -> InvestmentConstitution:
        existing = self.db.scalar(
            select(InvestmentConstitution)
            .where(InvestmentConstitution.user_id == DEMO_USER_ID, InvestmentConstitution.name == "Demo Constitution")
            .limit(1)
        )
        if existing is not None:
            return existing

        constitution = InvestmentConstitution(
            user_id=DEMO_USER_ID,
            version="v1",
            name="Demo Constitution",
            investment_style="disciplined",
            allowed_markets=["US"],
            forbidden_assets=[],
            forbidden_actions=["LIVE_EXECUTION"],
            max_single_position_pct=0.2,
            max_asset_class_pct=0.9,
            max_crypto_pct=0.2,
            max_single_exchange_pct=0.5,
            max_daily_loss_pct=0.03,
            max_monthly_drawdown_pct=0.1,
            leverage_allowed=False,
            derivatives_allowed=False,
            auto_execution_allowed=False,
            human_approval_required=True,
            cooldown_rules_json={"min_minutes_between_actions": 30},
            is_active=True,
        )
        self.db.add(constitution)
        self.db.flush()
        write_self_logic_audit_log(
            self.db,
            action="demo_seed.constitution_created",
            entity_type="InvestmentConstitution",
            entity_id=constitution.id,
            payload_json={"user_id": DEMO_USER_ID},
        )
        self.db.commit()
        self.db.refresh(constitution)
        return constitution

    def _ensure_risk_budget(self, constitution: InvestmentConstitution, account: Account) -> RiskBudget:
        budgets: dict[str, RiskBudget] = {}
        for asset_class in ("stock", "etf"):
            budget = self.db.scalar(
                select(RiskBudget)
                .where(
                    RiskBudget.user_id == DEMO_USER_ID,
                    RiskBudget.account_id == account.id,
                    RiskBudget.asset_class == asset_class,
                )
                .limit(1)
            )
            if budget is None:
                budget = RiskBudget(
                    user_id=DEMO_USER_ID,
                    constitution_id=constitution.id,
                    account_id=account.id,
                    asset_class=asset_class,
                    max_allocation_pct=0.8,
                    max_loss_pct=0.08,
                    max_order_notional=10_000,
                    max_leverage=1,
                    rebalance_threshold_pct=0.05,
                )
                self.db.add(budget)
                self.db.flush()
                write_self_logic_audit_log(
                    self.db,
                    action="demo_seed.risk_budget_created",
                    entity_type="RiskBudget",
                    entity_id=budget.id,
                    payload_json={"account_id": account.id, "asset_class": asset_class},
                )
            budgets[asset_class] = budget
        self.db.commit()
        for budget in budgets.values():
            self.db.refresh(budget)
        return budgets["stock"]

    def _ensure_playbook(self) -> StrategyPlaybook:
        existing = self.db.scalar(
            select(StrategyPlaybook)
            .where(StrategyPlaybook.user_id == DEMO_USER_ID, StrategyPlaybook.name == "Demo Quality Compounder")
            .limit(1)
        )
        if existing is not None:
            if existing.automation_level == "A2_ORDER_DRAFT":
                existing.automation_level = DEMO_AUTOMATION_LEVEL
                self.db.commit()
                self.db.refresh(existing)
            return existing

        playbook = StrategyPlaybook(
            user_id=DEMO_USER_ID,
            name="Demo Quality Compounder",
            strategy_type="fundamental_swing",
            applicable_markets=["US"],
            applicable_assets=["AAPL", "SPY", "NVDA"],
            entry_conditions_json={"requires_thesis": True, "requires_data_snapshot": True},
            exit_conditions_json={"revisit_on_thesis_break": True},
            risk_rules_json={"manual_review_rules": [], "max_single_position_pct": 0.2},
            automation_level=DEMO_AUTOMATION_LEVEL,
            requires_human_approval=True,
            is_active=True,
        )
        self.db.add(playbook)
        self.db.flush()
        write_self_logic_audit_log(
            self.db,
            action="demo_seed.playbook_created",
            entity_type="StrategyPlaybook",
            entity_id=playbook.id,
            payload_json={"name": playbook.name},
        )
        self.db.commit()
        self.db.refresh(playbook)
        return playbook

    def _ensure_thesis(self, account: Account, asset: Asset, playbook: StrategyPlaybook) -> InvestmentThesis:
        existing = self.db.scalar(
            select(InvestmentThesis)
            .where(InvestmentThesis.user_id == DEMO_USER_ID, InvestmentThesis.asset_id == asset.id)
            .order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc())
            .limit(1)
        )
        if existing is not None:
            return existing

        thesis_profiles = {
            "AAPL": {
                "entry_reason": "Own AAPL while services attach rate and buyback discipline keep free-cash-flow compounding intact.",
                "key_drivers": {"items": ["services_attach", "buybacks", "margin_resilience"]},
                "invalidation_conditions": {"items": ["gross_margin_break", "services_growth_stalls"]},
                "target_condition": "Review after the next earnings print or a 10% thesis drawdown.",
                "confidence": 0.77,
            },
            "NVDA": {
                "entry_reason": "Keep NVDA as long as accelerated-compute demand and data-center margins continue to support the AI infrastructure thesis.",
                "key_drivers": {"items": ["data_center_growth", "ai_compute_demand", "gross_margin_discipline"]},
                "invalidation_conditions": {"items": ["hyperscaler_capex_rollover", "margin_compression", "inventory_glut"]},
                "target_condition": "Review after the next earnings print or a sharp guide-down in data-center growth.",
                "confidence": 0.74,
            },
            "SPY": {
                "entry_reason": "Use SPY as the broad-market beta sleeve while macro liquidity and earnings breadth remain constructive.",
                "key_drivers": {"items": ["index_breadth", "earnings_revision_trend", "macro_liquidity"]},
                "invalidation_conditions": {"items": ["breadth_breakdown", "earnings_revision_collapse"]},
                "target_condition": "Reassess if broad-market trend breaks or macro regime changes materially.",
                "confidence": 0.68,
            },
        }
        profile = thesis_profiles.get(asset.symbol, thesis_profiles["AAPL"])

        thesis = InvestmentThesis(
            user_id=DEMO_USER_ID,
            asset_id=asset.id,
            account_id=account.id,
            strategy_playbook_id=playbook.id,
            entry_reason=profile["entry_reason"],
            key_drivers_json=profile["key_drivers"],
            invalidation_conditions_json=profile["invalidation_conditions"],
            expected_horizon="swing",
            target_condition=profile["target_condition"],
            max_loss_tolerance_pct=0.08,
            position_plan_json={"max_weight": 0.12, "add_only_on_evidence": True},
            confidence=profile["confidence"],
            source="demo_seed",
            status="active",
        )
        self.db.add(thesis)
        self.db.flush()
        write_self_logic_audit_log(
            self.db,
            action="demo_seed.thesis_created",
            entity_type="InvestmentThesis",
            entity_id=thesis.id,
            payload_json={"asset_id": asset.id},
        )
        self.db.commit()
        self.db.refresh(thesis)
        return thesis

    def _ensure_automation_policy(self, account: Account, asset: Asset, playbook: StrategyPlaybook) -> AutomationPolicy:
        existing = self.db.scalar(
            select(AutomationPolicy)
            .where(
                AutomationPolicy.user_id == DEMO_USER_ID,
                AutomationPolicy.account_id == account.id,
                AutomationPolicy.asset_id == asset.id,
                AutomationPolicy.is_active.is_(True),
            )
            .limit(1)
        )
        if existing is not None:
            if existing.automation_level == "A2_ORDER_DRAFT":
                existing.automation_level = DEMO_AUTOMATION_LEVEL
                self.db.commit()
                self.db.refresh(existing)
            return existing

        policy = AutomationPolicy(
            user_id=DEMO_USER_ID,
            account_id=account.id,
            asset_id=asset.id,
            strategy_playbook_id=playbook.id,
            automation_level=DEMO_AUTOMATION_LEVEL,
            max_notional_per_order=5_000,
            max_orders_per_day=2,
            requires_approval=True,
            allowed_actions=["CREATE_ORDER_DRAFT"],
            forbidden_actions=["LIVE_EXECUTION"],
            is_active=True,
        )
        self.db.add(policy)
        self.db.flush()
        write_self_logic_audit_log(
            self.db,
            action="demo_seed.automation_policy_created",
            entity_type="AutomationPolicy",
            entity_id=policy.id,
            payload_json={"asset_id": asset.id},
        )
        self.db.commit()
        self.db.refresh(policy)
        return policy

    def _ensure_research_report(self, *, snapshot_id: str, asset: Asset) -> ResearchReport:
        existing = self.db.scalar(
            select(ResearchReport)
            .where(ResearchReport.data_snapshot_id == snapshot_id, ResearchReport.asset_id == asset.id)
            .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())
            .limit(1)
        )
        if existing is not None:
            return existing

        report = ResearchReport(
            report_type="single_asset_research",
            agent_name="demo_seed",
            data_snapshot_id=snapshot_id,
            asset_id=asset.id,
            input_facts={"asset": asset.symbol, "snapshot_id": snapshot_id},
            summary=f"{asset.symbol} deterministic research fixture inside the paper-only demo environment.",
            bullish_case="Synthetic favorable scenario: business growth supports the fixture thesis.",
            bearish_case="Synthetic adverse scenario: margin pressure could weaken the fixture thesis.",
            key_risks={"items": ["valuation", "macro slowdown"]},
            suggested_action="review_only",
            confidence=0.84,
            evidence={"snapshot_id": snapshot_id, "source": "demo_seed"},
            limitations="Demo report only; read-only market data with deterministic content.",
        )
        self.db.add(report)
        self.db.flush()
        write_domain_audit_log(
            self.db,
            action="demo_seed.research_report_created",
            entity_type="ResearchReport",
            entity_id=report.id,
            payload_json={"asset_id": asset.id, "snapshot_id": snapshot_id},
            actor_id="demo-seed",
        )
        self.db.commit()
        self.db.refresh(report)
        return report

    def _ensure_order_intent(
        self,
        *,
        source_id: str,
        account: Account,
        asset: Asset,
        thesis: InvestmentThesis | None,
        playbook: StrategyPlaybook,
        policy: AutomationPolicy,
        side: str,
        order_type: str,
        quantity: float | None,
        notional: float | None,
        limit_price: float | None,
        rationale: str,
        user_rationale: str | None,
    ) -> OrderIntent:
        existing = self.db.scalar(select(OrderIntent).where(OrderIntent.source_id == source_id).limit(1))
        if existing is not None:
            return existing

        intent = OrderIntent(
            source_type="demo_seed",
            source_id=source_id,
            asset_id=asset.id,
            account_id=account.id,
            investment_thesis_id=thesis.id if thesis else None,
            strategy_playbook_id=playbook.id,
            automation_policy_id=policy.id,
            side=side,
            order_type=order_type,
            quantity=quantity,
            notional=notional,
            limit_price=limit_price,
            rationale=rationale,
            user_rationale=user_rationale,
            status="created",
        )
        self.db.add(intent)
        self.db.flush()
        write_domain_audit_log(
            self.db,
            action="demo_seed.order_intent_created",
            entity_type="OrderIntent",
            entity_id=intent.id,
            payload_json={"source_id": source_id, "asset_id": asset.id},
            actor_id="demo-seed",
        )
        self.db.commit()
        self.db.refresh(intent)
        return intent

    def _ensure_passing_draft(
        self,
        *,
        order_intent: OrderIntent,
        snapshot_id: str,
        current_position_pct: float,
        order_position_pct: float,
        exchange_pct: float,
    ) -> OrderDraft:
        existing = self.db.scalar(select(OrderDraft).where(OrderDraft.order_intent_id == order_intent.id).limit(1))
        if existing is not None:
            return existing

        DecisionGateService(self.db).evaluate_order(
            order_intent.id,
            {
                "user_id": DEMO_USER_ID,
                "data_snapshot_id": snapshot_id,
                "data_quality_status": "ok",
                "current_position_pct": current_position_pct,
                "order_position_pct": order_position_pct,
                "asset_class_pct": 0.18,
                "exchange_pct": exchange_pct,
                "current_leverage": 0,
                "daily_loss_pct": 0.01,
                "monthly_drawdown_pct": 0.03,
                "execution_mode": "paper",
                "broker_status": "healthy",
                "exchange_status": "healthy",
                "expected_slippage_pct": 0.001,
            },
        )
        draft = RiskEngineService(self.db).create_draft_after_risk(
            order_intent,
            {
                "order_mode": "manual",
                "max_order_notional": 10_000,
                "max_position_pct": 0.2,
                "total_equity": 100_000,
                "current_position_value": 0,
                "account_daily_loss": 0,
                "max_daily_loss": 2_500,
                "current_leverage": 0,
                "max_leverage": 1,
                "liquidity_passed": True,
                "volatility": 0.18,
                "max_volatility": 1,
                "kill_switch": False,
            },
        )
        self.db.refresh(draft)
        return draft

    def _ensure_approved(self, draft: OrderDraft, *, approver_id: str, reason: str) -> None:
        if draft.approval_status == "approved":
            return
        RiskEngineService(self.db).approve_draft(draft, approver_id=approver_id, decision_reason=reason)
        self.db.refresh(draft)

    def _ensure_rejected(self, draft: OrderDraft, *, approver_id: str, reason: str) -> None:
        if draft.approval_status == "rejected":
            return
        RiskEngineService(self.db).reject_draft(draft, approver_id=approver_id, decision_reason=reason)
        self.db.refresh(draft)

    def _ensure_paper_execution(
        self,
        draft: OrderDraft,
        *,
        fill_price: float,
        fill_quantity: float,
        approver_id: str,
        reason: str,
    ) -> PostTradeReview:
        existing_review = self.db.scalar(select(PostTradeReview).where(PostTradeReview.order_draft_id == draft.id).limit(1))
        if existing_review is not None:
            return existing_review

        _, _, review, _, _, _ = PaperExecutionService(self.db).execute_draft(
            draft,
            approver_id=approver_id,
            decision_reason=reason,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            fee_bps=1,
            slippage_bps=0,
        )
        return review

    def _ensure_completed_review(self, review: PostTradeReview, *, note: str) -> PostTradeReview:
        if review.status == "completed":
            return review
        review.status = "completed"
        review.review_json = {"source": "demo_seed", "note": note}
        self.db.commit()
        self.db.refresh(review)
        return review

    def _ensure_behavior_pattern_and_intervention(self, intent: OrderIntent) -> None:
        pattern = self.db.scalar(
            select(BehaviorPattern)
            .where(BehaviorPattern.user_id == DEMO_USER_ID, BehaviorPattern.pattern_type == "OVERTRADING")
            .limit(1)
        )
        if pattern is None:
            pattern = BehaviorPattern(
                user_id=DEMO_USER_ID,
                pattern_type="OVERTRADING",
                description="Seeded demo pattern for the monthly review sample.",
                evidence_json={"source": "demo_seed"},
                estimated_cost=75,
                frequency=1,
                severity="high",
            )
            self.db.add(pattern)
            self.db.flush()

        intervention = self.db.scalar(
            select(BehaviorIntervention)
            .where(BehaviorIntervention.order_intent_id == intent.id)
            .limit(1)
        )
        if intervention is None:
            intervention = BehaviorIntervention(
                user_id=DEMO_USER_ID,
                pattern_id=pattern.id,
                order_intent_id=intent.id,
                intervention_level="HARD_CONFIRM",
                message="Seeded behavior warning for the rejected execution sample.",
                bypassed=True,
            )
            self.db.add(intervention)
            self.db.flush()
        self.db.commit()

    def _ensure_blocked_gates(self, intent: OrderIntent) -> None:
        existing = self.db.scalars(select(DecisionGate).where(DecisionGate.order_intent_id == intent.id)).all()
        if existing:
            return
        DecisionGateService(self.db).evaluate_order(
            intent.id,
            {
                "user_id": DEMO_USER_ID,
                "data_quality_status": "warning",
                "research_report_required": True,
                "execution_mode": "paper",
                "broker_status": "healthy",
                "exchange_status": "healthy",
                "source_timestamp_valid": False,
            },
        )

    def _ensure_monthly_review_sample(self) -> MonthlyDecisionReview:
        start = date.today().replace(day=1)
        end = date.today()
        existing = self.db.scalar(
            select(MonthlyDecisionReview)
            .where(
                MonthlyDecisionReview.user_id == DEMO_USER_ID,
                MonthlyDecisionReview.period_start == start,
                MonthlyDecisionReview.period_end == end,
            )
            .limit(1)
        )
        if existing is not None:
            return existing
        return MonthlyDecisionReviewService(self.db).generate(
            user_id=DEMO_USER_ID,
            period_start=start,
            period_end=end,
        ).review

    def _ensure_workflow_path(self, entity_id: str, target_state: str) -> None:
        timeline = list(
            self.db.scalars(
                select(WorkflowState)
                .where(WorkflowState.workflow_type == "demo_order", WorkflowState.entity_id == entity_id)
                .order_by(WorkflowState.created_at, WorkflowState.id)
            ).all()
        )
        if timeline:
            return

        engine = WorkflowEngine(self.db)
        workflow = engine.create_workflow("demo_order", entity_id, {"seeded_by": "demo_seed"})

        sequences: dict[str, list[tuple[str, str, dict[str, Any] | None]]] = {
            "USER_APPROVAL_REQUIRED": [
                ("DATA_COLLECTED", "Demo data import prepared.", None),
                ("RESEARCH_GENERATED", "Demo research snapshot attached.", None),
                ("THESIS_CREATED_OR_MATCHED", "Demo thesis linked.", None),
                ("SIGNAL_DETECTED", "Demo idea surfaced for review.", None),
                ("ORDER_INTENT_CREATED", "Demo order intent recorded.", None),
                ("RESEARCH_GATE_PASSED", "Research gate passed.", None),
                ("THESIS_GATE_PASSED", "Thesis gate passed.", None),
                ("RISK_GATE_PASSED", "Risk gate passed.", None),
                ("BEHAVIOR_GATE_PASSED", "Behavior gate passed.", None),
                ("EXECUTION_GATE_PASSED", "Execution gate passed.", None),
                ("ORDER_DRAFT_CREATED", "Draft created after gates.", None),
                ("USER_APPROVAL_REQUIRED", "Pending human approval.", None),
            ],
            "POST_TRADE_REVIEWED": [
                ("DATA_COLLECTED", "Demo data import prepared.", None),
                ("RESEARCH_GENERATED", "Demo research snapshot attached.", None),
                ("THESIS_CREATED_OR_MATCHED", "Demo thesis linked.", None),
                ("SIGNAL_DETECTED", "Demo idea surfaced for review.", None),
                ("ORDER_INTENT_CREATED", "Demo order intent recorded.", None),
                ("RESEARCH_GATE_PASSED", "Research gate passed.", None),
                ("THESIS_GATE_PASSED", "Thesis gate passed.", None),
                ("RISK_GATE_PASSED", "Risk gate passed.", None),
                ("BEHAVIOR_GATE_PASSED", "Behavior gate passed.", None),
                ("EXECUTION_GATE_PASSED", "Execution gate passed.", None),
                ("ORDER_DRAFT_CREATED", "Draft created after gates.", None),
                ("USER_APPROVAL_REQUIRED", "Pending human approval.", None),
                ("APPROVED", "Demo approval recorded.", None),
                ("PAPER_EXECUTED", "Paper execution recorded.", None),
                ("EXECUTION_CONFIRMED", "Execution captured.", None),
                ("JOURNAL_WRITTEN", "Trade journal written.", None),
                ("REVIEW_SCHEDULED", "Post-trade review created.", None),
                ("POST_TRADE_REVIEWED", "Seeded review completed.", None),
            ],
            "REJECTED": [
                ("DATA_COLLECTED", "Demo data import prepared.", None),
                ("RESEARCH_GENERATED", "Demo research snapshot attached.", None),
                ("THESIS_CREATED_OR_MATCHED", "Demo thesis logic checked.", None),
                ("SIGNAL_DETECTED", "Demo idea surfaced for review.", None),
                ("ORDER_INTENT_CREATED", "Demo order intent recorded.", None),
                ("RESEARCH_GATE_PASSED", "Research gate passed.", None),
                ("THESIS_GATE_PASSED", "Thesis gate passed with manual rationale.", None),
                ("RISK_GATE_PASSED", "Risk gate passed.", None),
                ("BEHAVIOR_GATE_PASSED", "Behavior gate passed with warning context.", None),
                ("EXECUTION_GATE_PASSED", "Execution gate passed.", None),
                ("ORDER_DRAFT_CREATED", "Draft created after gates.", None),
                ("USER_APPROVAL_REQUIRED", "Pending human approval.", None),
                ("REJECTED", "Seeded rejection sample.", None),
            ],
        }

        if target_state == "BLOCKED":
            for state, reason, metadata in [
                ("DATA_COLLECTED", "Demo data import prepared.", None),
                ("RESEARCH_GENERATED", "Demo research missing on purpose.", None),
                ("THESIS_CREATED_OR_MATCHED", "Missing thesis blocker sample.", None),
                ("SIGNAL_DETECTED", "Blocked sample reached gating.", None),
                ("ORDER_INTENT_CREATED", "Blocked sample order intent recorded.", None),
            ]:
                workflow = engine.transition(workflow.id, state, reason, metadata)
            engine.block_workflow(
                workflow.id,
                "Seeded blocker sample: thesis missing and data quality insufficient.",
                {"data_quality": "insufficient", "thesis": "missing"},
            )
            return

        for state, reason, metadata in sequences.get(target_state, []):
            workflow = engine.transition(workflow.id, state, reason, metadata)

    def _blocked_gate_intents(self) -> set[str]:
        latest: dict[str, dict[str, str]] = {}
        gates = self.db.scalars(select(DecisionGate).order_by(DecisionGate.created_at.desc(), DecisionGate.id.desc())).all()
        for gate in gates:
            order_intent_id = gate.order_intent_id
            if order_intent_id is None:
                continue
            intent_gates = latest.setdefault(order_intent_id, {})
            if gate.gate_type not in intent_gates:
                intent_gates[gate.gate_type] = gate.status
        return {
            order_intent_id
            for order_intent_id, statuses in latest.items()
            if any(status != "PASSED" for status in statuses.values())
        }

    def _current_workflow_stage(
        self,
        *,
        data_snapshots: list[DataSnapshot],
        theses: list[InvestmentThesis],
        official_draft: OrderDraft | None,
        official_review: PostTradeReview | None,
    ) -> str:
        if official_review is not None and official_review.status == "completed":
            return "monthly_review_ready"
        if official_review is not None:
            return "journal_review_pending"
        if official_draft is not None and official_draft.approval_status == "approved" and official_draft.execution_status != "paper_filled":
            return "approved_waiting_paper_execute"
        if official_draft is not None and official_draft.approval_status == "pending":
            return "draft_waiting_approval"
        if official_draft is not None:
            return "draft_created"
        if theses:
            return "gates_ready"
        if data_snapshots:
            return "thesis_ready"
        return "data_import_pending"

    def _next_workflow_stage(self, current_stage: str) -> str | None:
        mapping = {
            "data_import_pending": "thesis_ready",
            "thesis_ready": "gates_ready",
            "gates_ready": "draft_created",
            "draft_created": "draft_waiting_approval",
            "draft_waiting_approval": "approved_waiting_paper_execute",
            "approved_waiting_paper_execute": "journal_review_pending",
            "journal_review_pending": "monthly_review_ready",
            "monthly_review_ready": None,
        }
        return mapping.get(current_stage)

    def _official_demo_draft(self) -> OrderDraft | None:
        return self.db.scalar(
            select(OrderDraft)
            .join(OrderIntent, OrderIntent.id == OrderDraft.order_intent_id)
            .where(OrderIntent.source_id == DEMO_PENDING_SOURCE_ID)
            .limit(1)
        )
