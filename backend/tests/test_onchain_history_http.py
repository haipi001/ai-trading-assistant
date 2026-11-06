from contextlib import contextmanager
from test_trade_permissions import managed_actor
from app.main import app
from app.db.session import get_db
from app.models import DataSnapshot
BASE='/production/human-control/llm/chat/'
@contextmanager
def database():
    gen=app.dependency_overrides[get_db]()
    try:yield next(gen)
    finally:gen.close()
def test_history_routes_use_verified_actor_and_never_grant_execution(client,managed_actor):
    managed_actor('owner')
    with database() as db:
        def row(user):return DataSnapshot(user_id=user,snapshot_type='research_chat_onchain_context',data_json={'wallet_id':'wallet-a','chain_id':'1','contract_address':'','context_version':9},metadata_json={'reply_status':'failed','validated_reply':None})
        own=row('tenant-trade-test');foreign=row('foreign');db.add_all([own,foreign]);db.commit();own_id=own.id;foreign_id=foreign.id
    query={'wallet_id':'wallet-a','chain_id':'1'}
    assert client.get(BASE+'onchain-contexts',params=query).status_code==401
    headers={'Authorization':'Bearer fixture','X-AI-Trading-User':'foreign'}
    result=client.get(BASE+'onchain-contexts',params=query,headers=headers)
    assert result.status_code==200,result.text
    assert [r['snapshot_id'] for r in result.json()['items']]==[own_id]
    assert result.json()['execution_available'] is False
    assert client.get(BASE+'onchain-contexts',params={**query,'chain_id':'8453'},headers=headers).json()['items']==[]
    detail=client.get(BASE+'onchain-context/'+own_id,headers=headers)
    assert detail.status_code==200 and detail.json()['validated_reply'] is None
    assert detail.json()['execution_available'] is False
    assert client.get(BASE+'onchain-context/'+foreign_id,headers=headers).status_code==404

    for bad in [{"chain_id":"unknown"},{"wallet_id":""},{"contract_address":"not-a-contract"}]:
        assert client.get(BASE+"onchain-contexts",params={**query,**bad},headers=headers).status_code==422
