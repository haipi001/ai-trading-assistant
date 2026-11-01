from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account
from app.models import Asset
from app.models import AuditLog
from app.models import Execution
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PaperCorporateAction
from app.models import PaperTaxLot
from app.models import PaperTaxLotRealization
from app.models import Position
from app.models import PostTradeReview
from app.models import TradeJournalEntry

DEFAULT_PAPER_CASH = Decimal("100000")
EPSILON = Decimal("0.0000000001")
MINUS_ONE = Decimal("-1")
ONE = Decimal("1")
TEN_THOUSAND = Decimal("10000")


@dataclass(frozen=True)
class PaperFillContext:
    requested_quantity: Decimal
    fill_quantity: Decimal
    cumulative_filled_quantity: Decimal
    remaining_quantity: Decimal
    requested_price: Decimal


class PaperExecutionBlockedError(ValueError):
    pass


class PaperExecutionService:
    def __init__(self, db: Session):
        self.db = db

    def apply_cash_dividend(
        self,
        *,
        account_id: str,
        asset_id: str,
        amount_per_share: float,
        effective_at: datetime | None = None,
        note: str | None = None,
    ) -> tuple[PaperCorporateAction, TradeJournalEntry]:
        account, asset, position = self._paper_action_context(account_id, asset_id)
        amount = to_decimal(amount_per_share)
        if amount <= 0:
            raise PaperExecutionBlockedError("paper cash dividend amount_per_share must be positive")

        quantity = to_decimal(position.quantity)
        cash_effect = quantity * amount
        cash_position = self._get_or_create_cash_position(account, seed_if_missing=Decimal("0"))
        self._apply_cash_effect(cash_position, cash_effect)

        corporate_action = PaperCorporateAction(
            account_id=account.id,
            asset_id=asset.id,
            action_type="cash_dividend",
            effective_at=effective_at or datetime.now(timezone.utc),
            quantity_before=quantity,
            quantity_after=quantity,
            cash_effect=cash_effect,
            amount_per_share=amount,
            status="applied",
            metadata_json={
                "note": note,
                "live_execution_performed": False,
                "cash_asset_id": cash_position.asset_id,
            },
        )
        self.db.add(corporate_action)
        self.db.flush()

        journal_entry = TradeJournalEntry(
            asset_id=asset.id,
            account_id=account.id,
            title=f"Paper dividend {asset.symbol}",
            notes="\n".join(
                [
                    "Paper corporate action applied: cash dividend.",
                    f"Quantity: {float(quantity)}",
                    f"Amount per share: {float(amount)}",
                    f"Cash effect: {float(cash_effect)}",
                    f"Note: {note or 'not provided'}",
                    "Live execution performed: false",
                ]
            ),
            tags_json=["paper_corporate_action", "cash_dividend", "no_live_broker_call"],
        )
        self.db.add(journal_entry)
        self.db.flush()
        self._write_audit_log(
            action="paper_corporate_action.cash_dividend_applied",
            entity_type="PaperCorporateAction",
            entity_id=corporate_action.id,
            payload_json={
                "account_id": account.id,
                "asset_id": asset.id,
                "quantity": float(quantity),
                "amount_per_share": float(amount),
                "cash_effect": float(cash_effect),
                "live_execution_performed": False,
            },
        )
        self._write_audit_log(
            action="trade_journal.created_from_paper_corporate_action",
            entity_type="TradeJournalEntry",
            entity_id=journal_entry.id,
            payload_json={"paper_corporate_action_id": corporate_action.id, "asset_id": asset.id, "account_id": account.id},
        )
        self.db.commit()
        self.db.refresh(corporate_action)
        self.db.refresh(journal_entry)
        return corporate_action, journal_entry

    def apply_stock_split(
        self,
        *,
        account_id: str,
        asset_id: str,
        ratio_numerator: float,
        ratio_denominator: float = 1.0,
        effective_at: datetime | None = None,
        note: str | None = None,
    ) -> tuple[PaperCorporateAction, TradeJournalEntry]:
        account, asset, position = self._paper_action_context(account_id, asset_id)
        numerator = to_decimal(ratio_numerator)
        denominator = to_decimal(ratio_denominator)
        if numerator <= 0 or denominator <= 0:
            raise PaperExecutionBlockedError("paper stock split ratio must be positive")
        ratio = numerator / denominator

        quantity_before = to_decimal(position.quantity)
        quantity_after = quantity_before * ratio
        position.quantity = quantity_after
        position.average_cost = to_decimal(position.average_cost) / ratio
        position.market_price = to_decimal(position.market_price) / ratio if to_decimal(position.market_price) > 0 else Decimal("0")
        position.market_value = quantity_after * to_decimal(position.market_price)
        position.unrealized_pnl = (to_decimal(position.market_price) - to_decimal(position.average_cost)) * quantity_after

        adjusted_lot_ids: list[str] = []
        for tax_lot in self._open_tax_lots(account.id, asset.id):
            tax_lot.quantity_opened = to_decimal(tax_lot.quantity_opened) * ratio
            tax_lot.quantity_remaining = to_decimal(tax_lot.quantity_remaining) * ratio
            tax_lot.average_cost = to_decimal(tax_lot.average_cost) / ratio
            tax_lot.metadata_json = {
                **(tax_lot.metadata_json or {}),
                "last_paper_corporate_action": "stock_split",
                "split_ratio": float(ratio),
            }
            adjusted_lot_ids.append(tax_lot.id)

        corporate_action = PaperCorporateAction(
            account_id=account.id,
            asset_id=asset.id,
            action_type="stock_split",
            effective_at=effective_at or datetime.now(timezone.utc),
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            cash_effect=0,
            ratio=ratio,
            status="applied",
            metadata_json={
                "ratio_numerator": float(numerator),
                "ratio_denominator": float(denominator),
                "note": note,
                "tax_lot_ids": adjusted_lot_ids,
                "live_execution_performed": False,
            },
        )
        self.db.add(corporate_action)
        self.db.flush()

        journal_entry = TradeJournalEntry(
            asset_id=asset.id,
            account_id=account.id,
            title=f"Paper split {asset.symbol}",
            notes="\n".join(
                [
                    "Paper corporate action applied: stock split.",
                    f"Ratio: {float(ratio)}",
                    f"Quantity before: {float(quantity_before)}",
                    f"Quantity after: {float(quantity_after)}",
                    f"Adjusted tax lots: {len(adjusted_lot_ids)}",
                    f"Note: {note or 'not provided'}",
                    "Live execution performed: false",
                ]
            ),
            tags_json=["paper_corporate_action", "stock_split", "tax_lot_adjustment", "no_live_broker_call"],
        )
        self.db.add(journal_entry)
        self.db.flush()
        self._write_audit_log(
            action="paper_corporate_action.stock_split_applied",
            entity_type="PaperCorporateAction",
            entity_id=corporate_action.id,
            payload_json={
                "account_id": account.id,
                "asset_id": asset.id,
                "ratio": float(ratio),
                "quantity_before": float(quantity_before),
                "quantity_after": float(quantity_after),
                "tax_lot_ids": adjusted_lot_ids,
                "live_execution_performed": False,
            },
        )
        self._write_audit_log(
            action="paper_tax_lots.adjusted_from_stock_split",
            entity_type="PaperCorporateAction",
            entity_id=corporate_action.id,
            payload_json={"tax_lot_ids": adjusted_lot_ids, "ratio": float(ratio)},
        )
        self.db.commit()
        self.db.refresh(corporate_action)
        self.db.refresh(journal_entry)
        return corporate_action, journal_entry

    def execute_draft(
        self,
        draft: OrderDraft,
        *,
        approver_id: str | None = None,
        decision_reason: str | None = None,
        fill_price: float | None = None,
        fill_quantity: float | None = None,
        fee_bps: float = 1.0,
        slippage_bps: float = 0.0,
    ) -> tuple[
        Execution,
        TradeJournalEntry,
        PostTradeReview,
        OrderDraft,
        list[PaperTaxLot],
        list[PaperTaxLotRealization],
    ]:
        order_intent = self.db.get(OrderIntent, draft.order_intent_id)
        if order_intent is None:
            raise PaperExecutionBlockedError("order intent is unavailable")
        account = self.db.get(Account, order_intent.account_id)
        asset = self.db.get(Asset, order_intent.asset_id)
        if account is None or asset is None:
            raise PaperExecutionBlockedError("order intent account or asset is unavailable")

        self._ensure_paper_executable(draft, account)
        fill_context = self._fill_context(order_intent, draft, fill_price, fill_quantity)
        execution_price = self._execution_price(order_intent.side, fill_context.requested_price, to_decimal(slippage_bps))
        fill_notional = fill_context.fill_quantity * execution_price
        fee_amount = self._fee_amount(fill_notional, fee_bps)
        slippage_amount = abs(execution_price - fill_context.requested_price) * fill_context.fill_quantity
        cash_effect = self._cash_effect(order_intent.side, fill_notional, fee_amount)

        cash_position = self._get_or_create_cash_position(
            account,
            seed_if_missing=DEFAULT_PAPER_CASH if cash_effect < 0 else Decimal("0"),
        )
        if to_decimal(cash_position.quantity) + cash_effect < 0:
            raise PaperExecutionBlockedError("paper execution blocked by insufficient paper cash")

        paper_position = self._prepare_position_for_execution(
            account=account,
            asset=asset,
            side=order_intent.side,
            quantity=fill_context.fill_quantity,
        )
        if order_intent.side.lower() == "sell":
            self._ensure_tax_lot_coverage(account, asset, paper_position)

        execution_status = "filled" if self._is_effectively_zero(fill_context.remaining_quantity) else "partially_filled"
        execution = Execution(
            order_draft_id=draft.id,
            position_id=paper_position.id,
            execution_mode="paper",
            status=execution_status,
            filled_quantity=fill_context.fill_quantity,
            average_fill_price=execution_price,
            fill_notional=fill_notional,
            fee_amount=fee_amount,
            slippage_amount=slippage_amount,
            cash_effect=cash_effect,
            requested_quantity=fill_context.requested_quantity,
            cumulative_filled_quantity=fill_context.cumulative_filled_quantity,
            remaining_quantity=fill_context.remaining_quantity,
            proceeds_amount=fill_notional if order_intent.side.lower() == "sell" else Decimal("0"),
            cost_basis_amount=Decimal("0"),
            realized_pnl=Decimal("0"),
        )
        self.db.add(execution)
        self.db.flush()

        affected_tax_lots: list[PaperTaxLot] = []
        tax_lot_realizations: list[PaperTaxLotRealization] = []
        cost_basis_amount = Decimal("0")
        proceeds_amount = fill_notional if order_intent.side.lower() == "sell" else Decimal("0")
        realized_pnl = Decimal("0")

        if order_intent.side.lower() == "buy":
            self._apply_buy(paper_position, fill_context.fill_quantity, execution_price, fee_amount)
            affected_tax_lots.append(
                self._create_buy_tax_lot(
                    account=account,
                    asset=asset,
                    draft=draft,
                    execution=execution,
                    quantity=fill_context.fill_quantity,
                    fill_notional=fill_notional,
                    fee_amount=fee_amount,
                )
            )
        elif order_intent.side.lower() == "sell":
            affected_tax_lots, tax_lot_realizations, cost_basis_amount, proceeds_amount, realized_pnl = self._consume_tax_lots(
                account=account,
                asset=asset,
                execution=execution,
                quantity=fill_context.fill_quantity,
                execution_price=execution_price,
                fee_amount=fee_amount,
            )
            self.db.flush()
            self._apply_sell(
                paper_position,
                fill_context.fill_quantity,
                execution_price,
                realized_pnl,
                self._remaining_average_cost(account.id, asset.id),
            )

        execution.cost_basis_amount = cost_basis_amount
        execution.proceeds_amount = proceeds_amount
        execution.realized_pnl = realized_pnl
        self._apply_cash_effect(cash_position, cash_effect)
        draft.execution_status = "paper_filled" if execution.status == "filled" else "paper_partially_filled"

        journal_entry = TradeJournalEntry(
            asset_id=asset.id,
            account_id=account.id,
            title=f"Paper {order_intent.side.upper()} {asset.symbol}",
            notes=self._journal_notes(
                order_intent,
                draft,
                fill_context,
                execution_price,
                fill_notional,
                fee_amount,
                slippage_amount,
                cash_effect,
                proceeds_amount,
                cost_basis_amount,
                realized_pnl,
                decision_reason,
            ),
            tags_json=["paper_execution", "human_approved", "no_live_broker_call"],
        )

        self.db.add(journal_entry)
        self.db.flush()
        post_trade_review = PostTradeReview(
            execution_id=execution.id,
            trade_journal_entry_id=journal_entry.id,
            order_draft_id=draft.id,
            user_id=approver_id or "manual-user",
            status="pending",
            prompt_json=self._post_trade_prompt(
                order_intent=order_intent,
                asset=asset,
                fill_context=fill_context,
                execution_price=execution_price,
                fee_amount=fee_amount,
                slippage_amount=slippage_amount,
                proceeds_amount=proceeds_amount,
                cost_basis_amount=cost_basis_amount,
                realized_pnl=realized_pnl,
            ),
            review_json={},
        )
        self.db.add(post_trade_review)
        self.db.flush()
        self._write_audit_log(
            action="paper_execution.filled",
            entity_type="Execution",
            entity_id=execution.id,
            payload_json={
                "order_draft_id": draft.id,
                "order_intent_id": order_intent.id,
                "position_id": paper_position.id,
                "approver_id": approver_id,
                "status": execution.status,
                "draft_execution_status": draft.execution_status,
                "requested_quantity": float(fill_context.requested_quantity),
                "filled_quantity": float(fill_context.fill_quantity),
                "cumulative_filled_quantity": float(fill_context.cumulative_filled_quantity),
                "remaining_quantity": float(fill_context.remaining_quantity),
                "average_fill_price": float(execution_price),
                "fill_notional": float(fill_notional),
                "fee_amount": float(fee_amount),
                "slippage_amount": float(slippage_amount),
                "cash_effect": float(cash_effect),
                "proceeds_amount": float(proceeds_amount),
                "cost_basis_amount": float(cost_basis_amount),
                "realized_pnl": float(realized_pnl),
                "tax_lot_ids": [tax_lot.id for tax_lot in affected_tax_lots],
                "tax_lot_realization_ids": [realization.id for realization in tax_lot_realizations],
                "live_execution_performed": False,
            },
        )
        self._write_audit_log(
            action="paper_portfolio.updated_from_execution",
            entity_type="Position",
            entity_id=paper_position.id,
            payload_json={
                "order_draft_id": draft.id,
                "execution_id": execution.id,
                "account_id": account.id,
                "asset_id": asset.id,
                "side": order_intent.side,
                "quantity": float(fill_context.fill_quantity),
                "cash_effect": float(cash_effect),
                "realized_pnl": float(realized_pnl),
            },
        )
        self._write_audit_log(
            action="trade_journal.created_from_paper_execution",
            entity_type="TradeJournalEntry",
            entity_id=journal_entry.id,
            payload_json={
                "order_draft_id": draft.id,
                "execution_id": execution.id,
                "asset_id": asset.id,
                "account_id": account.id,
            },
        )
        self._write_audit_log(
            action="post_trade_review.created_from_paper_execution",
            entity_type="PostTradeReview",
            entity_id=post_trade_review.id,
            payload_json={
                "order_draft_id": draft.id,
                "execution_id": execution.id,
                "trade_journal_entry_id": journal_entry.id,
                "status": post_trade_review.status,
            },
        )
        if affected_tax_lots:
            self._write_audit_log(
                action="paper_tax_lots.updated_from_execution",
                entity_type="Execution",
                entity_id=execution.id,
                payload_json={
                    "order_draft_id": draft.id,
                    "execution_id": execution.id,
                    "tax_lot_ids": [tax_lot.id for tax_lot in affected_tax_lots],
                    "tax_lot_realization_ids": [realization.id for realization in tax_lot_realizations],
                },
            )
        self.db.commit()
        self.db.refresh(execution)
        self.db.refresh(journal_entry)
        self.db.refresh(post_trade_review)
        self.db.refresh(draft)
        for tax_lot in affected_tax_lots:
            self.db.refresh(tax_lot)
        for realization in tax_lot_realizations:
            self.db.refresh(realization)
        return execution, journal_entry, post_trade_review, draft, affected_tax_lots, tax_lot_realizations

    def _ensure_paper_executable(self, draft: OrderDraft, account: Account) -> None:
        if account.mode not in {"paper", "manual", "mock"}:
            raise PaperExecutionBlockedError("paper execution requires paper, manual, or mock account mode")
        if account.live_trading_enabled:
            raise PaperExecutionBlockedError("paper execution refuses accounts with live trading enabled")
        if draft.risk_status != "passed":
            raise PaperExecutionBlockedError("paper execution requires passed risk status")
        if draft.behavior_status != "passed":
            raise PaperExecutionBlockedError("paper execution requires passed behavior status")
        if draft.approval_status != "approved":
            raise PaperExecutionBlockedError("paper execution requires approved order draft")
        if draft.execution_status == "paper_filled":
            raise PaperExecutionBlockedError("order draft already has a paper execution")

        gate_results = draft.decision_gate_results or {}
        required = {"RESEARCH_GATE", "THESIS_GATE", "RISK_GATE", "BEHAVIOR_GATE", "EXECUTION_GATE"}
        missing = sorted(required.difference(gate_results))
        failed = sorted(
            gate
            for gate, result in gate_results.items()
            if gate in required and isinstance(result, dict) and result.get("status") != "PASSED"
        )
        if missing or failed:
            raise PaperExecutionBlockedError(f"paper execution requires all gates passed; missing={missing}; failed={failed}")

    def _paper_action_context(self, account_id: str, asset_id: str) -> tuple[Account, Asset, Position]:
        account = self.db.get(Account, account_id)
        asset = self.db.get(Asset, asset_id)
        if account is None or asset is None:
            raise PaperExecutionBlockedError("paper corporate action account or asset is unavailable")
        if account.mode not in {"paper", "manual", "mock"}:
            raise PaperExecutionBlockedError("paper corporate action requires paper, manual, or mock account mode")
        if account.live_trading_enabled:
            raise PaperExecutionBlockedError("paper corporate action refuses accounts with live trading enabled")

        position = self._position(account.id, asset.id)
        if position is None or to_decimal(position.quantity) <= 0:
            raise PaperExecutionBlockedError("paper corporate action requires an existing positive paper position")
        return account, asset, position

    def _fill_context(
        self,
        order_intent: OrderIntent,
        draft: OrderDraft,
        requested_fill_price: float | None,
        requested_fill_quantity: float | None,
    ) -> PaperFillContext:
        requested_price = self._requested_price(order_intent, requested_fill_price)
        requested_quantity = self._requested_quantity(order_intent, requested_price)
        previous_requested_quantity = self._paper_requested_quantity(draft.id)
        if previous_requested_quantity > 0:
            requested_quantity = previous_requested_quantity

        already_filled_quantity = self._paper_filled_quantity(draft.id)
        remaining_before_fill = requested_quantity - already_filled_quantity
        if self._is_effectively_zero(remaining_before_fill) or remaining_before_fill < 0:
            raise PaperExecutionBlockedError("order draft already has a paper execution")

        fill_quantity = to_decimal(requested_fill_quantity) if requested_fill_quantity is not None else remaining_before_fill
        if fill_quantity <= 0:
            raise PaperExecutionBlockedError("paper execution fill_quantity must be positive")
        if fill_quantity - remaining_before_fill > EPSILON:
            raise PaperExecutionBlockedError("paper execution fill quantity exceeds remaining draft quantity")

        remaining_after_fill = requested_quantity - already_filled_quantity - fill_quantity
        if self._is_effectively_zero(remaining_after_fill):
            remaining_after_fill = Decimal("0")

        return PaperFillContext(
            requested_quantity=requested_quantity,
            fill_quantity=fill_quantity,
            cumulative_filled_quantity=already_filled_quantity + fill_quantity,
            remaining_quantity=remaining_after_fill,
            requested_price=requested_price,
        )

    def _requested_price(self, order_intent: OrderIntent, requested_fill_price: float | None) -> Decimal:
        notional = to_decimal(order_intent.notional)
        price = to_decimal(requested_fill_price if requested_fill_price is not None else order_intent.limit_price)
        quantity = to_decimal(order_intent.quantity)

        if price <= 0 and quantity > 0 and notional > 0:
            price = notional / quantity
        if price <= 0:
            raise PaperExecutionBlockedError("paper execution requires limit price or explicit fill price")
        return price

    def _requested_quantity(self, order_intent: OrderIntent, price: Decimal) -> Decimal:
        quantity = to_decimal(order_intent.quantity)
        notional = to_decimal(order_intent.notional)
        if quantity <= 0 and notional > 0 and price > 0:
            quantity = notional / price
        if quantity <= 0:
            raise PaperExecutionBlockedError("paper execution requires quantity or notional with fill price")
        return quantity

    def _paper_filled_quantity(self, order_draft_id: str) -> Decimal:
        filled_quantity = self.db.scalar(
            select(func.coalesce(func.sum(Execution.filled_quantity), 0)).where(
                Execution.order_draft_id == order_draft_id,
                Execution.execution_mode == "paper",
            )
        )
        return to_decimal(filled_quantity)

    def _paper_requested_quantity(self, order_draft_id: str) -> Decimal:
        requested_quantity = self.db.scalar(
            select(func.coalesce(func.max(Execution.requested_quantity), 0)).where(
                Execution.order_draft_id == order_draft_id,
                Execution.execution_mode == "paper",
            )
        )
        return to_decimal(requested_quantity)

    def _execution_price(self, side: str, requested_price: Decimal, slippage_bps: Decimal) -> Decimal:
        if slippage_bps < 0:
            raise PaperExecutionBlockedError("paper execution slippage_bps must be non-negative")
        multiplier = ONE + (slippage_bps / TEN_THOUSAND)
        if side.lower() == "sell":
            multiplier = ONE - (slippage_bps / TEN_THOUSAND)
        if side.lower() not in {"buy", "sell"}:
            raise PaperExecutionBlockedError("paper execution only supports buy or sell side")
        execution_price = requested_price * multiplier
        if execution_price <= 0:
            raise PaperExecutionBlockedError("paper execution price must remain positive after slippage")
        return execution_price

    def _fee_amount(self, fill_notional: Decimal, fee_bps: float) -> Decimal:
        fee_rate = to_decimal(fee_bps)
        if fee_rate < 0:
            raise PaperExecutionBlockedError("paper execution fee_bps must be non-negative")
        return abs(fill_notional) * fee_rate / TEN_THOUSAND

    def _cash_effect(self, side: str, fill_notional: Decimal, fee_amount: Decimal) -> Decimal:
        normalized = side.lower()
        if normalized == "buy":
            return (fill_notional + fee_amount) * MINUS_ONE
        if normalized == "sell":
            return fill_notional - fee_amount
        raise PaperExecutionBlockedError("paper execution only supports buy or sell side")

    def _prepare_position_for_execution(
        self,
        *,
        account: Account,
        asset: Asset,
        side: str,
        quantity: Decimal,
    ) -> Position:
        position = self._position(account.id, asset.id)
        if side.lower() == "buy":
            if position is None:
                position = Position(
                    account_id=account.id,
                    asset_id=asset.id,
                    quantity=0,
                    average_cost=0,
                    market_price=0,
                    market_value=0,
                    unrealized_pnl=0,
                    realized_pnl=0,
                    weight=0,
                )
                self.db.add(position)
                self.db.flush()
        elif side.lower() == "sell":
            if position is None or to_decimal(position.quantity) < quantity:
                raise PaperExecutionBlockedError("paper execution blocked by insufficient paper position quantity")
        else:
            raise PaperExecutionBlockedError("paper execution only supports buy or sell side")
        return position

    def _apply_buy(self, position: Position, quantity: Decimal, execution_price: Decimal, fee_amount: Decimal) -> None:
        old_quantity = to_decimal(position.quantity)
        old_cost_basis = old_quantity * to_decimal(position.average_cost)
        new_quantity = old_quantity + quantity
        new_cost_basis = old_cost_basis + (quantity * execution_price) + fee_amount
        position.quantity = new_quantity
        position.average_cost = new_cost_basis / new_quantity
        position.market_price = execution_price
        position.market_value = new_quantity * execution_price
        position.unrealized_pnl = (execution_price - to_decimal(position.average_cost)) * new_quantity

    def _apply_sell(
        self,
        position: Position,
        quantity: Decimal,
        execution_price: Decimal,
        realized_pnl: Decimal,
        remaining_average_cost: Decimal,
    ) -> None:
        old_quantity = to_decimal(position.quantity)
        new_quantity = old_quantity - quantity
        average_cost = remaining_average_cost if new_quantity > 0 and remaining_average_cost > 0 else Decimal("0")
        position.quantity = new_quantity
        position.average_cost = average_cost
        position.market_price = execution_price
        position.market_value = new_quantity * execution_price
        position.realized_pnl = to_decimal(position.realized_pnl) + realized_pnl
        position.unrealized_pnl = (execution_price - to_decimal(position.average_cost)) * new_quantity

    def _create_buy_tax_lot(
        self,
        *,
        account: Account,
        asset: Asset,
        draft: OrderDraft,
        execution: Execution,
        quantity: Decimal,
        fill_notional: Decimal,
        fee_amount: Decimal,
    ) -> PaperTaxLot:
        cost_basis = fill_notional + fee_amount
        tax_lot = PaperTaxLot(
            account_id=account.id,
            asset_id=asset.id,
            source_execution_id=execution.id,
            opened_order_draft_id=draft.id,
            status="open",
            quantity_opened=quantity,
            quantity_remaining=quantity,
            average_cost=cost_basis / quantity,
            cost_basis_remaining=cost_basis,
            metadata_json={
                "source": "paper_buy",
                "execution_id": execution.id,
                "fee_amount": float(fee_amount),
            },
        )
        self.db.add(tax_lot)
        self.db.flush()
        return tax_lot

    def _ensure_tax_lot_coverage(self, account: Account, asset: Asset, position: Position) -> list[PaperTaxLot]:
        position_quantity = to_decimal(position.quantity)
        if position_quantity <= 0:
            return []

        open_tax_lots = self._open_tax_lots(account.id, asset.id)
        open_quantity = sum((to_decimal(tax_lot.quantity_remaining) for tax_lot in open_tax_lots), Decimal("0"))
        missing_quantity = position_quantity - open_quantity
        if missing_quantity <= EPSILON:
            return open_tax_lots

        average_cost = to_decimal(position.average_cost)
        bootstrap_lot = PaperTaxLot(
            account_id=account.id,
            asset_id=asset.id,
            source_execution_id=None,
            opened_order_draft_id=None,
            status="open",
            quantity_opened=missing_quantity,
            quantity_remaining=missing_quantity,
            average_cost=average_cost,
            cost_basis_remaining=missing_quantity * average_cost,
            metadata_json={
                "source": "legacy_position_bootstrap",
                "reason": "created to cover existing paper position before FIFO realization",
                "position_id": position.id,
            },
        )
        self.db.add(bootstrap_lot)
        self.db.flush()
        return [*open_tax_lots, bootstrap_lot]

    def _consume_tax_lots(
        self,
        *,
        account: Account,
        asset: Asset,
        execution: Execution,
        quantity: Decimal,
        execution_price: Decimal,
        fee_amount: Decimal,
    ) -> tuple[list[PaperTaxLot], list[PaperTaxLotRealization], Decimal, Decimal, Decimal]:
        remaining_quantity = quantity
        affected_tax_lots: list[PaperTaxLot] = []
        tax_lot_realizations: list[PaperTaxLotRealization] = []
        total_cost_basis = Decimal("0")
        total_proceeds = Decimal("0")
        total_realized_pnl = Decimal("0")

        for tax_lot in self._open_tax_lots(account.id, asset.id):
            if remaining_quantity <= EPSILON:
                break

            lot_quantity = to_decimal(tax_lot.quantity_remaining)
            if lot_quantity <= EPSILON:
                continue

            consumed_quantity = min(lot_quantity, remaining_quantity)
            consumed_all_lot = self._is_effectively_zero(lot_quantity - consumed_quantity)
            cost_basis = to_decimal(tax_lot.cost_basis_remaining) if consumed_all_lot else to_decimal(tax_lot.average_cost) * consumed_quantity
            proceeds = execution_price * consumed_quantity
            fee_allocated = fee_amount * consumed_quantity / quantity
            realized_pnl = proceeds - cost_basis - fee_allocated

            tax_lot.quantity_remaining = lot_quantity - consumed_quantity
            tax_lot.cost_basis_remaining = max(to_decimal(tax_lot.cost_basis_remaining) - cost_basis, Decimal("0"))
            if self._is_effectively_zero(to_decimal(tax_lot.quantity_remaining)):
                tax_lot.quantity_remaining = Decimal("0")
                tax_lot.cost_basis_remaining = Decimal("0")
                tax_lot.status = "closed"
                tax_lot.closed_at = datetime.now(timezone.utc)

            realization = PaperTaxLotRealization(
                execution_id=execution.id,
                tax_lot_id=tax_lot.id,
                quantity=consumed_quantity,
                proceeds_amount=proceeds,
                cost_basis_amount=cost_basis,
                fee_allocated=fee_allocated,
                realized_pnl=realized_pnl,
            )
            self.db.add(realization)
            affected_tax_lots.append(tax_lot)
            tax_lot_realizations.append(realization)
            total_cost_basis += cost_basis
            total_proceeds += proceeds
            total_realized_pnl += realized_pnl
            remaining_quantity -= consumed_quantity

        if remaining_quantity > EPSILON:
            raise PaperExecutionBlockedError("paper execution blocked by insufficient tax lot quantity")

        self.db.flush()
        return affected_tax_lots, tax_lot_realizations, total_cost_basis, total_proceeds, total_realized_pnl

    def _open_tax_lots(self, account_id: str, asset_id: str) -> list[PaperTaxLot]:
        return list(
            self.db.scalars(
                select(PaperTaxLot)
                .where(
                    PaperTaxLot.account_id == account_id,
                    PaperTaxLot.asset_id == asset_id,
                    PaperTaxLot.status == "open",
                    PaperTaxLot.quantity_remaining > 0,
                )
                .order_by(PaperTaxLot.opened_at.asc(), PaperTaxLot.id.asc())
            ).all()
        )

    def _remaining_average_cost(self, account_id: str, asset_id: str) -> Decimal:
        open_tax_lots = self._open_tax_lots(account_id, asset_id)
        remaining_quantity = sum((to_decimal(tax_lot.quantity_remaining) for tax_lot in open_tax_lots), Decimal("0"))
        if remaining_quantity <= EPSILON:
            return Decimal("0")
        remaining_cost_basis = sum((to_decimal(tax_lot.cost_basis_remaining) for tax_lot in open_tax_lots), Decimal("0"))
        return remaining_cost_basis / remaining_quantity

    def _apply_cash_effect(self, cash_position: Position, cash_effect: Decimal) -> None:
        new_cash = to_decimal(cash_position.quantity) + cash_effect
        cash_position.quantity = new_cash
        cash_position.average_cost = Decimal("1")
        cash_position.market_price = Decimal("1")
        cash_position.market_value = new_cash
        cash_position.unrealized_pnl = Decimal("0")

    def _position(self, account_id: str, asset_id: str) -> Position | None:
        return self.db.scalar(
            select(Position)
            .where(Position.account_id == account_id, Position.asset_id == asset_id)
            .order_by(Position.id)
            .limit(1)
        )

    def _get_or_create_cash_position(self, account: Account, *, seed_if_missing: Decimal) -> Position:
        cash_asset = self._get_or_create_cash_asset(account.base_currency)
        cash_position = self._position(account.id, cash_asset.id)
        if cash_position is not None:
            return cash_position

        cash_position = Position(
            account_id=account.id,
            asset_id=cash_asset.id,
            quantity=seed_if_missing,
            average_cost=1,
            market_price=1,
            market_value=seed_if_missing,
            unrealized_pnl=0,
            realized_pnl=0,
            weight=0,
        )
        self.db.add(cash_position)
        self.db.flush()
        if seed_if_missing > 0:
            self._write_audit_log(
                action="paper_cash.seeded",
                entity_type="Position",
                entity_id=cash_position.id,
                payload_json={
                    "account_id": account.id,
                    "asset_id": cash_asset.id,
                    "amount": float(seed_if_missing),
                    "reason": "created missing paper cash ledger before first paper buy",
                },
            )
        return cash_position

    def _get_or_create_cash_asset(self, currency: str) -> Asset:
        symbol = currency.upper()
        cash_asset = self.db.scalar(select(Asset).where(Asset.symbol == symbol, Asset.asset_type == "cash").limit(1))
        if cash_asset is not None:
            return cash_asset

        cash_asset = Asset(
            symbol=symbol,
            name=f"{symbol} Cash",
            asset_type="cash",
            market="CASH",
            venue="PAPER_LEDGER",
            currency=symbol,
            tradable=False,
            manual_enabled=False,
            auto_enabled=False,
            risk_level="low",
        )
        self.db.add(cash_asset)
        self.db.flush()
        self._write_audit_log(
            action="paper_cash_asset.created",
            entity_type="Asset",
            entity_id=cash_asset.id,
            payload_json={"symbol": symbol, "source": "paper_execution_service"},
        )
        return cash_asset

    def _journal_notes(
        self,
        order_intent: OrderIntent,
        draft: OrderDraft,
        fill_context: PaperFillContext,
        execution_price: Decimal,
        fill_notional: Decimal,
        fee_amount: Decimal,
        slippage_amount: Decimal,
        cash_effect: Decimal,
        proceeds_amount: Decimal,
        cost_basis_amount: Decimal,
        realized_pnl: Decimal,
        decision_reason: str | None,
    ) -> str:
        return "\n".join(
            [
                "Paper execution recorded after human approval.",
                f"OrderDraft: {draft.id}",
                f"OrderIntent: {order_intent.id}",
                f"Side: {order_intent.side}",
                f"Requested quantity: {float(fill_context.requested_quantity)}",
                f"Filled quantity: {float(fill_context.fill_quantity)}",
                f"Cumulative filled quantity: {float(fill_context.cumulative_filled_quantity)}",
                f"Remaining quantity: {float(fill_context.remaining_quantity)}",
                f"Requested price: {float(fill_context.requested_price)}",
                f"Average fill price: {float(execution_price)}",
                f"Fill notional: {float(fill_notional)}",
                f"Fee amount: {float(fee_amount)}",
                f"Slippage amount: {float(slippage_amount)}",
                f"Cash effect: {float(cash_effect)}",
                f"Proceeds amount: {float(proceeds_amount)}",
                f"Cost basis amount: {float(cost_basis_amount)}",
                f"Realized PnL: {float(realized_pnl)}",
                f"Rationale: {order_intent.rationale}",
                f"Approval reason: {decision_reason or 'not provided'}",
                "Live execution performed: false",
            ]
        )

    def _post_trade_prompt(
        self,
        *,
        order_intent: OrderIntent,
        asset: Asset,
        fill_context: PaperFillContext,
        execution_price: Decimal,
        fee_amount: Decimal,
        slippage_amount: Decimal,
        proceeds_amount: Decimal,
        cost_basis_amount: Decimal,
        realized_pnl: Decimal,
    ) -> dict[str, Any]:
        return {
            "status": "pending_review",
            "trade_summary": {
                "order_intent_id": order_intent.id,
                "asset_symbol": asset.symbol,
                "side": order_intent.side,
                "requested_quantity": float(fill_context.requested_quantity),
                "filled_quantity": float(fill_context.fill_quantity),
                "cumulative_filled_quantity": float(fill_context.cumulative_filled_quantity),
                "remaining_quantity": float(fill_context.remaining_quantity),
                "average_fill_price": float(execution_price),
                "fee_amount": float(fee_amount),
                "slippage_amount": float(slippage_amount),
                "proceeds_amount": float(proceeds_amount),
                "cost_basis_amount": float(cost_basis_amount),
                "realized_pnl": float(realized_pnl),
            },
            "questions": [
                "Was this trade aligned with the thesis and strategy playbook?",
                "Which gate or warning mattered most before approval?",
                "Did the fill price, fee, or slippage change the risk/reward?",
                "What would invalidate this trade after entry?",
                "What should be updated in the constitution or playbook, if anything?",
            ],
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
                actor_id="paper-execution-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )

    def _is_effectively_zero(self, value: Decimal) -> bool:
        return abs(value) <= EPSILON


def to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))
