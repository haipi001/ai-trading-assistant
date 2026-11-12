"""Private user-authored parameter snapshots, never market evidence or authority."""
import hashlib
import json
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,model_validator
from sqlalchemy import select
from fastapi import HTTPException
from app.models import Account,DataSnapshot,AuditLog
from app.services.account_identity import account_markets
from app.models.core import utc_now

class GridConfiguration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['arithmetic_grid']
    lower: str=Field(pattern=r'^\d{1,16}(\.\d{1,12})?$',max_length=30)
    upper: str=Field(pattern=r'^\d{1,16}(\.\d{1,12})?$',max_length=30)
    intervals: int=Field(strict=True,ge=2,le=500)

    @model_validator(mode='after')
    def interval_order(self):
        from decimal import Decimal
        if Decimal(self.lower)<=0 or Decimal(self.upper)<=Decimal(self.lower):raise ValueError('invalid grid interval')
        return self

class SpotDcaConfiguration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['spot_dca']
    frequency: Literal['每天','每周','每月']
    first_run_local: str | None=Field(default=None,max_length=19,pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$')
    take_profit_percent: str | None=Field(default=None,max_length=30,pattern=r'^\d{1,16}(\.\d{1,12})?$')

    @model_validator(mode='after')
    def validate_values(self):
        from decimal import Decimal
        from datetime import datetime
        if self.take_profit_percent is not None and Decimal(self.take_profit_percent)<=0:raise ValueError('invalid take profit')
        if self.first_run_local is not None:datetime.fromisoformat(self.first_run_local)
        return self

class StrategyParameters(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str=Field(min_length=1,max_length=200)
    coin: str=Field(min_length=1,max_length=128)
    type: str=Field(min_length=1,max_length=128)
    amount: str=Field(pattern=r'^\d{1,16}(\.\d{1,12})?$',max_length=30)
    platform: str=Field(max_length=200)
    risk: str=Field(max_length=64)
    trigger: str=Field(default='',max_length=200)
    invalidation: str=Field(default='',max_length=200)
    constraints: str=Field(default='',max_length=400)
    grid: GridConfiguration | None=None
    dca: SpotDcaConfiguration | None=None
    budget_currency: str | None=Field(default=None,pattern=r'^[A-Z0-9]{2,12}$')
    quote_currency: str | None=Field(default=None,pattern=r'^[A-Z0-9]{2,12}$')

    @model_validator(mode='after')
    def one_strategy_configuration(self):
        if self.grid is not None and self.dca is not None:raise ValueError('mixed strategy configurations')
        return self

class StrategyMaterialPrepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    account_id: str=Field(min_length=1,max_length=128)
    market: Literal['stocks','cex']
    context_version: int=Field(strict=True,ge=0,le=2**53-1)
    parameters: StrategyParameters


def owned_account(db,user_id,account_id,market):
    account=db.scalar(select(Account).where(Account.id==account_id,Account.user_id==user_id))
    if account is None:raise HTTPException(404,'strategy material account unavailable')
    if market not in account_markets(account):raise HTTPException(422,'strategy material account market mismatch')
    return account


def prepare_strategy_material(db,user_id,request):
    from decimal import Decimal
    account=owned_account(db,user_id,request.account_id,request.market)
    if request.market=='stocks' and request.parameters.budget_currency is not None and request.parameters.budget_currency!=account.base_currency:
        raise HTTPException(422,'strategy budget currency differs from account currency')
    if Decimal(request.parameters.amount)<=0:raise HTTPException(422,'strategy amount must be positive')
    if request.parameters.grid and Decimal(request.parameters.amount)<20:raise HTTPException(422,'grid budget below minimum')
    material={'schema_version':1,'source':'user_local_strategy_parameters','account_id':request.account_id,'market':request.market,'context_version':request.context_version,'parameters':request.parameters.model_dump(exclude_none=True),'captured_at':utc_now().isoformat(),'independently_verified':False,'execution_available':False,'usable_for_trading':False,'limitations':'User-authored parameters only. No verified prices, backtest, profitability, strategy runtime, approval or execution authority.'}
    material['content_hash']=hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest()
    row=DataSnapshot(user_id=user_id,snapshot_type='terminal_strategy_parameters',data_json=material,metadata_json={'execution_available':False,'usable_for_trading':False})
    db.add(row);db.flush()
    db.add(AuditLog(user_id=user_id,actor_type='user',actor_id=user_id,action='terminal.strategy_material.prepare',entity_type='DataSnapshot',entity_id=row.id,payload_json={'account_id':request.account_id,'market':request.market,'context_version':request.context_version,'execution_available':False}))
    db.commit()
    return {'snapshot_id':row.id,'material':material,'execution_available':False}


def read_strategy_material(db,user_id,snapshot_id):
    row=db.scalar(select(DataSnapshot).where(DataSnapshot.id==snapshot_id,DataSnapshot.user_id==user_id,DataSnapshot.snapshot_type=='terminal_strategy_parameters'))
    if row is None:raise HTTPException(404,'strategy material unavailable')
    material=row.data_json
    if not isinstance(material,dict) or material.get('schema_version')!=1 or material.get('execution_available') is not False or material.get('usable_for_trading') is not False:
        raise HTTPException(409,'strategy material invalid')
    audit=db.scalar(select(AuditLog.id).where(AuditLog.user_id==user_id,AuditLog.actor_id==user_id,AuditLog.entity_id==row.id,AuditLog.action=='terminal.strategy_material.prepare'))
    if audit is None:raise HTTPException(409,'strategy material provenance unavailable')
    digest=hashlib.sha256(json.dumps({k:v for k,v in material.items() if k!='content_hash'},sort_keys=True).encode()).hexdigest()
    if digest!=material.get('content_hash'):raise HTTPException(409,'strategy material changed')
    account=owned_account(db,user_id,material['account_id'],material['market'])
    if material['market']=='stocks' and material['parameters'].get('budget_currency') is not None and material['parameters']['budget_currency']!=account.base_currency:
        raise HTTPException(409,'strategy account currency changed')
    return {'snapshot_id':row.id,'material':material,'execution_available':False}

class StrategyMaterialReference(BaseModel):
    model_config=ConfigDict(extra='forbid')
    snapshot_id: str=Field(min_length=1,max_length=128)
    account_id: str=Field(min_length=1,max_length=128)
    market: Literal['stocks','cex']
    context_version: int=Field(strict=True,ge=0,le=2**53-1)
    content_hash: str=Field(pattern=r'^[a-f0-9]{64}$')


def load_strategy_context(db,user_id,raw):
    from pydantic import ValidationError
    from datetime import timezone
    try:ref=StrategyMaterialReference.model_validate(raw)
    except (ValidationError,ValueError,TypeError):raise ValueError('ai_strategy_invalid') from None
    try:packet=read_strategy_material(db,user_id,ref.snapshot_id)
    except HTTPException:raise ValueError('ai_strategy_unavailable') from None
    material=packet['material']
    if any(material.get(key)!=getattr(ref,key) for key in ['account_id','market','context_version','content_hash']):raise ValueError('ai_strategy_identity_mismatch')
    from datetime import datetime
    try:
        instant=datetime.fromisoformat(material['captured_at'])
        if instant.tzinfo is None:instant=instant.replace(tzinfo=timezone.utc)
        if not -30<=(utc_now()-instant).total_seconds()<=600:raise ValueError()
    except (ValueError,TypeError,KeyError):raise ValueError('ai_strategy_stale') from None
    return material


def validate_strategy_citations(report,context):
    import re
    ids=report.evidence.get('strategy_citation_ids',[])
    text='\n'.join([report.summary,report.bullish_case,report.bearish_case,*report.key_risks,report.limitations,report.suggested_action])
    used=set(re.findall(r'\[(SP\d+)\]',text))
    if not isinstance(ids,list) or any(not isinstance(item,str) for item in ids) or len(ids)>1 or set(ids)!=used or (set(ids)!={'SP1'} if context else bool(ids)):
        raise ValueError('ai_strategy_citation_invalid')
    return ids


def strategy_research_history(db,user_id,account_id,market):
    from datetime import timezone
    owned_account(db,user_id,account_id,market)
    rows=list(db.scalars(select(DataSnapshot).where(DataSnapshot.user_id==user_id,DataSnapshot.snapshot_type=='research_chat_strategy_context',DataSnapshot.data_json['account_id'].as_string()==account_id,DataSnapshot.data_json['market'].as_string()==market).order_by(DataSnapshot.created_at.desc(),DataSnapshot.id.desc()).limit(21)))
    return {'items':[{'snapshot_id':row.id,'request_id':row.metadata_json.get('request_id'),'account_id':account_id,'market':market,'context_version':row.data_json['context_version'],'reply_status':row.metadata_json.get('reply_status'),'created_at':row.created_at.replace(tzinfo=timezone.utc).isoformat() if row.created_at.tzinfo is None else row.created_at.isoformat()} for row in rows[:20]],'has_more':len(rows)>20,'execution_available':False}


def strategy_research_artifact(db,user_id,snapshot_id):
    row=db.scalar(select(DataSnapshot).where(DataSnapshot.user_id==user_id,DataSnapshot.id==snapshot_id,DataSnapshot.snapshot_type=='research_chat_strategy_context'))
    if row is None:raise HTTPException(404,'strategy research unavailable')
    material=row.data_json
    if not isinstance(material,dict) or material.get('content_hash')!=hashlib.sha256(json.dumps({k:v for k,v in material.items() if k!='content_hash'},sort_keys=True).encode()).hexdigest():
        raise HTTPException(409,'strategy research material changed')
    owned_account(db,user_id,material['account_id'],material['market'])
    news_id=row.metadata_json.get('news_context_snapshot_id')
    news=db.scalar(select(DataSnapshot).where(DataSnapshot.user_id==user_id,DataSnapshot.id==news_id,DataSnapshot.snapshot_type=='research_chat_news_context')) if news_id else None
    if news_id and news is None:raise HTTPException(409,'strategy research source incomplete')
    return {'snapshot_id':row.id,'provided_strategy':material,'provided_news':news.data_json if news else None,'news_context_snapshot_id':news_id,'execution_available':False,**{key:row.metadata_json.get(key) for key in ['request_id','question','workspace_labels','provider','provider_mode','model','reply_status','validated_reply']}}

class StrategyParameterChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    field: Literal['amount','risk','trigger','invalidation','constraints','grid.lower','grid.upper','grid.intervals','dca.frequency','dca.first_run_local','dca.take_profit_percent']
    before: str=Field(max_length=400)
    after: str=Field(max_length=400)
    rationale: str=Field(min_length=1,max_length=600)
    citation_ids: list[Literal['SP1']]=Field(min_length=1,max_length=1)


def validate_strategy_changes(report,context):
    from decimal import Decimal,InvalidOperation
    from pydantic import ValidationError
    from copy import deepcopy
    import re
    raw=report.evidence.get('strategy_parameter_changes',[])
    if not isinstance(raw,list) or len(raw)>8 or (raw and not context):raise ValueError('ai_strategy_changes_invalid')
    if not raw:return []
    proposed=deepcopy(context['parameters']);result=[];seen=set()
    limits={'amount':30,'risk':64,'trigger':200,'invalidation':200,'constraints':400,'grid.lower':30,'grid.upper':30,'grid.intervals':3,'dca.frequency':8,'dca.first_run_local':19,'dca.take_profit_percent':30}
    for value in raw:
        try:change=StrategyParameterChange.model_validate(value)
        except (ValidationError,ValueError,TypeError):raise ValueError('ai_strategy_changes_invalid') from None
        grid_key=change.field.split('.')[1] if change.field.startswith('grid.') else None
        dca_key=change.field.split('.')[1] if change.field.startswith('dca.') else None
        optional_dca=dca_key in {'first_run_local','take_profit_percent'}
        if dca_key and not context['parameters'].get('dca'):raise ValueError('ai_strategy_changes_invalid')
        original=context['parameters'].get('dca',{}).get(dca_key,'') if dca_key else context['parameters'].get('grid',{}).get(grid_key) if grid_key else context['parameters'].get(change.field)
        if original is None or change.field in seen or change.before!=str(original) or change.after==change.before or (not change.after.strip() and not (optional_dca and change.after=='')) or len(change.after)>limits[change.field] or set(re.findall(r'\[(SP\d+)\]',change.rationale))-{'SP1'}:raise ValueError('ai_strategy_changes_invalid')
        if change.field=='amount':
            try:
                if not re.fullmatch(r'\d{1,16}(\.\d{1,12})?',change.after) or Decimal(change.after)<=0:raise ValueError()
            except (ValueError,InvalidOperation):raise ValueError('ai_strategy_changes_invalid') from None
        if dca_key:
            if optional_dca and change.after=='':proposed['dca'].pop(dca_key,None)
            else:proposed['dca'][dca_key]=change.after
        elif grid_key:
            if grid_key=='intervals':
                if not re.fullmatch(r'[1-9][0-9]{0,2}',change.after):raise ValueError('ai_strategy_changes_invalid')
                proposed['grid'][grid_key]=int(change.after)
            else:proposed['grid'][grid_key]=change.after
        else:proposed[change.field]=change.after
        seen.add(change.field);result.append(change.model_dump())
    if proposed.get('grid'):
        try:
            GridConfiguration.model_validate(proposed['grid'])
            if Decimal(proposed['amount'])<20:raise ValueError()
        except (ValidationError,ValueError,InvalidOperation):raise ValueError('ai_strategy_changes_invalid') from None
    if proposed.get('dca'):
        try:SpotDcaConfiguration.model_validate(proposed['dca'])
        except (ValidationError,ValueError):raise ValueError('ai_strategy_changes_invalid') from None
    return result
