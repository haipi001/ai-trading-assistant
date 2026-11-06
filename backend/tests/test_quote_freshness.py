from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import delete, select
from app.models import Quote
from test_server_account_risk import edit_db
from test_decision_gates import setup_gate_ready_order, passing_gate_payload, gate_by_type

@pytest.mark.parametrize('case,reason', [('missing','latest_quote_missing'),('stale','latest_quote_stale'),('future','latest_quote_in_future'),('zero','latest_quote_price_invalid')])
def test_request_cannot_disable_server_quote_validation(client, case, reason):
    asset, _, intent, snapshot = setup_gate_ready_order(client)
    def update(db):
        if case == 'missing':
            db.execute(delete(Quote).where(Quote.asset_id == asset['id']))
        else:
            for quote in db.scalars(select(Quote).where(Quote.asset_id == asset['id'])):
                if case == 'stale': quote.as_of = datetime.now(timezone.utc) - timedelta(hours=2)
                if case == 'future': quote.as_of = datetime.now(timezone.utc) + timedelta(hours=2)
                if case == 'zero': quote.price = 0
    edit_db(update)
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot, latest_quote_required=False, max_quote_age_seconds=999999))
    assert response.status_code == 201
    gate = gate_by_type(response.json()['gates'], 'EXECUTION_GATE')
    assert reason in gate['blocking_reasons_json']


def test_quote_expiring_after_approval_blocks_paper_execution(client):
    from test_paper_execution import create_approved_draft
    draft = create_approved_draft(client)
    intent = client.get(f"/orders/intents/{draft['order_intent_id']}").json()
    def expire(db):
        for quote in db.scalars(select(Quote).where(Quote.asset_id == intent['asset_id'])):
            quote.as_of = datetime.now(timezone.utc) - timedelta(hours=2)
    edit_db(expire)
    response = client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={})
    assert response.status_code == 422
    assert 'latest_quote_stale' in response.json()['detail']
    assert client.get('/paper-executions').json() == []
