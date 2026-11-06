"""Controlled browser fixture: workspace preferences only, never trading or real data."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import Settings
import app.core.auth as auth
import app.api.workspaces as workspaces
from app.db.base import Base
from app.db.session import get_db
import uvicorn

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',required=True)
    parser.add_argument('--port',type=int,default=8009)
    args=parser.parse_args()
    path=Path(args.database).resolve()
    if not path.is_relative_to(Path('/tmp').resolve()):
        raise SystemExit('Fixture database must be under /tmp')
    settings=Settings(_env_file=None,environment='local',managed_auth_required=False,beta_auth_required=False,
                      live_trading_enabled=False,live_execution_enabled=False,external_llm_calls_enabled=False,
                      runtime_scheduler_enabled=False)
    auth.get_settings=lambda:settings
    workspaces.get_settings=lambda:settings
    engine=create_engine('sqlite+pysqlite:///'+str(path),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    def database():
        with sessions() as session:
            yield session
    app=FastAPI(title='Controlled workspace-only fixture')
    app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:8850','http://localhost:8850'],
                       allow_credentials=True,allow_methods=['GET','PUT','OPTIONS'],allow_headers=['*'])
    app.dependency_overrides[get_db]=database
    app.include_router(workspaces.router)
    @app.get('/health/status')
    def status():
        return {'status':'controlled_fixture','contains_customer_data':False,'execution_available':False}
    uvicorn.run(app,host='127.0.0.1',port=args.port)
