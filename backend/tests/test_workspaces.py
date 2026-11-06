from test_trade_permissions import managed_actor


def payload(version=0):
    return {'expected_version':version,'context':{'page':'market','asset_class':'crypto_spot','symbol':'BTC','venue':'OKX','timeframe':'1h','mode':None}}


def test_workspace_persists_and_rejects_stale_writers(client):
    url='/api/v2/workspaces/terminal-main'
    assert client.get(url).status_code == 404
    first=client.put(url,json=payload())
    assert first.status_code == 200
    assert first.json()['version']==1
    assert first.json()['execution_authorized'] is False
    assert client.put(url,json=payload()).status_code==409
    assert client.put(url,json=payload(1)).json()['version']==2
    assert client.put(url,json=payload(1)).status_code==409
    assert client.get(url).json()['version']==2


def test_workspace_isolated_by_session_even_for_same_workspace_name(client,managed_actor):
    managed_actor('owner')
    headers={'Authorization':'Bearer fixture'}
    assert client.put('/api/v2/workspaces/terminal-main',json=payload(),headers=headers).status_code==200
    # A local header cannot override the verified session's namespace.
    result=client.get('/api/v2/workspaces/terminal-main',headers={**headers,'X-AI-Trading-User':'someone-else'})
    assert result.json()['version']==1
    assert client.get('/api/v2/workspaces/terminal-main').status_code==401


def test_workspace_preferences_cannot_accept_secrets_or_grant_trading(client):
    value=payload();value['context']['api_key']='fixture'
    assert client.put('/api/v2/workspaces/main',json=value).status_code==422
    value=payload();value['layout']={'trade_enabled':True}
    assert client.put('/api/v2/workspaces/main',json=value).status_code==422
    value=payload();value['context']['account_id']='other-account'
    assert client.put('/api/v2/workspaces/main',json=value).status_code==404


def test_distinct_local_users_do_not_share_workspace_records(client):
    url='/api/v2/workspaces/main'
    assert client.put(url,json=payload(),headers={'X-AI-Trading-User':'a'}).status_code==200
    assert client.get(url,headers={'X-AI-Trading-User':'b'}).status_code==404
    assert client.put(url,json=payload(),headers={'X-AI-Trading-User':'b'}).json()['version']==1


def test_terminal_panels_keep_onchain_identity_and_cannot_hide_foreign_accounts(client):
    value=payload()
    chain={'page':'chain','asset_class':'onchain','market':'onchain','chain_id':'1',
           'contract_address':'0x'+'a'*40,'context_version':7,'mode':None}
    value['layout']={'panel_count':4,'focused_panel':1,'panels':[
        {'panel_id':1,'function_code':'R042','locked':True,'context':chain}]}
    saved=client.put('/api/v2/workspaces/terminal-panels',json=value)
    assert saved.status_code==200
    assert saved.json()['layout']['panels'][0]['context']['contract_address']==chain['contract_address']
    assert saved.json()['execution_authorized'] is False
    value['expected_version']=1
    value['layout']['panels'][0]['context']['account_id']='another-user-account'
    assert client.put('/api/v2/workspaces/terminal-panels',json=value).status_code==404
    del value['layout']['panels'][0]['context']['account_id']
    value['layout']['panels'][0]['context']['wallet_id']='another-wallet'
    assert client.put('/api/v2/workspaces/terminal-panels',json=value).status_code==404


def test_terminal_workspace_rejects_conflicting_panels_and_chain_identity(client):
    value=payload()
    panel={'panel_id':0,'function_code':'R009','locked':False,'context':value['context'].copy()}
    value['layout']={'panel_count':2,'focused_panel':0,'panels':[panel,panel]}
    assert client.put('/api/v2/workspaces/terminal-panels',json=value).status_code==422
    value['layout']['panels']=[panel]
    panel['context']['market']='stocks';panel['context']['chain_id']='1'
    assert client.put('/api/v2/workspaces/terminal-panels',json=value).status_code==422


def test_terminal_origin_cors_preflight(client):
    response=client.options('/api/v2/workspaces/terminal-main',headers={
        'Origin':'http://127.0.0.1:8850','Access-Control-Request-Method':'PUT',
        'Access-Control-Request-Headers':'authorization,content-type'})
    assert response.status_code==200
    assert response.headers['access-control-allow-origin']=='http://127.0.0.1:8850'


def test_terminal_market_memory_and_split_roundtrip_and_ownership(client):
    value=payload()
    value['context']['market']='cex'
    value['layout']={'panel_count':2,'focused_panel':0,'split_columns':.65,'split_rows':.4,
        'market_contexts':[value['context'].copy()],
        'panels':[{'panel_id':0,'function_code':'GP','terminal_symbol':'NVDA','context':value['context'].copy()}]}
    response=client.put('/api/v2/workspaces/remembered-markets',json=value)
    assert response.status_code==200
    assert response.json()['layout']['split_columns']==.65
    assert response.json()['layout']['panels'][0]['terminal_symbol']=='NVDA'
    value['expected_version']=1
    value['layout']['market_contexts'][0]['account_id']='hidden-other-account'
    assert client.put('/api/v2/workspaces/remembered-markets',json=value).status_code==404
    del value['layout']['market_contexts'][0]['account_id']
    value['layout']['market_contexts'].append(value['layout']['market_contexts'][0].copy())
    assert client.put('/api/v2/workspaces/remembered-markets',json=value).status_code==422
    value['layout']['market_contexts']=[];value['layout']['split_rows']=.9
    assert client.put('/api/v2/workspaces/remembered-markets',json=value).status_code==422


def test_workspace_session_context_respects_server_auth_policy(client,managed_actor,monkeypatch):
    from app.core.config import Settings
    settings=Settings(managed_auth_required=False,beta_auth_required=False,api_rate_limit_enabled=False)
    for module in ['app.core.auth_middleware','app.core.auth','app.api.workspaces']:
        monkeypatch.setattr(module+'.get_settings',lambda:settings)
    local=client.get('/api/v2/workspaces/session/context')
    assert local.status_code==200
    assert local.json()['auth_mode']=='local'
    assert local.json()['execution_authorized'] is False
    assert 'session_token' not in local.json()
    settings.managed_auth_required=True
    managed_actor('owner')
    assert client.get('/api/v2/workspaces/session/context').status_code==401
    managed=client.get('/api/v2/workspaces/session/context',headers={'Authorization':'Bearer fixture'})
    assert managed.status_code==200
    assert managed.json()['auth_mode']=='managed'
    assert managed.json()['execution_authorized'] is False


def seed_identity_options(owner):
    from app.main import app
    from app.db.session import get_db
    from app.models import Account, Wallet
    session=app.dependency_overrides[get_db]()
    db=next(session)
    try:
        db.add_all([
            Account(id='own-stock',user_id=owner,name='Stock Paper',account_type='brokerage',broker='mock',base_currency='USD',mode='paper'),
            Account(id='own-cex',user_id=owner,name='CEX Read',account_type='exchange_account',broker='mock',base_currency='USDT',mode='read_only'),
            Account(id='foreign-account',user_id='foreign',name='Foreign',account_type='brokerage',broker='mock',base_currency='USD',mode='paper'),
            Wallet(id='own-eth',user_id=owner,address='0x'+'1'*40,chain='ethereum',label='ETH'),
            Wallet(id='own-base',user_id=owner,address='0x'+'2'*40,chain='base',label='Base'),
            Wallet(id='inactive-wallet',user_id=owner,address='0x'+'3'*40,chain='ethereum',is_active=False),
            Wallet(id='foreign-wallet',user_id='foreign',address='0x'+'4'*40,chain='ethereum'),
        ])
        db.commit()
    finally:
        session.close()


def test_identity_options_are_owned_readonly_metadata_with_explicit_market_and_chain(client):
    seed_identity_options('identity-test')
    headers={'X-AI-Trading-User':'identity-test'}
    response=client.get('/api/v2/workspaces/session/options',headers=headers)
    assert response.status_code==200
    result=response.json()
    assert result['execution_authorized'] is False
    assert {a['id'] for a in result['accounts']}=={'own-stock','own-cex'}
    assert {w['id'] for w in result['wallets']}=={'own-eth','own-base'}
    assert next(a for a in result['accounts'] if a['id']=='own-stock')['markets']==['stocks']
    assert next(a for a in result['accounts'] if a['id']=='own-cex')['paper_eligible'] is False
    assert {w['chain_id'] for w in result['wallets']}=={'1','8453'}
    assert 'session_token' not in response.text and 'api_key' not in response.text
    assert client.get('/api/v2/workspaces/session/options',headers={'X-AI-Trading-User':'other'}).json()['accounts']==[]


def test_identity_options_require_managed_session_and_ignore_spoofed_local_identity(client,managed_actor):
    seed_identity_options('tenant-trade-test')
    managed_actor('viewer')
    assert client.get('/api/v2/workspaces/session/options').status_code==401
    result=client.get('/api/v2/workspaces/session/options',headers={'Authorization':'Bearer fixture','X-AI-Trading-User':'foreign'})
    assert result.status_code==200
    assert result.json()['user_id']=='tenant-trade-test'
    assert {a['id'] for a in result.json()['accounts']}=={'own-stock','own-cex'}


def test_workspace_rejects_owned_but_incompatible_account_or_wallet(client):
    seed_identity_options('identity-test')
    headers={'X-AI-Trading-User':'identity-test'}
    value=payload();value['context'].update(market='cex',account_id='own-stock')
    assert client.put('/api/v2/workspaces/incompatible',json=value,headers=headers).status_code==422

    value=payload();value['context']={'page':'chain','asset_class':'onchain','market':'onchain','chain_id':'8453','wallet_id':'own-eth'}
    assert client.put('/api/v2/workspaces/incompatible',json=value,headers=headers).status_code==422
    value['context']['wallet_id']='own-base'
    assert client.put('/api/v2/workspaces/incompatible',json=value,headers=headers).status_code==200
    value['expected_version']=1;value['context'].update(chain_id='1',wallet_id='inactive-wallet')
    assert client.put('/api/v2/workspaces/incompatible',json=value,headers=headers).status_code==422


def test_market_workspaces_preserve_inactive_panels_and_validate_hidden_lock_ownership(client):
    from copy import deepcopy
    value=payload();value['context']['market']='cex'
    view={'market':'cex','panel_count':2,'focused_panel':1,'last_function_code':'R009','last_terminal_symbol':'',
          'split_columns':.65,'split_rows':.4,
          'panels':[{'panel_id':i,'function_code':'R009' if i==0 else 'HELP','context':deepcopy(value['context'])} for i in range(4)],
          'locked_contexts':[{'key':'main:R009','context':deepcopy(value['context'])}]}
    value['layout']={'market_workspaces':[view]}
    response=client.put('/api/v2/workspaces/market-layouts',json=value)
    assert response.status_code==200
    saved=response.json()['layout']['market_workspaces'][0]
    assert len(saved['panels'])==4 and saved['focused_panel']==1 and saved['split_columns']==.65
    assert saved['locked_contexts'][0]['key']=='main:R009'
    value['expected_version']=1
    view['locked_contexts'][0]['context']['account_id']='foreign-account'
    assert client.put('/api/v2/workspaces/market-layouts',json=value).status_code==404
    del view['locked_contexts'][0]['context']['account_id']
    value['layout']['market_workspaces'].append(deepcopy(view))
    assert client.put('/api/v2/workspaces/market-layouts',json=value).status_code==422
    value['layout']['market_workspaces'].pop()
    view['panels'][3]['panel_id']=2
    assert client.put('/api/v2/workspaces/market-layouts',json=value).status_code==422
    assert client.get('/api/v2/workspaces/market-layouts').json()['version']==1
