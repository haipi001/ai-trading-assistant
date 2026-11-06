from decimal import Decimal
import pytest
from sqlalchemy import select
from app.main import app
from app.db.session import get_db
from app.models import Asset, Position, KillSwitch, RiskBudget
from test_risk_approval import create_account, create_asset, create_intent, risk_payload
from test_paper_execution import create_approved_draft


def edit_db(callback):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        callback(db)
        db.commit()
    finally:
        generator.close()


def check(client, intent, **overrides):
    response = client.post('/risk/check-order', json=risk_payload(intent['id'], **overrides))
    assert response.status_code == 201
    return response.json()


def account_state(result):
    return next(r for r in result['rules_json']['rules'] if r['rule'] == 'trusted_account_state')['details']


def setup(client):
    asset, account = create_asset(client), create_account(client)
    intent = create_intent(client, asset['id'], account['id'])
    assert check(client, intent)['hard_rule_passed']
    return asset, account, intent


def set_cash(db, account_id, amount):
    cash_asset = db.scalar(select(Asset).where(Asset.asset_type == 'cash'))
    position = db.scalar(select(Position).where(Position.account_id == account_id, Position.asset_id == cash_asset.id))
    position.quantity = position.market_value = Decimal(str(amount))


def test_zero_exposure_and_inflated_equity_cannot_hide_persisted_position(client):
    asset, account, intent = setup(client)
    def update(db):
        set_cash(db, account['id'], 70000)
        db.add(Position(account_id=account['id'], asset_id=asset['id'], quantity=300, average_cost=100,
                        market_price=100, market_value=30000, unrealized_pnl=0, realized_pnl=0, weight=0))
    edit_db(update)
    result = check(client, intent, total_equity=1e12, current_position_value=0, max_position_pct=1)
    assert not result['hard_rule_passed']
    assert result['rules_json']['context']['current_position_value'] == 30000
    assert result['rules_json']['context']['total_equity'] == 100000
    assert 'max_position_pct' in result['reason']
    assert account_state(result)['snapshot']['source'] == 'PAPER_LEDGER'


def test_client_cannot_raise_server_default_order_limit(client):
    asset, account, _ = setup(client)
    intent = create_intent(client, asset['id'], account['id'], notional=15000)
    result = check(client, intent, max_order_notional=1e9)
    assert not result['hard_rule_passed']
    assert 'max_order_notional' in result['reason']


def test_cash_exhaustion_is_not_reseeded_or_replaced_with_client_equity(client):
    _, account, intent = setup(client)
    edit_db(lambda db: set_cash(db, account['id'], 0))
    result = check(client, intent, total_equity=1e12)
    assert not result['hard_rule_passed']
    assert 'account_equity_unavailable' in account_state(result)['errors']
    assert Decimal(account_state(result)['snapshot']['cash']) == 0


def test_other_account_cannot_supply_cash_or_dilute_exposure(client):
    _, account, intent = setup(client)
    create_account(client)
    edit_db(lambda db: set_cash(db, account['id'], 500))
    result = check(client, intent, total_equity=1e12)
    assert 'insufficient_available_cash_after_reservations' in account_state(result)['errors']
    assert Decimal(account_state(result)['snapshot']['equity']) == 500


def test_approved_open_order_reserves_cash_for_next_preview(client):
    asset, account, _ = setup(client)
    create_approved_draft(client, asset=asset, account=account, notional=9000)
    edit_db(lambda db: set_cash(db, account['id'], 10000))
    intent = create_intent(client, asset['id'], account['id'], notional=2000)
    evidence = account_state(check(client, intent, total_equity=1e12))
    assert Decimal(evidence['snapshot']['reserved_cash']) == 9000
    assert Decimal(evidence['snapshot']['available_cash']) == 1000
    assert 'insufficient_available_cash_after_reservations' in evidence['errors']


def test_real_kill_switch_cannot_be_overridden_by_request_false(client):
    _, account, intent = setup(client)
    edit_db(lambda db: db.add(KillSwitch(reason='test stop', account_id=account['id'], engaged_by='test')))
    result = check(client, intent, kill_switch=False)
    assert not result['hard_rule_passed']
    assert 'kill_switch' in result['reason']


def test_execution_revalidates_kill_switch_after_approval(client):
    asset, account, _ = setup(client)
    draft = create_approved_draft(client, asset=asset, account=account)
    edit_db(lambda db: db.add(KillSwitch(reason='stop after approval', account_id=account['id'], engaged_by='test')))
    response = client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={})
    assert response.status_code == 422
    assert 'kill_switch' in response.json()['detail']
    assert client.get('/paper-executions').json() == []


def test_approval_revalidates_account_cash_after_preview(client):
    _, account, intent = setup(client)
    from test_risk_approval import pass_decision_gates
    pass_decision_gates(client, intent['id'], account['id'])
    draft = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent['id'])).json()
    edit_db(lambda db: set_cash(db, account['id'], 0))
    response = client.post(f"/orders/drafts/{draft['id']}/approve", json={})
    assert response.status_code == 422
    assert 'trusted_account_state' in response.json()['detail']


def test_live_never_uses_paper_capital_as_broker_evidence(client):
    asset = create_asset(client)
    account = create_account(client, mode='live', live_trading_enabled=True)
    intent = create_intent(client, asset['id'], account['id'])
    result = check(client, intent, total_equity=1e12)
    assert 'trusted_broker_account_snapshot_unavailable' in account_state(result)['errors']
    assert account_state(result)['snapshot']['source'] == 'UNVERIFIED'
    assert client.get('/positions').json() == []


def test_request_identity_cannot_select_weaker_account_policy(client):
    from test_decision_gates import setup_gate_ready_order, passing_gate_payload, gate_by_type
    _, account, intent, snapshot = setup_gate_ready_order(client)
    def lower_budget(db):
        budget = db.scalar(select(RiskBudget).where(RiskBudget.account_id == account['id']))
        budget.max_order_notional = 500
    edit_db(lower_budget)
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot, user_id='other-user'))
    assert response.status_code == 201
    gate = gate_by_type(response.json()['gates'], 'RISK_GATE')
    assert 'risk_budget_max_order_notional_exceeded' in gate['blocking_reasons_json']


def test_nonfinite_inputs_rejected_by_schema():
    from pydantic import ValidationError
    from app.schemas import RiskCheckOrderRequest, DecisionGateEvaluateRequest
    for schema, field in [(RiskCheckOrderRequest, 'total_equity'), (DecisionGateEvaluateRequest, 'current_position_pct')]:
        with pytest.raises(ValidationError): schema(order_intent_id='test', **{field: float('nan')})


def test_small_declared_notional_cannot_hide_large_quantity_times_price(client):
    asset, account, _ = setup(client)
    intent = create_intent(client, asset['id'], account['id'], quantity=150, limit_price=100, notional=1)
    result = check(client, intent, max_order_notional=1e9)
    assert not result['hard_rule_passed']
    assert Decimal(result['rules_json']['context']['_server_order_notional']) == 15000
    assert 'max_order_notional' in result['reason']


def test_existing_approved_draft_is_reserved_when_same_intent_creates_another_draft(client):
    asset, account, _ = setup(client)
    draft = create_approved_draft(client, asset=asset, account=account, notional=9000)
    edit_db(lambda db: set_cash(db, account['id'], 10000))
    result = check(client, {'id': draft['order_intent_id']}, total_equity=1e12)
    assert Decimal(account_state(result)['snapshot']['reserved_cash']) == 9000
    assert 'insufficient_available_cash_after_reservations' in account_state(result)['errors']


def test_partial_fill_revalidates_only_remaining_quantity_not_full_original_amount(client):
    asset, account, _ = setup(client)
    draft = create_approved_draft(client, asset=asset, account=account, quantity=10, notional=None, limit_price=100)
    first = client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={'fill_price':100,'fill_quantity':4,'fee_bps':0})
    assert first.status_code == 201
    def update(db):
        set_cash(db, account['id'], 600)
        collateral = Asset(symbol='COLLATERAL',name='Paper collateral',asset_type='etf',market='US',venue='OTHER',currency='USD')
        db.add(collateral)
        db.flush()
        db.add(Position(account_id=account['id'],asset_id=collateral.id,quantity=40,average_cost=100,market_price=100,market_value=4000,unrealized_pnl=0,realized_pnl=0,weight=0))
    edit_db(update)
    second = client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={'fill_price':100,'fill_quantity':6,'fee_bps':0})
    assert second.status_code == 201, second.text
    assert second.json()['execution']['remaining_quantity'] == 0
