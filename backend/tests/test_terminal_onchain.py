from contextlib import contextmanager
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.main import app
from app.db.session import get_db
from app.models import Wallet, DataSnapshot, AuditLog, TokenAllowance, ProtocolPosition
from app.models.core import utc_now
from app.adapters.evm_rpc_readonly import EvmRpcReadOnlyAdapter, EvmRpcError
from test_trade_permissions import managed_actor

ADDRESS='0x'+'1'*40
CONTRACT='0x'+'a'*40
URL='/api/v2/workspaces/onchain/wallet-a'

@contextmanager
def database():
    gen=app.dependency_overrides[get_db]()
    try:
        yield next(gen)
    finally:
        gen.close()


def seed_wallet(owner='default-user', active=True):
    with database() as db:
        db.add(Wallet(id='wallet-a',user_id=owner,address=ADDRESS,chain='ethereum',is_active=active))
        db.commit()


def mock_rpc(monkeypatch, *, decimals=6, fail=False, chain='0x1'):
    calls=[]
    def request(self,payload):
        calls.append(payload)
        if fail:
            raise EvmRpcError('controlled timeout with private endpoint text')
        method=payload['method']
        if method=='eth_chainId':result=chain
        elif method=='eth_blockNumber':result='0x1234'
        elif method=='eth_getBalance':result=hex(10**18+1)
        elif payload['params'][0]['data']=='0x313ce567':result=hex(decimals)
        else:result=hex(1234567)
        return {'result':result}
    monkeypatch.setattr(EvmRpcReadOnlyAdapter,'_request',request)
    return calls


def test_snapshot_pins_balances_and_metadata_to_verified_block_without_float_loss(monkeypatch):
    calls=mock_rpc(monkeypatch)
    adapter=EvmRpcReadOnlyAdapter.for_chain('ethereum')
    result=adapter.read_wallet_snapshot(ADDRESS,CONTRACT)
    assert result['block_number']==0x1234
    assert result['chain_id']=='1'
    assert result['balances'][0]['amount']=='1.000000000000000001'
    assert result['balances'][1]['amount']=='1.234567'
    assert all(row['params'][-1]=='0x1234' for row in calls[2:])
    assert {row['method'] for row in calls}=={'eth_chainId','eth_blockNumber','eth_getBalance','eth_call'}
    with pytest.raises(EvmRpcError):adapter._call('eth_sendRawTransaction',[])
    mock_rpc(monkeypatch,decimals=0)
    assert EvmRpcReadOnlyAdapter.for_chain('ethereum').read_wallet_snapshot(ADDRESS,CONTRACT)['balances'][1]['amount']=='1234567'


def test_owned_snapshot_reads_cache_identity_provenance_and_staleness(client,monkeypatch):
    seed_wallet();calls=mock_rpc(monkeypatch)
    empty=client.get(URL,params={'chain_id':'1','context_version':3}).json()
    assert empty['snapshot'] is None and not calls
    result=client.post(URL+'/refresh',json={'chain_id':'1','contract_address':CONTRACT.upper().replace('0X','0x'),'context_version':4})
    assert result.status_code==200,result.text
    value=result.json();snap=value['snapshot']
    assert value['contract_address']==CONTRACT and value['context_version']==4
    assert snap['source']=='evm_rpc_readonly' and snap['block_number']==0x1234
    assert snap['stale'] is False and value['execution_available'] is False and value['signing_available'] is False
    assert client.get(URL,params={'chain_id':'1'}).json()['snapshot'] is None
    assert client.get(URL,params={'chain_id':'8453'}).status_code==422
    with database() as db:
        row=db.get(DataSnapshot,snap['id']);row.as_of=utc_now()-timedelta(hours=1);db.commit()
        assert row.metadata_json['usable_for_trading'] is False
        assert len(list(db.scalars(select(AuditLog).where(AuditLog.action=='terminal.onchain.read'))))==1
    assert client.get(URL,params={'chain_id':'1','contract_address':CONTRACT}).json()['snapshot']['stale'] is True


@pytest.mark.parametrize('decimals,chain,fail',[(37,'0x1',False),(6,'0x2105',False),(6,'0x1',True)])
def test_failed_rpc_has_no_partial_snapshot_and_preserves_cached_observation(client,monkeypatch,decimals,chain,fail):
    seed_wallet();mock_rpc(monkeypatch)
    first=client.post(URL+'/refresh',json={'chain_id':'1'}).json()['snapshot']['id']
    mock_rpc(monkeypatch,decimals=decimals,chain=chain,fail=fail)
    result=client.post(URL+'/refresh',json={'chain_id':'1','contract_address':CONTRACT})
    assert result.status_code==502 and result.json()['detail']=={'code':'onchain_rpc_unavailable'}
    assert 'private endpoint' not in result.text
    with database() as db:
        assert [s.id for s in db.scalars(select(DataSnapshot))]==[first]
        assert len(list(db.scalars(select(AuditLog).where(AuditLog.action=='terminal.onchain.read_failed'))))==1
    assert client.get(URL,params={'chain_id':'1'}).json()['snapshot']['id']==first
    assert client.get(URL,params={'chain_id':'1','contract_address':CONTRACT}).json()['last_read_error']['code']=='onchain_rpc_unavailable'
    assert client.get(URL,params={'chain_id':'1'}).json()['last_read_error'] is None


def test_readonly_route_rejects_foreign_inactive_wallets_and_unregistered_networks(client,monkeypatch):
    seed_wallet(owner='another-user');calls=mock_rpc(monkeypatch)
    assert client.get(URL,params={'chain_id':'1'}).status_code==404
    assert client.post(URL+'/refresh',json={'chain_id':'1'}).status_code==404
    with database() as db:
        w=db.get(Wallet,'wallet-a');w.user_id='default-user';w.is_active=False;db.commit()
    assert client.get(URL,params={'chain_id':'1'}).status_code==404
    with database() as db:
        db.get(Wallet,'wallet-a').is_active=True;db.commit()
    assert client.get(URL,params={'chain_id':'999'}).status_code==422
    assert client.post(URL+'/refresh',json={'chain_id':'1','rpc_url':'https://private.example/','sign':True}).status_code==422
    assert not calls


def test_recorded_allowances_and_protocols_are_deduplicated_scoped_and_explicitly_partial(client):
    seed_wallet();now=utc_now()
    with database() as db:
        for i,when in enumerate([now-timedelta(hours=1),now]):
            db.add(TokenAllowance(wallet_id='wallet-a',user_id='default-user',chain='ethereum',token='X',symbol='X',token_address=CONTRACT,spender=ADDRESS,amount=i+1,source='mock_read_only',as_of=when))
            db.add(ProtocolPosition(wallet_id='wallet-a',user_id='default-user',chain='ethereum',protocol_name='Recorded protocol',position_type='exposure',asset_symbol='X',usd_value=99,risk_json={'token_address':CONTRACT},as_of=when))
        db.add(TokenAllowance(wallet_id='wallet-a',user_id='another-user',chain='ethereum',token='X',symbol='X',spender=ADDRESS))
        db.add(DataSnapshot(user_id='default-user',snapshot_type='terminal_onchain_readonly',data_json={'wallet_id':'wallet-a','chain_id':'1','contract_address':''}))
        db.commit()
    value=client.get(URL,params={'chain_id':'1','contract_address':CONTRACT}).json()
    assert len(value['recorded_allowances'])==len(value['recorded_protocols'])==1
    assert value['recorded_allowances'][0]['amount'].startswith('2.')
    assert value['recorded_allowances'][0]['source']=='mock_read_only'
    assert value['recorded_protocols'][0]['source']=='unverified_record'
    assert value['recorded_protocols'][0]['usd_value'] is None
    assert value['coverage']['protocols']=='recorded_only_not_full_index'
    assert client.get(URL,params={'chain_id':'1'}).json()['snapshot'] is None # unattested stored data is not RPC provenance
    assert client.get(URL,params={'chain_id':'1','contract_address':'0x'+'b'*40}).json()['recorded_protocols']==[]


def test_managed_identity_cannot_be_replaced_by_local_user_header(client,managed_actor,monkeypatch):
    seed_wallet(owner='tenant-trade-test');managed_actor('owner');mock_rpc(monkeypatch)
    assert client.get(URL,params={'chain_id':'1'}).status_code==401
    headers={'Authorization':'Bearer fixture','X-AI-Trading-User':'another-user'}
    result=client.post(URL+'/refresh',json={'chain_id':'1'},headers=headers)
    assert result.status_code==200,result.text
    assert result.json()['wallet']['id']=='wallet-a'


@pytest.mark.parametrize('method,result',[('eth_chainId','oops'),('eth_blockNumber','0x'),('eth_blockNumber',hex(2**54)),('eth_call','0x')])
def test_malformed_rpc_identity_height_or_contract_response_fails_closed(method,result):
    def transport(payload):
        if payload['method']==method:return {'result':result}
        return {'result':{'eth_chainId':'0x1','eth_blockNumber':'0x1234','eth_getBalance':'0x1','eth_call':'0x6'}[payload['method']]}
    adapter=EvmRpcReadOnlyAdapter.for_chain('ethereum',transport=transport)
    with pytest.raises(EvmRpcError):adapter.read_wallet_snapshot(ADDRESS,CONTRACT)


def test_failed_refresh_status_survives_cache_read_until_success_for_same_identity(client,monkeypatch):
    seed_wallet();mock_rpc(monkeypatch)
    first=client.post(URL+'/refresh',json={'chain_id':'1','contract_address':CONTRACT}).json()['snapshot']['id']
    mock_rpc(monkeypatch,fail=True)
    assert client.post(URL+'/refresh',json={'chain_id':'1','contract_address':CONTRACT}).status_code==502
    cached=client.get(URL,params={'chain_id':'1','contract_address':CONTRACT,'context_version':12}).json()
    assert cached['snapshot']['id']==first and cached['context_version']==12
    assert cached['last_read_error']['code']=='onchain_rpc_unavailable'
    mock_rpc(monkeypatch)
    recovered=client.post(URL+'/refresh',json={'chain_id':'1','contract_address':CONTRACT}).json()
    assert recovered['last_read_error'] is None and recovered['snapshot']['id']!=first
