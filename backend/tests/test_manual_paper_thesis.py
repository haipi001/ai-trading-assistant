import pytest
from sqlalchemy import select,func
from app.models import Account,Asset,OrderIntent,OrderDraft,Execution,AgentRun
from test_risk_approval import create_asset,create_account
from test_server_account_risk import edit_db


def business_counts():
    result=[]
    def read(db):
        result.extend(db.scalar(select(func.count()).select_from(model)) for model in [OrderIntent,OrderDraft,Execution,AgentRun])
    edit_db(read)
    return result


def payload(asset,account):
    return {'asset_id':asset['id'],'account_id':account['id'],'entry_reason':'Explicit human investment rationale.',
        'key_drivers':['Evidence to verify'],'invalidation_conditions':['Observed thesis break'],
        'expected_horizon':'swing','target_condition':'Review after original evidence changes.',
        'max_loss_tolerance_pct':.02,'confidence':.6}


@pytest.mark.parametrize('market',['stocks','cex'])
def test_manual_thesis_is_user_owned_without_order_or_agent_run(client,market):
    asset=create_asset(client);account=create_account(client)
    if market=='cex':
        def configure(db):
            crypto=db.get(Asset,asset['id']);crypto.asset_type='crypto';crypto.symbol='BTC';crypto.market='GLOBAL';crypto.venue='CEX'
            db.get(Account,account['id']).account_type='exchange_account'
        edit_db(configure)
    before=business_counts()
    response=client.post('/theses/manual-paper',json=payload(asset,account))
    assert response.status_code==201,response.text
    result=response.json();thesis=result['thesis']
    assert result['execution_available'] is False
    assert thesis['user_id']=='default-user'
    assert thesis['asset_id']==asset['id'] and thesis['account_id']==account['id']
    assert thesis['source']=='terminal_manual' and thesis['status']=='active'
    assert thesis['position_plan_json']=={'execution_available':False,'human_authored':True}
    assert thesis['data_snapshot_id'] is None
    assert business_counts()==before
    audit=client.get('/audit-logs').json()
    assert any(row['action']=='terminal.manual_thesis.created' and row['entity_id']==thesis['id'] for row in audit)


@pytest.mark.parametrize('kind,status', [('foreign',404),('live',422),('market',422),('chain',422),('spoof',422),('blank',422)])
def test_manual_thesis_rejects_invalid_scope_and_ownership(client,kind,status):
    asset=create_asset(client);account=create_account(client);body=payload(asset,account)
    def modify(db):
        if kind=='foreign':db.get(Account,account['id']).user_id='other-user'
        if kind=='live':db.get(Account,account['id']).mode='live'
        if kind=='market':db.get(Account,account['id']).account_type='exchange_account'
        if kind=='chain':db.get(Asset,asset['id']).chain_id='8453'
    edit_db(modify)
    if kind=='spoof':body['user_id']='other-user'
    if kind=='blank':body['entry_reason']='   '
    response=client.post('/theses/manual-paper',json=body)
    assert response.status_code==status,response.text
    assert client.get('/investment-theses').json()==[]
    assert business_counts()==[0,0,0,0]

from test_trade_permissions import managed_actor

def test_viewer_cannot_create_manual_paper_thesis(client,managed_actor):
    managed_actor('owner')
    headers={'Authorization':'Bearer controlled'}
    asset_response=client.post('/assets',headers=headers,json={'symbol':'AAPL','name':'Controlled stock','asset_type':'stock','market':'US','venue':'NASDAQ','currency':'USD'})
    account_response=client.post('/accounts',headers=headers,json={'name':'Owned Paper','account_type':'brokerage','broker':'mock','base_currency':'USD','mode':'paper'})
    assert asset_response.status_code==201,asset_response.text
    assert account_response.status_code==201,account_response.text
    asset,account=asset_response.json(),account_response.json()
    created=client.post('/theses/manual-paper',headers=headers,json=payload(asset,account))
    assert created.status_code==201,created.text
    assert created.json()['thesis']['user_id']=='tenant-trade-test'
    managed_actor('viewer')
    response=client.post('/theses/manual-paper',headers={'Authorization':'Bearer controlled'},json=payload(asset,account))
    assert response.status_code==403,response.text
    assert business_counts()==[0,0,0,0]
