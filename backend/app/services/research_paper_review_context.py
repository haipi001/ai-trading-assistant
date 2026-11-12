"""Frozen, owned Paper review records; research material, never trade authority."""
import hashlib
import json
from datetime import timezone
from decimal import Decimal,InvalidOperation
from typing import Literal
from pydantic import BaseModel,Field,ValidationError
from sqlalchemy import select
from app.models import Account,Asset,AuditLog,DataSnapshot,DecisionGate,Execution,OrderDraft,OrderIntent,PostTradeReview,TradeJournalEntry
from app.models.core import utc_now
from app.services.account_identity import account_markets


class PaperReviewMaterialError(ValueError):
    pass


class PaperReviewPrepare(BaseModel):
    model_config={'extra':'forbid'}
    context_version: int = Field(strict=True,ge=0,le=2**53-1)


class PaperReviewReference(PaperReviewPrepare):
    schema_version: int = Field(strict=True,ge=1,le=1)
    snapshot_id: str = Field(min_length=1,max_length=128)
    execution_id: str = Field(min_length=1,max_length=128)
    account_id: str = Field(min_length=1,max_length=128)
    asset_id: str = Field(min_length=1,max_length=128)
    market: Literal['stocks','cex']


def instant(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True).encode()).hexdigest()


def number(value):
    if value is None:return None
    try:
        result=Decimal(str(value))
        if not result.is_finite():raise ValueError()
        return format(result.normalize(),'f')
    except (ValueError,InvalidOperation):raise PaperReviewMaterialError('ai_paper_review_source_invalid') from None


def text(value,limit):
    if not isinstance(value,str):raise PaperReviewMaterialError('ai_paper_review_source_invalid')
    return {'text':value[:limit],'truncated':len(value)>limit}


def records(db,user_id,execution_id):
    fill=db.scalar(select(Execution).where(Execution.id==execution_id,Execution.user_id==user_id,Execution.execution_mode=='paper'))
    if fill is None:raise PaperReviewMaterialError('ai_paper_review_source_unavailable')
    draft=db.get(OrderDraft,fill.order_draft_id)
    intent=db.get(OrderIntent,draft.order_intent_id) if draft else None
    account=db.get(Account,intent.account_id) if intent else None
    asset=db.get(Asset,intent.asset_id) if intent else None
    review=db.scalar(select(PostTradeReview).where(PostTradeReview.execution_id==fill.id,PostTradeReview.user_id==user_id))
    journal=db.get(TradeJournalEntry,review.trade_journal_entry_id) if review else None
    if not all([draft,intent,account,asset,review,journal]) or any(row.user_id!=user_id for row in [draft,intent,account,review,journal]) or review.order_draft_id!=draft.id or journal.account_id!=account.id or journal.asset_id!=asset.id:
        raise PaperReviewMaterialError('ai_paper_review_source_invalid')
    market='stocks' if asset.asset_type in {'stock','etf'} else 'cex' if asset.asset_type=='crypto' else None
    if market not in account_markets(account) or asset.chain_id or asset.contract_address:
        raise PaperReviewMaterialError('ai_paper_review_identity_mismatch')
    gates=[]
    saved=draft.decision_gate_results
    if not isinstance(saved,dict) or len(saved)>10:raise PaperReviewMaterialError('ai_paper_review_source_invalid')
    for gate_type,value in sorted(saved.items()):
        if not isinstance(value,dict):raise PaperReviewMaterialError('ai_paper_review_source_invalid')
        gate_id=value.get('gate_id')
        if not gate_id:continue
        gate=db.get(DecisionGate,gate_id)
        if gate is None or gate.user_id!=user_id or gate.order_intent_id!=intent.id or gate.gate_type!=gate_type:
            raise PaperReviewMaterialError('ai_paper_review_source_invalid')
        gates.append({'record_id':gate.id,'gate_type':gate.gate_type,'status':gate.status,'recorded_at':instant(gate.created_at).isoformat()})
    if len(gates)>10:raise PaperReviewMaterialError('ai_paper_review_source_invalid')
    manual=review.review_json.get('terminal_manual_review') if isinstance(review.review_json,dict) else None
    notes=manual.get('notes') if isinstance(manual,dict) and manual.get('source')=='human' else None
    entries=[
        {'id':'PR1','kind':'paper_execution','record_id':fill.id,'recorded_at':instant(fill.created_at).isoformat(),'execution_mode':'paper','status':fill.status,
         'filled_quantity':number(fill.filled_quantity),'average_fill_price':number(fill.average_fill_price),'fill_notional':number(fill.fill_notional),'fee_amount':number(fill.fee_amount),'realized_pnl':number(fill.realized_pnl)},
        {'id':'PR2','kind':'original_order_rationale','record_id':intent.id,'side':intent.side,'order_type':intent.order_type,'requested_quantity':number(intent.quantity),'limit_price':number(intent.limit_price),'rationale':text(intent.user_rationale or intent.rationale or '',4000),'thesis_id':intent.investment_thesis_id},
        {'id':'PR3','kind':'saved_review_record','record_id':review.id,'status':review.status,'record_updated_at':instant(review.updated_at).isoformat(),'human_notes':text(notes,8000) if notes is not None else None,'terminal_notes_source':'recorded_human' if notes is not None else 'unavailable','other_review_fields_included':False},
        {'id':'PR4','kind':'trade_journal_record','record_id':journal.id,'recorded_at':instant(journal.created_at).isoformat(),'notes':text(journal.notes,4000),'is_completion_evidence':False},
        {'id':'PR5','kind':'historical_decision_gates','gates':gates,'complete_five_gates':{row['gate_type'] for row in gates}=={'RESEARCH_GATE','THESIS_GATE','RISK_GATE','BEHAVIOR_GATE','EXECUTION_GATE'},'current_authorization_verified':False},
    ]
    return {'execution_id':fill.id,'account_id':account.id,'asset_id':asset.id,'market':market,
        'instrument':{'symbol':asset.symbol,'asset_type':asset.asset_type,'market':asset.market,'venue':asset.venue,'currency':asset.currency},'entries':entries}


def prepare_paper_review_context(db,user_id,execution_id,raw):
    try:request=PaperReviewPrepare.model_validate(raw)
    except (ValidationError,TypeError,ValueError):raise PaperReviewMaterialError('ai_paper_review_invalid') from None
    value=records(db,user_id,execution_id);now=utc_now()
    snapshot=DataSnapshot(user_id=user_id,snapshot_type='terminal_paper_review_context',data_json={},metadata_json={'execution_available':False,'usable_for_trading':False})
    db.add(snapshot);db.flush()
    reference={'schema_version':1,'snapshot_id':snapshot.id,'context_version':request.context_version,**{key:value[key] for key in ['execution_id','account_id','asset_id','market']}}
    material={'schema_version':1,'reference':reference,'captured_at':now.isoformat(),'source':'paper_ledger','server_retrieved':True,'independently_verified':False,
        'execution_available':False,'usable_for_trading':False,'record_revision':digest(value),**value,
        'limitations':'Paper records only, not live fills, current prices, approval authority or performance attribution. Original rationale and manual notes are user-authored claims, not verified facts. Historical gates are not current authorization. Only terminal manual notes are included; other review fields are unavailable. Text may be truncated with explicit flags.'}
    material['content_hash']=digest(material);snapshot.data_json=material
    db.add(AuditLog(user_id=user_id,actor_type='user',actor_id=user_id,action='terminal.paper_review.prepare',entity_type='DataSnapshot',entity_id=snapshot.id,payload_json={'execution_id':execution_id,'account_id':value['account_id'],'context_version':request.context_version,'execution_available':False}))
    db.commit()
    return {'reference':reference,'provided_paper_review':material,'execution_available':False}


def load_paper_review_context(db,user_id,raw,*,now=None):
    try:ref=PaperReviewReference.model_validate(raw)
    except (ValidationError,TypeError,ValueError):raise PaperReviewMaterialError('ai_paper_review_invalid') from None
    source=db.scalar(select(DataSnapshot).where(DataSnapshot.id==ref.snapshot_id,DataSnapshot.user_id==user_id,DataSnapshot.snapshot_type=='terminal_paper_review_context'))
    audit=db.scalar(select(AuditLog.id).where(AuditLog.entity_id==ref.snapshot_id,AuditLog.entity_type=='DataSnapshot',AuditLog.user_id==user_id,AuditLog.actor_id==user_id,AuditLog.action=='terminal.paper_review.prepare'))
    if source is None or audit is None:raise PaperReviewMaterialError('ai_paper_review_source_unavailable')
    material=source.data_json
    if not isinstance(material,dict) or material.get('content_hash')!=digest({key:value for key,value in material.items() if key!='content_hash'}):raise PaperReviewMaterialError('ai_paper_review_source_invalid')
    if material.get('reference')!=ref.model_dump():raise PaperReviewMaterialError('ai_paper_review_identity_mismatch')
    if not -30<=((now or utc_now())-instant(source.as_of)).total_seconds()<=600:raise PaperReviewMaterialError('ai_paper_review_stale')
    if digest(records(db,user_id,ref.execution_id))!=material.get('record_revision'):raise PaperReviewMaterialError('ai_paper_review_changed')
    return material


def validate_paper_review_citations(report,context):
    import re
    ids=report.evidence.get('paper_review_citation_ids',[])
    allowed={entry['id'] for entry in context['entries']} if context else set()
    referenced=set(re.findall(r'\[(PR\d+)\]','\n'.join([report.summary,report.bullish_case,report.bearish_case,*report.key_risks,report.limitations,report.suggested_action])))
    if not isinstance(ids,list) or context and not ids or len(ids)>5 or any(not isinstance(value,str) for value in ids) or set(ids)-allowed or set(ids)!=referenced:
        raise PaperReviewMaterialError('ai_paper_review_citation_invalid')
    return list(dict.fromkeys(ids))
