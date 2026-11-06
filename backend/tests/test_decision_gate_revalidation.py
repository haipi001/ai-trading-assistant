"""Recheck current self-logic at every Paper workflow boundary."""
import pytest
from sqlalchemy import func, select
from app.models import (
    AuditLog, AutomationPolicy, BehaviorIntervention, BehaviorPattern,
    InvestmentConstitution, InvestmentThesis, OrderIntent, StrategyPlaybook,
    StrategyRule, ThesisCheckpoint, ThesisViolation,
)
from test_decision_gates import setup_rule_gated_order, passing_gate_payload, gate_by_type
from test_research_evidence_revalidation import draft, approve, execute
from test_server_account_risk import edit_db


def prepared(client):
    intent, snapshot_id = setup_rule_gated_order(
        client, rule_type='max_order_notional', conditions={'max_notional': 10000}, notional=500,
    )
    def attach_policy(db):
        policy = AutomationPolicy(
            user_id='user-1', account_id=intent['account_id'], asset_id=intent['asset_id'],
            automation_level='A3_ORDER_DRAFT', max_notional_per_order=10000,
            allowed_actions=['CREATE_ORDER_DRAFT'], forbidden_actions=[], is_active=True,
        )
        db.add(policy)
        db.flush()
        db.get(OrderIntent, intent['id']).automation_policy_id = policy.id
    edit_db(attach_policy)
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot_id))
    assert response.status_code == 201 and response.json()['all_passed'], response.text
    return intent, snapshot_id


def mutate(kind, intent):
    def apply(db):
        order = db.get(OrderIntent, intent['id'])
        thesis = db.get(InvestmentThesis, order.investment_thesis_id)
        if kind == 'thesis_inactive':
            thesis.status = 'invalidated'
        elif kind == 'checkpoint':
            db.add(ThesisCheckpoint(thesis_id=thesis.id, checkpoint_type='invalidation', invalidates_thesis=True))
        elif kind == 'thesis_asset':
            # Existing, unrelated asset to preserve the actual FK.
            from app.models import Asset
            asset = Asset(symbol='OTHER', name='Other', asset_type='stock', market='US', venue='NASDAQ', currency='USD')
            db.add(asset)
            db.flush()
            thesis.asset_id = asset.id
        elif kind == 'forbidden_asset':
            constitution = db.scalar(select(InvestmentConstitution).where(InvestmentConstitution.user_id == 'user-1'))
            constitution.forbidden_assets = [intent['asset_id']]
        elif kind == 'class_limit':
            constitution = db.scalar(select(InvestmentConstitution).where(InvestmentConstitution.user_id == 'user-1'))
            constitution.max_asset_class_pct = 0.001
        elif kind == 'playbook_inactive':
            db.get(StrategyPlaybook, thesis.strategy_playbook_id).is_active = False
        elif kind == 'rule':
            rule = db.scalar(select(StrategyRule).where(StrategyRule.strategy_playbook_id == thesis.strategy_playbook_id))
            rule.conditions_json = {'max_notional': 50}
        elif kind == 'confidence':
            rule = db.scalar(select(StrategyRule).where(StrategyRule.strategy_playbook_id == thesis.strategy_playbook_id))
            rule.rule_type, rule.conditions_json = 'min_thesis_confidence', {'min_confidence': 0.9}
        elif kind == 'behavior_block':
            db.add(BehaviorIntervention(user_id='user-1', order_intent_id=order.id,
                intervention_level='BLOCK', message='Persisted control fixture'))
        elif kind == 'policy_asset':
            from app.models import Asset
            asset = Asset(symbol='POLICY-OTHER', name='Other policy scope', asset_type='stock', market='US', venue='NASDAQ', currency='USD')
            db.add(asset)
            db.flush()
            db.get(AutomationPolicy, order.automation_policy_id).asset_id = asset.id
        elif kind == 'policy_inactive':
            db.get(AutomationPolicy, order.automation_policy_id).is_active = False
    edit_db(apply)


@pytest.mark.parametrize('stage', ['draft', 'approval', 'execution'])
@pytest.mark.parametrize('kind', [
    'thesis_inactive', 'checkpoint', 'thesis_asset', 'forbidden_asset', 'class_limit',
    'playbook_inactive', 'rule', 'confidence', 'behavior_block', 'policy_inactive', 'policy_asset',
])
def test_current_self_logic_changes_block_every_boundary(client, kind, stage):
    intent, _ = prepared(client)
    record = draft(client, intent) if stage != 'draft' else None
    if stage == 'execution':
        assert approve(client, record).status_code == 201
    mutate(kind, intent)
    if stage == 'draft':
        from test_risk_approval import risk_payload
        response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent['id']))
    else:
        response = approve(client, record) if stage == 'approval' else execute(client, record)
    assert response.status_code == 422, response.text
    assert 'current decision gates blocked' in response.json()['detail']
    assert client.get('/paper-executions').json() == []
    def inspect(db):
        assert db.scalar(select(AuditLog.id).where(AuditLog.entity_id == intent['id'],
            AuditLog.action == 'decision_gate.revalidation_blocked')) is not None
        # Revalidation must not manufacture behavior detections/violations.
        assert db.scalar(select(func.count()).select_from(ThesisViolation).where(
            ThesisViolation.related_order_intent_id == intent['id'])) == 0
    edit_db(inspect)


def test_hard_confirm_requires_explicit_response_but_unrelated_intervention_does_not_block(client):
    intent, _ = prepared(client)
    record = draft(client, intent)
    ids = []
    def add(db):
        other = db.scalar(select(OrderIntent).where(OrderIntent.id != intent['id']))
        db.add(BehaviorIntervention(user_id='user-1', order_intent_id=other.id,
            intervention_level='BLOCK', message='Unrelated order'))
        item = BehaviorIntervention(user_id='user-1', order_intent_id=intent['id'],
            intervention_level='HARD_CONFIRM', message='Confirm fixture')
        db.add(item)
        db.flush()
        ids.append(item.id)
    edit_db(add)
    assert approve(client, record).status_code == 422
    response = client.post(f'/behavior/interventions/{ids[0]}/respond', json={
        'user_response': 'Explicitly confirmed in isolated test', 'bypassed': True,
    })
    assert response.status_code == 200, response.text
    assert approve(client, record).status_code == 201
    response = execute(client, record)
    assert response.status_code == 201, response.text


def test_repeated_thesis_failure_does_not_duplicate_violations_or_patterns(client):
    intent, _ = prepared(client)
    record = draft(client, intent)
    mutate('checkpoint', intent)
    for _ in range(2):
        assert approve(client, record).status_code == 422
    def inspect(db):
        assert db.scalar(select(func.count()).select_from(ThesisViolation)) == 0
        assert db.scalar(select(func.count()).select_from(BehaviorPattern)) == 0
    edit_db(inspect)


def test_direct_playbook_rules_apply_without_thesis_and_missing_confidence_fails_closed(client):
    intent, snapshot_id = prepared(client)
    def direct(db):
        order = db.get(OrderIntent, intent['id'])
        thesis = db.get(InvestmentThesis, order.investment_thesis_id)
        order.strategy_playbook_id = thesis.strategy_playbook_id
        order.investment_thesis_id = None
        rule = db.scalar(select(StrategyRule).where(StrategyRule.strategy_playbook_id == thesis.strategy_playbook_id))
        rule.rule_type, rule.conditions_json = 'min_thesis_confidence', {'min_confidence': 0.5}
    edit_db(direct)
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot_id))
    result = gate_by_type(response.json()['gates'], 'RISK_GATE')
    assert result['status'] == 'BLOCKED'
    assert any('strategy_rule:min_thesis_confidence:' in reason for reason in result['blocking_reasons_json'])
