"""Owned application-ledger observations, never live balances or verified prices."""
import hashlib
import json
import re
from datetime import timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select,func
from app.models import Account,Asset,Position,DataSnapshot,AuditLog
from app.models.core import utc_now
from app.services.account_identity import account_markets

class PortfolioContextError(ValueError):
    pass

class PortfolioPrepare(BaseModel):
    model_config={'extra':'forbid'}
    account_id: str = Field(min_length=1,max_length=128)
    market: Literal['stocks','cex']
    context_version: int = Field(strict=True,ge=0,le=2**53-1)

class PortfolioReference(PortfolioPrepare):
    schema_version: int = Field(strict=True,ge=1,le=1)
    snapshot_id: str = Field(min_length=1,max_length=128)

def instant(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True).encode()).hexdigest()

def number(value):
    try:
        result=Decimal(str(value))
        if not result.is_finite():raise ValueError()
        return format(result.normalize(),'f')
    except (ValueError,InvalidOperation):raise PortfolioContextError('ai_portfolio_invalid') from None

def ledger(db,user_id,ref):
    account=db.scalar(select(Account).where(Account.id==ref.account_id,Account.user_id==user_id))
    if account is None or ref.market not in account_markets(account):
        raise PortfolioContextError('ai_portfolio_identity_mismatch')
    foreign=db.scalar(select(Position.id).where(Position.account_id==account.id,Position.user_id!=user_id).limit(1))
    if foreign:raise PortfolioContextError('ai_portfolio_source_invalid')
    total=db.scalar(select(func.count()).select_from(Position).where(Position.account_id==account.id,Position.user_id==user_id))
    rows=list(db.execute(select(Position,Asset).outerjoin(Asset,Asset.id==Position.asset_id).where(Position.account_id==account.id,Position.user_id==user_id).order_by(Position.id).limit(20)))
    identity={'account_id':account.id,'account_type':account.account_type,'mode':account.mode,'base_currency':account.base_currency}
    entries=[{'id':'H1','kind':'account_ledger','source':'application_ledger','account':identity,'total_position_count':total,'included_count':len(rows),'truncated':total>len(rows)}]
    for index,(row,asset) in enumerate(rows,2):
        if asset is None:raise PortfolioContextError('ai_portfolio_source_invalid')
        entries.append({'id':'H'+str(index),'kind':'position_ledger','source':'application_ledger','record_id':row.id,
            'instrument':{'asset_id':asset.id,'symbol':asset.symbol,'asset_type':asset.asset_type,'market':asset.market,'venue':asset.venue,'currency':asset.currency,'chain_id':asset.chain_id,'contract_address':asset.contract_address},
            'quantity':number(row.quantity),'recorded_average_cost':number(row.average_cost),'recorded_market_price':number(row.market_price),'recorded_market_value':number(row.market_value),
            'record_updated_at':instant(row.updated_at).isoformat(),'quote_as_of':None,'valuation_verified':False})
    return {'account':identity,'entries':entries,'total_position_count':total,'included_count':len(rows),'truncated':total>len(rows)}

def prepare_portfolio_context(db,user_id,raw):
    try:ref=PortfolioPrepare.model_validate(raw)
    except (ValidationError,ValueError,TypeError):raise PortfolioContextError('ai_portfolio_invalid') from None
    data=ledger(db,user_id,ref);now=utc_now()
    source=DataSnapshot(user_id=user_id,snapshot_type='terminal_portfolio_ledger',data_json={},metadata_json={'execution_available':False,'usable_for_trading':False})
    db.add(source);db.flush()
    reference={'schema_version':1,'snapshot_id':source.id,**ref.model_dump()}
    material={'schema_version':1,'reference':reference,'account_id':ref.account_id,'market':ref.market,'context_version':ref.context_version,
        'source_snapshot_id':source.id,'source':'application_ledger','captured_at':now.isoformat(),
        'server_retrieved':True,'independently_verified':False,'valuation_freshness':'unknown','ledger_revision':digest(data),**data,
        'limitations':'Owned application-ledger records only, not a broker/exchange balance refresh or independently verified valuation. Record update time is not quote time. Zero/default values are not proof of zero exposure. At most 20 position records; no cross-account totals, FX conversion, live P&L or return calculation. Quantity precision is the stored ledger precision. No secrets or execution authority.'}
    material['content_hash']=digest(material)
    source.data_json=material
    db.add(AuditLog(user_id=user_id,actor_type='user',actor_id=user_id,action='terminal.portfolio.prepare',entity_type='DataSnapshot',entity_id=source.id,payload_json={'account_id':ref.account_id,'market':ref.market,'context_version':ref.context_version,'execution_available':False}))
    db.commit()
    return {'reference':reference,'provided_portfolio':material,'execution_available':False}

def load_portfolio_context(db,user_id,raw,*,now=None):
    try:ref=PortfolioReference.model_validate(raw)
    except (ValidationError,ValueError,TypeError):raise PortfolioContextError('ai_portfolio_invalid') from None
    source=db.scalar(select(DataSnapshot).where(DataSnapshot.id==ref.snapshot_id,DataSnapshot.user_id==user_id,DataSnapshot.snapshot_type=='terminal_portfolio_ledger'))
    audit=db.scalar(select(AuditLog).where(AuditLog.entity_id==ref.snapshot_id,AuditLog.entity_type=='DataSnapshot',AuditLog.actor_id==user_id,AuditLog.user_id==user_id,AuditLog.action=='terminal.portfolio.prepare'))
    if source is None or audit is None:raise PortfolioContextError('ai_portfolio_source_unavailable')
    data=source.data_json
    if not isinstance(data,dict):raise PortfolioContextError('ai_portfolio_source_invalid')
    if data.get('reference')!=ref.model_dump():raise PortfolioContextError('ai_portfolio_identity_mismatch')
    if data.get('content_hash')!=digest({k:v for k,v in data.items() if k!='content_hash'}):raise PortfolioContextError('ai_portfolio_source_invalid')
    now=now or utc_now()
    if not -30<=(now-instant(source.as_of)).total_seconds()<=600:raise PortfolioContextError('ai_portfolio_stale')
    if digest(ledger(db,user_id,ref))!=data.get('ledger_revision'):raise PortfolioContextError('ai_portfolio_changed')
    return data

def validate_portfolio_citations(report,context):
    ids=report.evidence.get('portfolio_citation_ids',[])
    allowed={entry['id'] for entry in context['entries']} if context else set()
    referenced=set(re.findall(r'\[(H\d+)\]','\n'.join([report.summary,report.bullish_case,report.bearish_case,*report.key_risks,report.limitations,report.suggested_action])))
    if not isinstance(ids,list) or len(ids)>21 or any(not isinstance(value,str) for value in ids) or set(ids)-allowed or set(ids)!=referenced:
        raise PortfolioContextError('ai_portfolio_citation_invalid')
    return list(dict.fromkeys(ids))
