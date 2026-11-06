"""Server-resolved, immutable research material from an owned read-only observation."""
import hashlib
import json
import re
from datetime import timezone
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from app.models import Wallet, DataSnapshot, AuditLog, TokenAllowance, ProtocolPosition
from app.models.core import utc_now
from app.adapters.evm_rpc_readonly import resolve_chain, EvmRpcError


class OnchainContextError(ValueError):
    pass


class OnchainReference(BaseModel):
    model_config = {'extra': 'forbid'}
    schema_version: int = Field(strict=True, ge=1, le=1)
    snapshot_id: str = Field(min_length=1, max_length=128)
    wallet_id: str = Field(min_length=1, max_length=128)
    chain_id: str = Field(pattern=r'^[1-9][0-9]{0,19}$')
    contract_address: str = Field(pattern=r'^(0x[0-9a-fA-F]{40})?$')
    context_version: int = Field(strict=True, ge=0, le=2**53-1)
    allowance_ids: list[str] = Field(default_factory=list, max_length=20)
    protocol_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def ids(self):
        for values in (self.allowance_ids,self.protocol_ids):
            if len(set(values)) != len(values) or any(not 1<=len(value)<=128 for value in values):
                raise ValueError('invalid record references')
        self.contract_address=self.contract_address.lower()
        return self


def instant(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def load_onchain_context(db, user_id, raw, *, now=None):
    now=now or utc_now()
    try:
        ref=OnchainReference.model_validate(raw)
    except (ValidationError,ValueError,TypeError):
        raise OnchainContextError('ai_onchain_invalid') from None
    wallet=db.scalar(select(Wallet).where(Wallet.id==ref.wallet_id,Wallet.user_id==user_id,Wallet.is_active.is_(True)))
    if wallet is None:
        raise OnchainContextError('ai_onchain_identity_mismatch')
    try:
        if str(resolve_chain(wallet.chain)[0])!=ref.chain_id:
            raise EvmRpcError('wrong chain')
    except EvmRpcError:
        raise OnchainContextError('ai_onchain_identity_mismatch') from None
    source=db.scalar(select(DataSnapshot).where(DataSnapshot.id==ref.snapshot_id,DataSnapshot.user_id==user_id,DataSnapshot.snapshot_type=='terminal_onchain_readonly'))
    audit=db.scalar(select(AuditLog).where(AuditLog.entity_id==ref.snapshot_id,AuditLog.entity_type=='DataSnapshot',AuditLog.action=='terminal.onchain.read',AuditLog.actor_id==user_id))
    if source is None or audit is None:
        raise OnchainContextError('ai_onchain_source_unavailable')
    data=source.data_json;metadata=source.metadata_json
    if not isinstance(data,dict) or not isinstance(metadata,dict):
        raise OnchainContextError('ai_onchain_invalid')
    if (data.get('wallet_id'),data.get('chain_id'),data.get('contract_address'))!=(ref.wallet_id,ref.chain_id,ref.contract_address):
        raise OnchainContextError('ai_onchain_identity_mismatch')
    if data.get('wallet_address')!=wallet.address.lower():
        raise OnchainContextError('ai_onchain_source_unavailable')
    if metadata.get('provider')!='evm_rpc_readonly' or metadata.get('signing_available') is not False or metadata.get('execution_available') is not False or metadata.get('usable_for_trading') is not False:
        raise OnchainContextError('ai_onchain_source_unavailable')
    if not -30<=(now-instant(source.as_of)).total_seconds()<=600:
        raise OnchainContextError('ai_onchain_stale')
    failure=db.scalar(select(AuditLog).where(AuditLog.action=='terminal.onchain.read_failed',AuditLog.actor_id==user_id,AuditLog.entity_id==wallet.id,
        AuditLog.payload_json['chain_id'].as_string()==ref.chain_id,AuditLog.payload_json['contract_address'].as_string()==ref.contract_address,
        AuditLog.created_at>source.as_of).limit(1))
    if failure:
        raise OnchainContextError('ai_onchain_refresh_failed')
    balances=data.get('balances')
    if type(data.get('block_number')) is not int or not 0<=data['block_number']<=2**53-1 or not isinstance(balances,list) or len(balances)!=(2 if ref.contract_address else 1):
        raise OnchainContextError('ai_onchain_invalid')
    safe_balances=[]
    for i,row in enumerate(balances):
        if not isinstance(row,dict) or not isinstance(row.get('symbol'),str) or not 1<=len(row['symbol'])<=32 or not isinstance(row.get('amount'),str) or not re.fullmatch(r'[0-9]{1,80}(\.[0-9]{1,36})?',row['amount']) or type(row.get('decimals')) is not int or not 0<=row['decimals']<=36 or row.get('contract_address')!=(ref.contract_address if i else None):
            raise OnchainContextError('ai_onchain_invalid')
        safe_balances.append({key:row[key] for key in ('symbol','amount','decimals','contract_address')})
    entries=[{'id':'W1','record_id':source.id,'kind':'balances','source':'evm_rpc_readonly',
              'as_of':instant(source.as_of).isoformat(),'block_number':data['block_number'],'balances':safe_balances}]
    for ids,model,prefix in ((ref.allowance_ids,TokenAllowance,'A'),(ref.protocol_ids,ProtocolPosition,'P')):
        rows=list(db.scalars(select(model).where(model.id.in_(ids),model.user_id==user_id,model.wallet_id==wallet.id,model.chain==wallet.chain))) if ids else []
        mapping={row.id:row for row in rows}
        if len(mapping)!=len(ids):
            raise OnchainContextError('ai_onchain_identity_mismatch')
        for number,rid in enumerate(ids,1):
            row=mapping[rid];risk=row.risk_json or {} if prefix=='P' else {}
            address=(str(risk.get('token_address') or '') if prefix=='P' else row.token_address or '').lower()
            if ref.contract_address and address!=ref.contract_address:
                raise OnchainContextError('ai_onchain_identity_mismatch')
            entry={'id':prefix+str(number),'record_id':row.id,'contract_address':address or None,'as_of':instant(row.as_of).isoformat(),
                   'stale':not -30<=(now-instant(row.as_of)).total_seconds()<=600,'provenance':'stored_source_claim_not_independently_verified'}
            if prefix=='A':
                entry.update(kind='allowance',symbol=row.symbol,spender=row.spender,amount=str(row.amount),risk_level=row.risk_level,source=row.source)
            else:
                entry.update(kind='protocol',protocol=row.protocol_name,position_type=row.position_type,symbol=row.asset_symbol,
                             usd_value=str(row.usd_value) if risk.get('priced') is True else None,source=str(risk.get('source') or 'unverified_record'))
            entries.append(entry)
    context={'schema_version':1,'reference':ref.model_dump(),'wallet_id':ref.wallet_id,'wallet_public_address':wallet.address,
             'chain_id':ref.chain_id,'contract_address':ref.contract_address,'context_version':ref.context_version,
             'source_snapshot_id':source.id,'source_as_of':instant(source.as_of).isoformat(),'block_number':data['block_number'],
             'server_retrieved':True,'independently_verified':False,'entries':entries,'captured_at':now.isoformat(),
             'limitations':'Read-only node observation, not finalized or independently cryptographically verified. No USD valuation or complete approval/protocol index. Stored approvals/protocols may be stale or mock source claims, not current chain facts. No signing, trading, or account authority. Browser context_version is frozen as supplied, not proof of current browser focus.'}
    context['content_hash']=hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    return context


def validate_onchain_citations(report,context):
    ids=report.evidence.get('onchain_citation_ids',[])
    allowed={item['id'] for item in context['entries']} if context else set()
    referenced=set(re.findall(r'\[([WAP][0-9]+)\]','\n'.join([report.summary,report.bullish_case,report.bearish_case,*report.key_risks,report.limitations,report.suggested_action])))
    if not isinstance(ids,list) or len(ids)>41 or any(not isinstance(value,str) for value in ids) or set(ids)-allowed or set(ids)!=referenced:
        raise OnchainContextError('ai_onchain_citation_invalid')
    return list(dict.fromkeys(ids))
