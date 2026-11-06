"""Human Paper reasoning uses server-issued market evidence, without an AI report."""
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.models import DataSnapshot, ManualTradeEvidence, OrderIntent, Quote, ResearchReport
from test_decision_gates import create_asset, create_account, create_constitution, create_risk_budget, passing_gate_payload, gate_by_type
from test_risk_approval import risk_payload
from test_research_evidence_revalidation import approve, execute
from test_server_account_risk import edit_db


def setup(client, **overrides):
    asset, account = create_asset(client), create_account(client)
    constitution = create_constitution(client)
    create_risk_budget(client, constitution['id'], account['id'])
    response = client.post('/orders/intents', json={
        'source_type': 'manual', 'asset_id': asset['id'], 'account_id': account['id'],
        'side': 'buy', 'order_type': 'limit', 'quantity': 1, 'limit_price': 225.12,
        'rationale': 'Explicit manual fixture rationale', 'user_rationale': 'Human decision without AI report',
    } | overrides)
    assert response.status_code == 201
    assert client.post('/mock/update-quotes').status_code == 200
    return asset, account, response.json()


def prepare(client, intent):
    return client.post(f"/orders/intents/{intent['id']}/manual-evidence")


def evaluate(client, intent, snapshot_id, **overrides):
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def make_draft(client, intent, snapshot_id):
    gates = evaluate(client, intent, snapshot_id)
    assert gates['all_passed'], gates
    response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent['id']))
    assert response.status_code == 201, response.text
    return response.json()


def test_manual_paper_full_api_flow_without_research_reports(client):
    _, _, intent = setup(client)
    response = prepare(client, intent)
    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence['evidence_mode'] == 'manual_paper_quote' and evidence['quote_source'] == 'mock'
    record = make_draft(client, intent, evidence['data_snapshot_id'])
    assert record['approval_status'] == 'pending'
    assert execute(client, record).status_code == 422
    assert approve(client, record).status_code == 201
    filled = execute(client, record)
    assert filled.status_code == 201, filled.text
    assert client.get('/reports').json() == []
    assert len(client.get('/paper-executions').json()) == 1
    restored = client.get(f"/orders/intents/{intent['id']}/manual-evidence")
    assert restored.status_code == 200 and restored.json()['data_snapshot_id'] == evidence['data_snapshot_id']
    assert execute(client, record).status_code == 422


@pytest.mark.parametrize('overrides', [
    {'source_type': 'research_report'}, {'source_type': 'controlled_auto'}, {'user_rationale': ''},
    {'order_type': 'market'}, {'quantity': 0}, {'limit_price': 0},
    {'evidence_json': {'report_id': 'pretend-report'}},
])
def test_manual_evidence_cannot_be_used_for_nonmanual_or_invalid_orders(client, overrides):
    _, _, intent = setup(client, **overrides)
    response = prepare(client, intent)
    assert response.status_code == 422


@pytest.mark.parametrize('kind', ['missing', 'stale', 'future', 'zero'])
def test_manual_evidence_rejects_unusable_server_quote(client, kind):
    asset, _, intent = setup(client)
    def change(db):
        quotes = db.scalars(select(Quote).where(Quote.asset_id == asset['id'])).all()
        for quote in quotes:
            if kind == 'missing': db.delete(quote)
            elif kind == 'zero': quote.price = 0
            else: quote.as_of = datetime.now(timezone.utc) + timedelta(seconds=600 if kind == 'future' else -901)
    edit_db(change)
    assert prepare(client, intent).status_code == 422


def test_manual_evidence_is_paper_only(client):
    _, account, intent = setup(client)
    from app.models import Account
    edit_db(lambda db: setattr(db.get(Account, account['id']), 'mode', 'live'))
    assert prepare(client, intent).status_code == 422


def test_forged_snapshot_and_caller_disable_flags_do_not_replace_server_evidence(client):
    _, _, intent = setup(client)
    snapshots = []
    def forge(db):
        snapshot = DataSnapshot(snapshot_type='manual_paper_quote', data_json={'quotes': []}, metadata_json={'ai_used': False})
        db.add(snapshot); db.flush(); snapshots.append(snapshot.id)
    edit_db(forge)
    result = evaluate(client, intent, snapshots[0], research_report_required=False, quality_report_required=False)
    gate = gate_by_type(result['gates'], 'RESEARCH_GATE')
    assert gate['status'] == 'BLOCKED'
    assert 'research_report_missing' in gate['blocking_reasons_json']
    assert 'data_quality_report_missing' in gate['blocking_reasons_json']


@pytest.mark.parametrize('kind', ['snapshot', 'quantity', 'rationale', 'expired', 'quote'])
def test_manual_evidence_changes_block_approved_execution(client, kind):
    _, _, intent = setup(client)
    evidence = prepare(client, intent).json()
    record = make_draft(client, intent, evidence['data_snapshot_id'])
    assert approve(client, record).status_code == 201
    def change(db):
        if kind == 'snapshot':
            db.get(DataSnapshot, evidence['data_snapshot_id']).data_json = {'forged': True}
        elif kind == 'expired':
            db.get(ManualTradeEvidence, evidence['data_snapshot_id']).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif kind == 'quote':
            db.get(Quote, evidence['quote_id']).price = 226
        else:
            setattr(db.get(OrderIntent, intent['id']), 'quantity' if kind == 'quantity' else 'user_rationale',
                    2 if kind == 'quantity' else 'changed reason')
    edit_db(change)
    assert execute(client, record).status_code == 422
    assert client.get('/paper-executions').json() == []


def test_manual_snapshot_cannot_be_reused_by_another_intent(client):
    asset, account, intent = setup(client)
    evidence = prepare(client, intent).json()
    other = client.post('/orders/intents', json={
        'source_type': 'manual', 'asset_id': asset['id'], 'account_id': account['id'], 'side': 'buy',
        'order_type': 'limit', 'quantity': 1, 'limit_price': 225.12, 'rationale': 'Other', 'user_rationale': 'Other human',
        'evidence_json': {'manual_snapshot_id': evidence['data_snapshot_id']},
    }).json()
    assert not evaluate(client, other, evidence['data_snapshot_id'])['all_passed']


def test_other_tenant_cannot_read_or_reprepare_manual_evidence(client, monkeypatch):
    from app.core.auth import AuthenticatedUser, ROLE_PERMISSIONS
    from app.core.config import Settings
    _, _, intent = setup(client)
    assert prepare(client, intent).status_code == 201
    settings = Settings(managed_auth_required=True, beta_auth_required=False, api_rate_limit_enabled=False)
    monkeypatch.setattr('app.core.auth_middleware.get_settings', lambda: settings)
    monkeypatch.setattr('app.core.auth.get_settings', lambda: settings)
    actor = AuthenticatedUser('unrelated-tenant', 'owner', ROLE_PERMISSIONS['owner'], True, True)
    monkeypatch.setattr('app.core.auth_middleware.ManagedAuthService.authenticate', lambda *_: actor)
    url = f"/orders/intents/{intent['id']}/manual-evidence"
    headers = {'Authorization': 'Bearer isolated-test-session'}
    assert client.get(url, headers=headers).status_code == 404
    assert client.post(url, headers=headers).status_code in {404, 422}


def test_corrupted_manual_evidence_cannot_be_read_as_a_valid_receipt(client):
    _, _, intent = setup(client)
    evidence = prepare(client, intent).json()
    edit_db(lambda db: setattr(db.get(DataSnapshot, evidence['data_snapshot_id']), 'data_json', {'forged': True}))
    response = client.get(f"/orders/intents/{intent['id']}/manual-evidence")
    assert response.status_code == 404
    assert 'inconsistent' in response.json()['detail']
