"""Temporary HTTP fixture for native browser Paper tests; no real connectors/secrets."""
import argparse
from pathlib import Path
import sys
parser=argparse.ArgumentParser()
parser.add_argument('--database',required=True)
parser.add_argument('--research',action='store_true',help='Seed mock research through the real data trust and report evaluator APIs')
parser.add_argument('--port',type=int,default=8009)
args=parser.parse_args()
path=Path(args.database).resolve()
if not path.is_relative_to(Path('/tmp').resolve()) or path.exists():
    raise SystemExit('Choose a new fixture database under /tmp')
backend=Path(__file__).resolve().parents[2]/'backend'
sys.path[:0]=[str(backend),str(backend/'tests')]
import app.core.config as config
settings=config.Settings(_env_file=None,environment='local',database_url='sqlite+pysqlite:///'+str(path),
    managed_auth_required=False,beta_auth_required=False,runtime_scheduler_enabled=False,
    live_trading_enabled=False,live_execution_enabled=False,live_execution_adapter_mode='disabled',
    external_llm_calls_enabled=False,ai_provider_default='mock',automation_level='A0_READ_ONLY')
config.get_settings=lambda:settings
import app.core.local_secrets as local_secrets
local_secrets.load_user_secrets=lambda:None
from app.main import app as registered_app
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from app.api import domain, self_logic, mock, paper_execution, reports, decision_gates, risk, theses, workspaces, health, data_sources, data_catalog
from app.db.base import Base
from app.db.session import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from test_decision_gates import create_asset,create_account,create_constitution,create_risk_budget
import uvicorn
allowed=('/accounts','/assets','/investment-constitutions','/risk-budgets','/mock/update-quotes',
    '/quotes','/orders','/decision-gates','/risk','/paper-executions','/reports','/investment-theses',
    '/positions','/reviews','/trade-journal-entries','/post-trade-reviews','/api/v2/workspaces','/health','/openapi.json')
if args.research:allowed+=('/data-sources','/data-catalog')
app=FastAPI(title='Controlled Paper fixture: mock data only')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:8850','http://localhost:8850'],
    allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
selected=APIRouter()
for module in (domain,self_logic,mock,paper_execution,reports,decision_gates,risk,theses,workspaces,health,data_sources,data_catalog):
    selected.routes.extend(route for route in module.router.routes if any(
        getattr(route,'path','')==p or getattr(route,'path','').startswith(p+'/') for p in allowed))
assert selected.routes, 'No fixture routes registered'
app.include_router(selected)
engine=create_engine(settings.database_url,connect_args={'check_same_thread':False})
Base.metadata.create_all(engine)
sessions=sessionmaker(bind=engine,autoflush=False)
def database():
    with sessions() as db:
        yield db
app.dependency_overrides[get_db]=database
with TestClient(app) as client:
    asset=create_asset(client)
    create_asset(client,symbol='MSFT')
    first=create_account(client)
    second=client.post('/accounts',json={'name':'Second Paper Fixture','account_type':'brokerage','broker':'mock','base_currency':'USD','mode':'paper'})
    assert second.status_code==201,second.text
    cex=client.post('/accounts',json={'name':'CEX Paper Fixture','account_type':'exchange_account','broker':'mock','base_currency':'USD' if args.research else 'USDT','mode':'paper'})
    assert cex.status_code==201,cex.text
    owner=client.get('/api/v2/workspaces/session/context').json()['user_id']
    from app.models import Wallet
    with sessions() as db:
        db.add_all([Wallet(user_id=owner,address='0x'+'1'*40,chain='ethereum',label='Controlled ETH wallet'),
                    Wallet(user_id=owner,address='0x'+'2'*40,chain='base',label='Controlled Base wallet')])
        db.commit()
    constitution=create_constitution(client)
    for account in [first,second.json()]:create_risk_budget(client,constitution['id'],account['id'])
    assert client.post('/mock/update-quotes').status_code==200
    if args.research:
        # Real import -> catalog review/trust -> ReportGenerator -> evaluator.
        # All materials remain marked mock; no seeded report bypasses evaluation.
        from test_decision_gates import create_quality_snapshot,create_report
        snapshot=create_quality_snapshot(client,['AAPL'])
        report=create_report(client,snapshot)
        print('Controlled research report evaluated: '+report['id']+'; source snapshot '+snapshot,flush=True)
        crypto=[row for row in client.get('/assets').json() if (row['symbol'],row['asset_type'],row['market'],row['venue'],row['currency'])==('BTC','crypto','GLOBAL','CEX','USD')]
        assert len(crypto)==1,'Mock import must supply exactly one BTC/USD identity'
        from app.models import InvestmentConstitution
        with sessions() as db:
            saved=db.get(InvestmentConstitution,constitution['id'])
            saved.allowed_markets=['US','GLOBAL']
            db.commit()
        budget=client.post('/risk-budgets',json={'user_id':'user-1','constitution_id':constitution['id'],'account_id':cex.json()['id'],'asset_class':'crypto','max_allocation_pct':0.2,'max_loss_pct':0.08,'max_order_notional':1000,'max_leverage':1,'rebalance_threshold_pct':0.05})
        assert budget.status_code==201,budget.text
        connection=client.post('/data-sources/connections',json={'name':'Controlled CEX research source','provider':'mock_market_data','source_type':'market_data','mode':'read_only'})
        assert connection.status_code==201,connection.text
        imported=client.post('/data-sources/connections/'+connection.json()['id']+'/import-quotes',json={'symbols':['BTC'],'asset_type':'crypto','market':'GLOBAL','venue':'CEX','currency':'USD'})
        assert imported.status_code==201,imported.text
        entry=imported.json()['catalog_entry']['id']
        for stage in ['reviewed','trusted']:
            promoted=client.post('/data-catalog/entries/'+entry+'/promote')
            assert promoted.status_code==200 and promoted.json()['current_stage']==stage,promoted.text
        crypto_report=create_report(client,imported.json()['snapshot']['id'])
        assert client.post('/mock/update-quotes').status_code==200
        print('Controlled CEX BTC/USD research evaluated: '+crypto_report['id'],flush=True)

print('Controlled Paper fixture ready; live routes removed, mock quotes, isolated SQLite.',flush=True)
uvicorn.run(app,host='127.0.0.1',port=args.port)
