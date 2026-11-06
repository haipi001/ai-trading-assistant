from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.models import Approval, OrderDraft, OrderIntent
from test_paper_execution import create_approved_draft
from test_server_account_risk import edit_db

@pytest.mark.parametrize('field,value', [('notional', 300), ('side','sell'), ('account_id','different-account'), ('limit_price',99)])
def test_order_mutation_invalidates_human_approval(client, field, value):
    draft = create_approved_draft(client)
    def mutate(db):
        intent = db.get(OrderIntent, draft['order_intent_id'])
        setattr(intent, field, value)
    edit_db(mutate)
    response = client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={})
    assert response.status_code == 422
    # Missing account is also fail-closed before grant validation.
    assert any(text in response.json()['detail'] for text in ['terms changed', 'unavailable'])
    assert client.get('/paper-executions').json() == []

@pytest.mark.parametrize('offset', [-600, 600])
def test_expired_or_future_approval_cannot_be_extended_by_json_policy(client, offset):
    draft = create_approved_draft(client)
    def mutate(db):
        approval = db.scalar(select(Approval).where(Approval.order_draft_id == draft['id']))
        approval.decided_at = datetime.now(timezone.utc) + timedelta(seconds=offset)
        record = db.get(OrderDraft, draft['id'])
        record.approval_policy = {**record.approval_policy, 'grant':{**record.approval_policy['grant'], 'ttl_seconds':99999999}}
    edit_db(mutate)
    response = client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={})
    assert response.status_code == 422
    assert 'approval expired' in response.json()['detail']
    assert client.get('/paper-executions').json() == []

def test_legacy_approved_status_without_persisted_grant_requires_reapproval(client):
    draft = create_approved_draft(client)
    def remove_grant(db):
        record = db.get(OrderDraft, draft['id'])
        record.approval_policy = {'required':True}
    edit_db(remove_grant)
    assert client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={}).status_code == 422
    assert client.post(f"/orders/drafts/{draft['id']}/approve", json={}).status_code == 201
    result = client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={"fill_price":225.12})
    assert result.status_code == 201, result.text

def test_modifying_draft_clears_grant(client):
    draft = create_approved_draft(client)
    response = client.post(f"/orders/drafts/{draft['id']}/modify", json={})
    assert response.status_code == 200
    assert 'grant' not in response.json()['approval_policy']
    assert client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={}).status_code == 422
