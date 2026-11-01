"""Isolated AI transport acceptance; browser public-market requests are independent."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.ai import OpenAIProvider, DeepSeekProvider
from app.api.production import router, production_user, get_db
from app.core import local_secrets
from app.core.auth import AuthenticatedUser, ROLE_PERMISSIONS
from app.db.base import Base
from app.services.human_control import HumanControlService, DEFAULT_CONFIGS
from app.api.news_feed import router as news_router
from app.services import news_feed

KEY='fixture-adapter-key'
CALLS=[]
ACTOR=AuthenticatedUser('ai-browser-fixture','owner',ROLE_PERMISSIONS['owner'],True,True)

def transport(self,payload,api_key):
    assert api_key==KEY
    name='openai' if isinstance(self,OpenAIProvider) else 'deepseek'
    facts=json.loads(payload['input'] if name=='openai' else payload['messages'][0]['content'])
    market=facts['input_facts'].get('market_context') or {}
    CALLS.append({'market_count':len(market.get('bars',[])),'market_symbol':market.get('symbol'),'market_timeframe':market.get('timeframe'),'provider':name,'model':payload['model'],'question':facts['input_facts']['user_question'],'key_matched_fixture':True,'news_count':len(facts['input_facts'].get('news_context',{}).get('articles',[]))})
    value={'report_id':'fixture-report','report_type':facts['report_type'],'agent_name':facts['agent_name'],'data_snapshot_id':facts['data_snapshot_id'],'input_facts':{},'summary':f'合成验收回复：已使用 {name} / {payload["model"]}，这不是真实模型回复。','bullish_case':'没有提供实时数据','bearish_case':'没有提供实时数据','key_risks':['合成数据，仅验证调用链'],'suggested_action':'核对研究证据','confidence':0.1,'evidence':{},'limitations':'仅收到问题与工作区标签；没有行情或账户数据。'}
    if facts['input_facts'].get('news_context'):
        value['summary']+=' 来源报道见 [N1]。'
        value['limitations']='已附带合成资讯；没有实时行情或账户数据。'
        value['evidence']={'news_citation_ids':['N1']}
    if market:
        value['summary']+=' 主图原始样本见 [M1]。'
        value['evidence']['market_citation_ids']=['M1']
        value['limitations']='附带的浏览器行情未经独立核实；合成模型回复仅验证调用链，没有账户数据。'
    if name=='openai':
        value['input_facts']=json.dumps(value['input_facts']);value['evidence']=json.dumps(value['evidence'])
    return {'output_text':json.dumps(value)} if name=='openai' else {'content':[{'type':'tool_use','name':'emit_research_report','input':value}]}

if __name__=='__main__':
    with TemporaryDirectory(prefix='ai-chat-browser-fixture-') as directory:
        local_secrets.store_path=lambda:Path(directory)/'credentials.env'
        OpenAIProvider._request=transport
        DeepSeekProvider._request=transport
        news_feed.fetch_news_json=lambda *args:{'status':'ok','articles':[{'title':'合成资讯：第一条报道','url':'https://example.com/fixture-news-one','description':'隔离验收用来源材料，不是真实新闻。','publishedAt':(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat(),'source':{'name':'合成来源 A'}},{'title':'合成资讯：第二条报道','url':'https://example.com/fixture-news-two','description':'用于验证来源列表和快照，不用于市场判断。','publishedAt':(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat(),'source':{'name':'合成来源 B'}}]}
        engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        app=FastAPI(title='Isolated AI browser fixture')
        app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3003','http://localhost:3003'],allow_methods=['GET','POST','PUT'],allow_headers=['Content-Type'],allow_credentials=True)
        paths={'/production/human-control/llm/credentials','/production/human-control/llm/chat/status','/production/human-control/llm/chat'}
        selected = APIRouter()
        selected.routes.extend(route for route in router.routes if route.path in paths)
        app.include_router(selected)
        app.include_router(news_router)
        with Session(engine) as db:
            news_feed.NewsFeedService(db,ACTOR.user_id).refresh()
        def fixture_db():
            with Session(engine) as session:yield session
        app.dependency_overrides[get_db]=fixture_db
        app.dependency_overrides[production_user]=lambda:ACTOR
        @app.get('/production/human-control/status')
        def configuration():
            with Session(engine) as db:
                service=HumanControlService(db)
                value={**DEFAULT_CONFIGS['research_evidence'],**service._get_config(ACTOR.user_id,'research_evidence')}
                return {'projects':[{'key':'research_evidence','configuration':service._redacted_config(value)}]}
        @app.get('/health/status')
        def health():return {'status':'ok','service':'isolated-ai-browser-fixture','fixture':True}
        @app.get('/fixture/status')
        def status():return {'fixture':True,'calls':CALLS}
        @app.get('/assets')
        def assets():return []  # No local candles; allow the normal public-market path.
        uvicorn.run(app,host='127.0.0.1',port=8002,access_log=False)
