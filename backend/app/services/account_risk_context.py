"""Server-owned financial inputs. Paper capital is never a live broker balance."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Asset, AuditLog, Execution, InvestmentConstitution
from app.models import InvestmentThesis, KillSwitch, OrderDraft, OrderIntent, Position, Quote, RiskBudget, RiskCheck
from app.services.paper_execution import DEFAULT_PAPER_CASH, PaperExecutionService

ZERO = Decimal('0')


def number(value) -> Decimal:
    result = Decimal(str(value if value is not None else 0))
    if not result.is_finite():
        raise ValueError('non-finite financial value')
    return result


def server_account_context(db: Session, intent: OrderIntent, requested: dict, *, draft_id: str | None = None) -> dict:
    """Client figures can make a preview stricter; they cannot reduce server risk.

    No broker-synchronized account implementation exists yet, so only the
    explicitly simulated paper ledger can supply executable financial facts.
    Persisted manual/imported portfolio snapshots are not broker attestations.
    """
    account = db.get(Account, intent.account_id)
    asset = db.get(Asset, intent.asset_id)
    if account is None or asset is None:
        return {**requested, '_account_risk_errors': ['account_or_asset_missing']}
    errors = []
    if asset.currency != account.base_currency:
        errors.append('order_currency_conversion_unavailable')
    simulated = account.mode in {'paper', 'mock'} and not account.live_trading_enabled
    if not simulated:
        errors.append('trusted_broker_account_snapshot_unavailable')
    positions = list(db.scalars(select(Position).where(Position.account_id == account.id)).all())
    if simulated:
        cash_service = PaperExecutionService(db)
        cash_asset = cash_service._get_or_create_cash_asset(account.base_currency)
        if not any(p.asset_id == cash_asset.id for p in positions):
            initial = DEFAULT_PAPER_CASH if not positions else ZERO
            cash_service._get_or_create_cash_position(account, seed_if_missing=initial)
            db.add(AuditLog(actor_type='system', actor_id='paper-ledger', action='paper.cash_initialized',
                            entity_type='Account', entity_id=account.id,
                            payload_json={'source': 'PAPER_LEDGER', 'initial_cash': str(initial), 'currency': account.base_currency, 'real_funds': False}))
            db.flush()
            positions = list(db.scalars(select(Position).where(Position.account_id == account.id)).all())
    assets = {a.id: a for a in db.scalars(select(Asset).where(Asset.id.in_([p.asset_id for p in positions]))).all()}
    equity = cash = current = asset_class = crypto = exchange = ZERO
    for position in positions:
        held = assets.get(position.asset_id)
        if held is None:
            errors.append('position_asset_unavailable')
            continue
        if held.currency != account.base_currency:
            errors.append('account_currency_conversion_unavailable')
        value = number(position.market_value)
        if value < 0 or number(position.quantity) < 0:
            errors.append('short_or_margin_position_unsupported')
        equity += value
        if held.asset_type in {'cash', 'stablecoin'}:
            # Only base-currency cash is spendable; a stablecoin position needs
            # venue-specific settlement/FX capabilities before being cash.
            if held.asset_type == 'cash' and held.currency == account.base_currency:
                cash += value
        if held.id == asset.id:
            current += max(ZERO, value)
        if held.asset_type == asset.asset_type:
            asset_class += max(ZERO, value)
        if held.asset_type == 'crypto':
            crypto += max(ZERO, value)
        if held.venue == asset.venue and held.asset_type != 'cash':
            exchange += max(ZERO, value)
    if equity <= 0:
        errors.append('account_equity_unavailable')
    amounts = [number(intent.notional)] if intent.notional is not None else []
    quantity = number(intent.quantity) if intent.quantity is not None else None
    if quantity is not None:
        if quantity <= 0: errors.append('order_quantity_invalid')
        price = number(intent.limit_price) if intent.limit_price is not None else None
        if price is None:
            quote = db.scalar(select(Quote).where(Quote.asset_id == asset.id).order_by(Quote.as_of.desc(), Quote.id.desc()).limit(1))
            if quote is not None:
                as_of = quote.as_of if quote.as_of.tzinfo else quote.as_of.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - as_of).total_seconds()
                if 0 <= age <= 900: price = number(quote.price)
            if price is None: errors.append('order_valuation_quote_unavailable')
        if price is not None:
            if price <= 0: errors.append('order_valuation_price_invalid')
            amounts.append(quantity * price)
    notional = max(amounts, default=ZERO)
    if notional <= 0:
        errors.append('order_notional_unavailable')
    original_notional = notional
    if draft_id is not None:
        own_fills = list(db.scalars(select(Execution).where(Execution.order_draft_id == draft_id)).all())
        if quantity is not None and quantity > 0:
            filled = sum((number(fill.filled_quantity) for fill in own_fills), ZERO)
            notional *= max(ZERO, quantity - filled) / quantity
        else:
            notional = max(ZERO, notional - sum((number(fill.fill_notional) for fill in own_fills), ZERO))
    reserved_cash = reserved_target = reserved_class = reserved_crypto = reserved_exchange = ZERO
    draft_query = select(OrderDraft, OrderIntent).join(OrderIntent, OrderDraft.order_intent_id == OrderIntent.id).where(
        OrderIntent.account_id == account.id,
        OrderDraft.approval_status == 'approved',
        OrderDraft.execution_status.not_in(['paper_filled', 'cancelled', 'rejected', 'expired']),
    )
    if draft_id is not None:
        draft_query = draft_query.where(OrderDraft.id != draft_id)
    drafts = db.execute(draft_query).all()
    for draft, pending in drafts:
        if pending.side != 'buy':
            continue
        amounts = [number(pending.notional), number(pending.quantity) * number(pending.limit_price)]
        approved_risk = db.scalar(select(RiskCheck).where(RiskCheck.order_intent_id == pending.id,
            RiskCheck.hard_rule_passed.is_(True)).order_by(RiskCheck.created_at.desc(), RiskCheck.id.desc()).limit(1))
        if approved_risk:
            amounts.append(number((approved_risk.rules_json or {}).get('context', {}).get('_server_order_notional')))
        amount = max(amounts)
        fills = list(db.scalars(select(Execution).where(Execution.order_draft_id == draft.id)).all())
        amount = max(ZERO, amount - sum((number(fill.fill_notional) for fill in fills), ZERO))
        reserved_cash += amount
        pending_asset = db.get(Asset, pending.asset_id)
        if pending.asset_id == asset.id: reserved_target += amount
        if pending_asset and pending_asset.asset_type == asset.asset_type: reserved_class += amount
        if pending_asset and pending_asset.asset_type == 'crypto': reserved_crypto += amount
        if pending_asset and pending_asset.venue == asset.venue: reserved_exchange += amount
    available = max(ZERO, cash - reserved_cash)
    if intent.side == 'buy' and notional > available:
        errors.append('insufficient_available_cash_after_reservations')
    if intent.side == 'sell' and notional > current:
        errors.append('sell_exceeds_server_position')
    sign = Decimal('-1') if intent.side == 'sell' else Decimal('1')
    pct = lambda value: float(max(ZERO, value) / equity) if equity > 0 else 1.0
    final_target = max(ZERO, current + sign * notional) + reserved_target
    final_class = max(ZERO, asset_class + sign * notional) + reserved_class
    final_crypto = max(ZERO, crypto + (sign * notional if asset.asset_type == 'crypto' else ZERO)) + reserved_crypto
    final_exchange = max(ZERO, exchange + sign * notional) + reserved_exchange
    # This is ledger loss, not a caller's assertion that today's loss is zero.
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    fills = db.execute(select(Execution, OrderIntent.side).join(OrderDraft, Execution.order_draft_id == OrderDraft.id).join(
        OrderIntent, OrderDraft.order_intent_id == OrderIntent.id).where(OrderIntent.account_id == account.id, Execution.created_at >= start)).all()
    # Sell realized PnL already includes its allocated fee; do not charge it twice.
    daily_loss = sum((max(ZERO, -number(fill.realized_pnl)) + (number(fill.fee_amount) if side == 'buy' else ZERO)
                      for fill, side in fills), ZERO)
    user_id = account.user_id
    if intent.investment_thesis_id:
        thesis = db.get(InvestmentThesis, intent.investment_thesis_id)
        if thesis: user_id = thesis.user_id
    budget = db.scalar(select(RiskBudget).where(RiskBudget.asset_class == asset.asset_type,
        (RiskBudget.account_id == account.id) | ((RiskBudget.account_id.is_(None)) & (RiskBudget.user_id == user_id)))
        .order_by(RiskBudget.account_id.desc(), RiskBudget.updated_at.desc(), RiskBudget.id.desc()).limit(1))
    if budget:
        user_id = budget.user_id
        constitution = db.get(InvestmentConstitution, budget.constitution_id)
        if constitution is not None and not constitution.is_active:
            errors.append('account_risk_constitution_inactive')
    else:
        constitution = db.scalar(select(InvestmentConstitution).where(InvestmentConstitution.user_id == user_id,
            InvestmentConstitution.is_active.is_(True)).order_by(InvestmentConstitution.updated_at.desc(), InvestmentConstitution.id.desc()).limit(1))
    max_notional = min(Decimal('10000'), number(budget.max_order_notional)) if budget else Decimal('10000')
    max_position = min(Decimal('.25'), number(constitution.max_single_position_pct)) if constitution else Decimal('.25')
    max_loss = min(Decimal('1000'), equity * number(constitution.max_daily_loss_pct)) if constitution else Decimal('1000')
    max_leverage = number(budget.max_leverage) if budget else Decimal('1')
    if constitution and not constitution.leverage_allowed: max_leverage = ZERO
    kill = db.scalar(select(KillSwitch.id).where(KillSwitch.disengaged_at.is_(None),
        (KillSwitch.account_id == account.id) | KillSwitch.account_id.is_(None),
        (KillSwitch.asset_id == asset.id) | KillSwitch.asset_id.is_(None)).limit(1)) is not None
    result = dict(requested)
    result['user_id'] = user_id
    def at_least(key, value): result[key] = max(float(value), float(requested.get(key) or 0))
    def at_most(key, value): result[key] = min(float(value), float(requested[key])) if requested.get(key) is not None else float(value)
    at_most('total_equity', equity)
    at_least('current_position_value', current)
    at_least('current_position_pct', pct(current + reserved_target))
    at_least('order_position_pct', pct(notional) if intent.side == 'buy' else 0)
    at_least('asset_class_pct', pct(final_class))
    at_least('crypto_pct', pct(final_crypto))
    at_least('exchange_pct', pct(final_exchange))
    at_least('account_daily_loss', daily_loss)
    at_least('daily_loss_pct', pct(daily_loss))
    for key, value in [('max_order_notional', max_notional), ('max_position_pct', max_position), ('max_daily_loss', max_loss), ('max_leverage', max_leverage)]: at_most(key, value)
    if constitution:
        for key in ['max_single_position_pct', 'max_asset_class_pct', 'max_crypto_pct', 'max_single_exchange_pct', 'max_daily_loss_pct', 'max_monthly_drawdown_pct']:
            at_most(key, getattr(constitution, key))
    result['kill_switch'] = kill or bool(requested.get('kill_switch'))
    result['order_mode'] = 'auto' if intent.source_type in {'auto', 'controlled_auto', 'strategy_auto'} else requested.get('order_mode', 'manual')
    result['_account_risk_errors'] = sorted(set(errors))
    result['_server_order_notional'] = str(original_notional)
    result['_server_remaining_notional'] = str(notional)
    result['_server_projected_position_pct'] = pct(final_target)
    result['_account_risk_evidence'] = {'source': 'PAPER_LEDGER' if simulated else 'UNVERIFIED', 'account_id': account.id,
        'currency': account.base_currency, 'equity': str(equity), 'cash': str(cash), 'reserved_cash': str(reserved_cash),
        'available_cash': str(available), 'position_value': str(current), 'real_funds': False, 'evaluated_at': datetime.now(timezone.utc).isoformat()}
    return result
