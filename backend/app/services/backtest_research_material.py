"""Owned immutable saved-backtest material; never approval or execution authority."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models import DataSnapshot, AuditLog
from app.models.core import utc_now
from app.services.backtests import BacktestRunsService, BacktestRunNotFoundError

KIND='terminal_backtest_research_material'
ACTION='terminal.backtest_material.prepare'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()

def prepare_backtest_material(db,user_id,run_id):
    service=BacktestRunsService(db)
    run=service.get_run(run_id)
    if run.user_id!=user_id:raise BacktestRunNotFoundError('backtest run not found')
    packet=service.research_packet(run_id)
    # JSON roundtrip detaches the artifact from mutable ORM JSON values.
    material=json.loads(json.dumps({'schema_version':1,'source':'saved_application_backtest','captured_at':utc_now().isoformat(),'backtest_run_id':run.id,'strategy_playbook_id':run.strategy_playbook_id,'run_status':run.status,'run_created_at':run.created_at.isoformat(),'date_from':run.date_from.isoformat(),'date_to':run.date_to.isoformat(),'initial_capital':str(run.initial_capital),'parameters':run.parameters_json,'results':run.results_json,'research_packet':packet,'independently_verified':False,'execution_available':False,'usable_for_trading':False,'limitations':'Saved application simulation only; not current editor execution, broker performance, verified market history or trading authority.'},allow_nan=False))
    material['content_hash']=digest(material)
    row=DataSnapshot(user_id=user_id,snapshot_type=KIND,data_json=material,metadata_json={'execution_available':False,'usable_for_trading':False})
    db.add(row);db.flush()
    db.add(AuditLog(user_id=user_id,actor_type='user',actor_id=user_id,action=ACTION,entity_type='DataSnapshot',entity_id=row.id,payload_json={'backtest_run_id':run.id,'content_hash':material['content_hash'],'execution_available':False}))
    db.commit()
    return {'snapshot_id':row.id,'material':material,'execution_available':False}

def read_backtest_material(db,user_id,run_id,snapshot_id):
    row=db.scalar(select(DataSnapshot).where(DataSnapshot.id==snapshot_id,DataSnapshot.user_id==user_id,DataSnapshot.snapshot_type==KIND))
    if row is None:raise HTTPException(404,'backtest material unavailable')
    if not isinstance(row.data_json,dict):raise HTTPException(409,'invalid backtest material')
    if row.data_json.get('backtest_run_id')!=run_id:raise HTTPException(404,'backtest material unavailable')
    material=row.data_json
    if material.get('execution_available') is not False or material.get('usable_for_trading') is not False or material.get('schema_version')!=1:raise HTTPException(409,'invalid backtest material')
    audit=db.scalar(select(AuditLog).where(AuditLog.user_id==user_id,AuditLog.actor_id==user_id,AuditLog.entity_id==row.id,AuditLog.action==ACTION))
    try:valid=digest({k:v for k,v in material.items() if k!='content_hash'})==material.get('content_hash')
    except (TypeError,ValueError):valid=False
    if not valid or audit is None or audit.payload_json.get('content_hash')!=material.get('content_hash') or audit.payload_json.get('backtest_run_id')!=run_id:raise HTTPException(409,'backtest material provenance changed')
    return {'snapshot_id':row.id,'material':material,'execution_available':False}


def list_backtest_material(db,user_id,run_id):
    run=BacktestRunsService(db).get_run(run_id)
    if run.user_id!=user_id:raise BacktestRunNotFoundError('backtest run not found')
    rows=list(db.scalars(select(DataSnapshot).where(DataSnapshot.user_id==user_id,DataSnapshot.snapshot_type==KIND,DataSnapshot.data_json['backtest_run_id'].as_string()==run_id).order_by(DataSnapshot.created_at.desc(),DataSnapshot.id.desc()).limit(21)))
    return {'backtest_run_id':run_id,'execution_available':False,'has_more':len(rows)>20,'items':[{'snapshot_id':row.id,'created_at':row.created_at.isoformat()} for row in rows[:20]]}
