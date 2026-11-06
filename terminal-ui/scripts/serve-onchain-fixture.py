"""Controlled Web3 UI fixture; optional real read-only fixed public-address probe."""
import argparse
from pathlib import Path
import sys
p=argparse.ArgumentParser()
p.add_argument('--database',required=True)
p.add_argument('--control-file',required=True)
p.add_argument('--port',type=int,default=8001)
p.add_argument('--research',action='store_true',help='Enable only research-chat routes with a controlled local provider; no external model')
p.add_argument('--public-probe',action='store_true',help='Allow real read-only RPC only for the fixed public reference address')
a=p.parse_args()
if a.research and a.public_probe:raise SystemExit('Keep controlled research and real public RPC probes separate')
path=Path(a.database).resolve();control=Path(a.control_file).resolve()
if not path.is_relative_to(Path('/tmp').resolve()) or path.exists() or not control.is_relative_to(Path('/tmp').resolve()) or control.exists():
    raise SystemExit('Use new fixture files under /tmp')
control.write_text('ok');control.chmod(0o600)
root=Path(__file__).resolve().parents[2]/'backend'
sys.path.insert(0,str(root))
import app.core.config as config
settings=config.Settings(_env_file=None,environment='local',database_url='sqlite+pysqlite:///'+str(path),managed_auth_required=False,beta_auth_required=False,runtime_scheduler_enabled=False,live_trading_enabled=False,live_execution_enabled=False,external_llm_calls_enabled=False,ai_provider_default='mock',automation_level='A0_READ_ONLY')
config.get_settings=lambda:settings
import app.core.local_secrets as secrets
secrets.load_user_secrets=lambda:None
from app.main import app as registered_app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import workspaces,terminal_onchain,health
from app.db.base import Base
from app.db.session import get_db
from app.models import Wallet,TokenAllowance,ProtocolPosition
from app.models.core import utc_now
from app.adapters.evm_rpc_readonly import EvmRpcReadOnlyAdapter,EvmRpcError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import timedelta
import uvicorn
app=FastAPI(title='Controlled Web3 fixture: no network, no execution routes')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:8850','http://localhost:8850'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
for module in (workspaces,terminal_onchain,health):app.include_router(module.router)
if a.research:
    from app.api import production
    from fastapi.routing import APIRoute
    allowed={
        '/production/human-control/llm/chat/status',
        '/production/human-control/llm/chat',
        '/production/human-control/llm/chat/onchain-contexts',
        '/production/human-control/llm/chat/onchain-context/{snapshot_id}',
    }
    # Copy only these real production handlers; never expose execution/configuration routes.
    app.router.routes.extend(route for route in production.router.routes if isinstance(route,APIRoute) and route.path in allowed)

engine=create_engine(settings.database_url,connect_args={'check_same_thread':False});Base.metadata.create_all(engine)
sessions=sessionmaker(bind=engine,autoflush=False)
def database():
    with sessions() as db:yield db
app.dependency_overrides[get_db]=database
with sessions() as db:
    db.add_all([Wallet(id='fixture-eth',user_id='default-user',address='0x'+'1'*40,chain='ethereum',label='Controlled ETH wallet'),Wallet(id='fixture-base',user_id='default-user',address='0x'+'2'*40,chain='base',label='Controlled Base wallet')]);db.flush()
    if a.public_probe:
        db.add(Wallet(id='public-reference',user_id='default-user',address='0x000000000000000000000000000000000000dEaD',chain='ethereum',label='Public reference address · real read-only'))
    db.add(TokenAllowance(wallet_id='fixture-eth',chain='ethereum',token='Fixture token',symbol='TEST',token_address='0x'+'a'*40,spender='0x'+'3'*40,amount=1000,risk_level='high',source='controlled_fixture',as_of=utc_now()-timedelta(hours=1)))
    db.add(ProtocolPosition(wallet_id='fixture-eth',chain='ethereum',protocol_name='Controlled protocol example',position_type='exposure',asset_symbol='TEST',risk_json={'token_address':'0x'+'a'*40,'source':'controlled_fixture'},as_of=utc_now()-timedelta(hours=1)))
    db.commit()
def request(self,payload):
    mode=control.read_text().strip()
    if mode=='fail':raise EvmRpcError('Controlled RPC failure')
    method=payload['method']
    if method=='eth_chainId':result=hex(8453 if mode=='wrong-chain' else self.expected_chain_id)
    elif method=='eth_blockNumber':result=hex(21000000)
    elif method=='eth_getBalance':result=hex(10**18+1 if self.expected_chain_id==1 else 2*10**18)
    elif method=='eth_call':result=hex(6 if payload['params'][0]['data']=='0x313ce567' else 1234567)
    else:raise EvmRpcError('Unexpected fixture RPC method')
    return {'result':result}
if a.research:
    import json
    import time
    from app.core.auth import AuthenticatedUser,ROLE_PERMISSIONS
    from app.services.human_control import HumanControlService
    # A fake local credential only, isolated from the user's credential store.
    secrets.store_path=lambda:path.with_suffix('.fixture-secrets.env')
    actor=AuthenticatedUser(user_id='default-user',role='owner',permissions=ROLE_PERMISSIONS['owner'],auth_required=False,token_configured=False)
    with sessions() as db:
        HumanControlService(db).set_llm_credentials(actor=actor,payload={
            'provider':'deepseek','model':'controlled-ui-fixture-no-network',
            'api_key':'fixture-local-not-a-real-key','monthly_budget_usd':10,
            'per_request_budget_usd':1,'approved_for_research':True})
    class ControlledProvider:
        def generate_report(self,**kwargs):
            mode=control.read_text().strip()
            if mode=='ai-delay':time.sleep(8)
            if mode=='ai-fail':raise RuntimeError('Controlled model failure')
            context=kwargs['input_facts'].get('onchain_context')
            ids=[entry['id'] for entry in context['entries']] if context else []
            citations=' '.join('['+value+']' for value in ids)
            if mode=='ai-invalid':citations='[W999]';ids=['W999']
            return json.dumps({
                'report_id':'controlled-ui-fixture','report_type':kwargs['report_type'],
                'agent_name':kwargs['agent_name'],'data_snapshot_id':kwargs['data_snapshot_id'],
                'summary':'受控验收响应（未调用外部模型）。仅解释所选只读证据。 '+citations,
                'bullish_case':'受控材料不足以形成看多结论',
                'bearish_case':'授权与协议记录可能陈旧，不能推出当前完整风险',
                'key_risks':['受控数据，非真实模型分析','节点观测不代表最终性或独立验证'],
                'suggested_action':'检查来源和未知项，不执行交易','confidence':0.1,
                'limitations':'Controlled local provider; no network, no trading report promotion',
                'input_facts':{},'evidence':{'onchain_citation_ids':ids}})
    HumanControlService._provider_from_llm_config=lambda self,config:ControlledProvider()
original_request=EvmRpcReadOnlyAdapter._request
original_read=EvmRpcReadOnlyAdapter.read_wallet_snapshot
def read(self,address,contract_address=None):
    if a.public_probe and address.lower()=='0x000000000000000000000000000000000000dead':
        self.transport=lambda payload:original_request(self,payload)
    return original_read(self,address,contract_address)
EvmRpcReadOnlyAdapter._request=request
EvmRpcReadOnlyAdapter.read_wallet_snapshot=read
print('Fixture: controlled RPC; research='+str(a.research)+' (local provider only). Live routes absent.',flush=True)
uvicorn.run(app,host='127.0.0.1',port=a.port,access_log=False)
