from test_trade_permissions import managed_actor
from test_workspaces import seed_identity_options


def body():
    return {'account_id':'own-stock','market':'stocks','context_version':3,'parameters':{'name':'Manual strategy','coin':'AAPL','type':'DCA','amount':'100','platform':'mock','risk':'bounded','trigger':'weekly','invalidation':'manual pause','constraints':'no leverage'}}


def test_strategy_material_is_owned_private_and_never_trade_authority(client):
    seed_identity_options('strategy-owner')
    headers={'X-AI-Trading-User':'strategy-owner'}
    response=client.post('/api/v2/workspaces/research/strategy-material',json=body(),headers=headers)
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    value=response.json()
    assert value['material']['parameters']==body()['parameters']
    assert value['material']['source']=='user_local_strategy_parameters'
    assert value['execution_available'] is False
    assert value['material']['usable_for_trading'] is False
    url='/api/v2/workspaces/research/strategy-material/'+value['snapshot_id']
    assert client.get(url,headers=headers).json()==value
    assert client.get(url,headers={'X-AI-Trading-User':'foreign'}).status_code==404


def test_strategy_material_rejects_foreign_account_market_unknown_fields_and_invalid_amount(client):
    seed_identity_options('strategy-owner')
    headers={'X-AI-Trading-User':'strategy-owner'}
    for amount in ['0','-1','NaN','Infinity','1e4']:
        value=body();value['parameters']['amount']=amount
        assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==422
    value=body();value['parameters']['api_key']='fixture'
    assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==422
    value=body();value['account_id']='foreign-account'
    assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==404
    value=body();value['market']='cex'
    assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==422


def test_strategy_material_requires_managed_permission(client,managed_actor):
    seed_identity_options('tenant-trade-test')
    managed_actor('viewer')
    url='/api/v2/workspaces/research/strategy-material'
    assert client.post(url,json=body()).status_code==401
    assert client.post(url,json=body(),headers={'Authorization':'Bearer fixture'}).status_code==403


def test_grid_material_preserves_typed_configuration_and_rejects_invalid_grid(client):
    seed_identity_options('strategy-owner');headers={'X-AI-Trading-User':'strategy-owner'}
    grid={'kind':'arithmetic_grid','lower':'100','upper':'200','intervals':10}
    value=body();value['parameters']['grid']=grid
    result=client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers)
    assert result.status_code==200
    assert result.json()['material']['parameters']['grid']==grid
    for patch in [{'intervals':True},{'intervals':2.5},{'intervals':501},{'upper':'99'},{'lower':'NaN'},{'leverage':10}]:
        value=body();value['parameters']['grid']={**grid,**patch}
        assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==422


def test_strategy_material_preserves_declared_units_and_rejects_wrong_stock_budget_currency(client):
    seed_identity_options('strategy-owner');headers={'X-AI-Trading-User':'strategy-owner'}
    value=body();value['parameters'].update(budget_currency='USD',quote_currency='USD')
    result=client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers)
    assert result.status_code==200
    assert result.json()['material']['parameters']['budget_currency']=='USD'
    value['parameters']['budget_currency']='EUR'
    assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==422


def test_spot_dca_material_preserves_plan_and_rejects_invalid_dates_or_mixed_configuration(client):
    seed_identity_options('strategy-owner');headers={'X-AI-Trading-User':'strategy-owner'}
    dca={'kind':'spot_dca','frequency':'每周','first_run_local':'2027-01-02T09:30','take_profit_percent':'20'}
    value=body();value['parameters']['dca']=dca
    result=client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers)
    assert result.status_code==200
    assert result.json()['material']['parameters']['dca']==dca
    for patch in [{'frequency':'每秒'},{'first_run_local':'2027-02-30T09:30'},{'first_run_local':'2027-01-02T09:30Z'},{'take_profit_percent':'NaN'},{'take_profit_percent':'0'},{'execute':True}]:
        value=body();value['parameters']['dca']={**dca,**patch}
        assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==422
    value=body();value['parameters']['dca']=dca;value['parameters']['grid']={'kind':'arithmetic_grid','lower':'100','upper':'200','intervals':10}
    assert client.post('/api/v2/workspaces/research/strategy-material',json=value,headers=headers).status_code==422
