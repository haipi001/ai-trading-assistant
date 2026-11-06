"""Owned, evidence-bearing on-chain reads for the terminal. No signing route."""
from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.auth import AuthenticatedUser, require_permission
from app.db.session import get_db
from app.models import Wallet, DataSnapshot, AuditLog, TokenAllowance, ProtocolPosition
from app.models.core import utc_now
from app.adapters.evm_rpc_readonly import EvmRpcReadOnlyAdapter, EvmRpcError, resolve_chain

router = APIRouter(prefix='/api/v2/workspaces/onchain', tags=['terminal-onchain-readonly'])
STALE_SECONDS = 600


class OnchainRead(BaseModel):
    model_config = {'extra': 'forbid'}
    chain_id: str = Field(pattern=r'^[1-9][0-9]{0,19}$')
    contract_address: str = Field(default='', pattern=r'^(0x[0-9a-fA-F]{40})?$')
    context_version: int = Field(default=0, ge=0)


def owned_wallet(db, actor, wallet_id, chain_id):
    wallet = db.scalar(select(Wallet).where(Wallet.id == wallet_id, Wallet.user_id == actor.user_id,
                                          Wallet.is_active.is_(True)))
    if wallet is None:
        raise HTTPException(404, detail={'code': 'onchain_wallet_not_found'})
    try:
        actual, _ = resolve_chain(wallet.chain)
        requested, _ = resolve_chain(chain_id)
    except EvmRpcError as exc:
        raise HTTPException(422, detail={'code': 'onchain_chain_unsupported'}) from exc
    if actual != requested:
        raise HTTPException(422, detail={'code': 'onchain_chain_mismatch'})
    return wallet


def timestamp(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def recorded_rows(db, actor, wallet, model):
    rows = list(db.scalars(select(model).where(model.wallet_id == wallet.id, model.user_id == actor.user_id,
                                             model.chain == wallet.chain)
                           .order_by(model.as_of.desc(), model.id).limit(201)))
    return rows[:200], len(rows) > 200


def packet(db, actor, wallet, selection):
    contract = selection.contract_address.lower()
    snapshot = db.scalar(select(DataSnapshot).where(
        DataSnapshot.user_id == actor.user_id, DataSnapshot.snapshot_type == 'terminal_onchain_readonly',
        DataSnapshot.data_json['wallet_id'].as_string() == wallet.id,
        DataSnapshot.data_json['chain_id'].as_string() == selection.chain_id,
        DataSnapshot.data_json['contract_address'].as_string() == contract,
        DataSnapshot.id.in_(select(AuditLog.entity_id).where(
            AuditLog.action == 'terminal.onchain.read', AuditLog.actor_id == actor.user_id,
            AuditLog.entity_type == 'DataSnapshot')),
    ).order_by(DataSnapshot.as_of.desc(), DataSnapshot.id).limit(1))
    observed = None
    if snapshot:
        observed = {'id': snapshot.id, 'as_of': timestamp(snapshot.as_of).isoformat(),
                    'stale': not -30 <= (utc_now() - timestamp(snapshot.as_of)).total_seconds() <= STALE_SECONDS,
                    'source': 'evm_rpc_readonly', 'block_number': snapshot.data_json['block_number'],
                    'balances': snapshot.data_json['balances'], 'finality': 'observed_not_finalized'}
    failure = db.scalar(select(AuditLog).where(
        AuditLog.action == 'terminal.onchain.read_failed', AuditLog.actor_id == actor.user_id,
        AuditLog.entity_id == wallet.id, AuditLog.entity_type == 'Wallet',
        AuditLog.payload_json['chain_id'].as_string() == selection.chain_id,
        AuditLog.payload_json['contract_address'].as_string() == contract,
    ).order_by(AuditLog.created_at.desc(), AuditLog.id).limit(1))
    last_error = None
    if failure and (not snapshot or timestamp(failure.created_at) > timestamp(snapshot.as_of)):
        last_error = {'code': 'onchain_rpc_unavailable', 'as_of': timestamp(failure.created_at).isoformat()}
    allowances, allowance_truncated = recorded_rows(db, actor, wallet, TokenAllowance)
    protocols, protocol_truncated = recorded_rows(db, actor, wallet, ProtocolPosition)
    # Repeated refreshes append historical rows. Show the latest observation per
    # identity instead of summing duplicate balances or exposures.
    seen = set()
    approval_rows = []
    for row in allowances:
        if contract and (row.token_address or '').lower() != contract:
            continue
        key = ((row.token_address or '').lower(), row.spender.lower())
        if key in seen:
            continue
        seen.add(key)
        approval_rows.append({'id': row.id, 'contract_address': row.token_address, 'symbol': row.symbol,
                              'spender': row.spender, 'amount': str(row.amount), 'risk_level': row.risk_level,
                              'source': row.source, 'as_of': timestamp(row.as_of).isoformat()})
    seen = set()
    protocol_rows = []
    for row in protocols:
        risk = row.risk_json or {}
        address = str(risk.get('token_address') or '').lower()
        if contract and address != contract:
            continue
        key = (row.protocol_name, row.position_type, address, row.asset_symbol)
        if key in seen:
            continue
        seen.add(key)
        protocol_rows.append({'id': row.id, 'protocol': row.protocol_name, 'position_type': row.position_type,
                              'symbol': row.asset_symbol, 'contract_address': address or None,
                              'source': str(risk.get('source') or 'unverified_record'),
                              'as_of': timestamp(row.as_of).isoformat(),
                              'usd_value': str(row.usd_value) if risk.get('priced') is True else None})
    return {'wallet': {'id': wallet.id, 'label': wallet.label, 'address': wallet.address},
            'chain_id': selection.chain_id, 'contract_address': contract,
            'context_version': selection.context_version, 'snapshot': observed, 'last_read_error': last_error,
            'recorded_allowances': approval_rows, 'recorded_protocols': protocol_rows,
            'coverage': {'allowances': 'recorded_only_not_full_index', 'protocols': 'recorded_only_not_full_index',
                         'allowances_truncated': allowance_truncated, 'protocols_truncated': protocol_truncated},
            'limitations': ['USD价格未接入，余额不等于资产估值。',
                            '授权和协议仅展示已存记录；没有记录不代表没有风险或仓位。',
                            '区块高度为读取时观察值，未证明最终确认或排除链重组。'],
            'execution_available': False, 'signing_available': False}


@router.get('/{wallet_id}')
def read_onchain_workspace(wallet_id: str, chain_id: str = Query(pattern=r'^[1-9][0-9]{0,19}$'),
                           contract_address: str = Query(default='', pattern=r'^(0x[0-9a-fA-F]{40})?$'),
                           context_version: int = Query(default=0, ge=0),
                           actor: AuthenticatedUser = Depends(require_permission('read')),
                           db: Session = Depends(get_db)):
    selection = OnchainRead(chain_id=chain_id, contract_address=contract_address, context_version=context_version)
    wallet = owned_wallet(db, actor, wallet_id, chain_id)
    return packet(db, actor, wallet, selection)


@router.post('/{wallet_id}/refresh')
def refresh_onchain_workspace(wallet_id: str, selection: OnchainRead,
                              actor: AuthenticatedUser = Depends(require_permission('read')),
                              db: Session = Depends(get_db)):
    wallet = owned_wallet(db, actor, wallet_id, selection.chain_id)
    try:
        adapter = EvmRpcReadOnlyAdapter.for_chain(wallet.chain, timeout_seconds=6)
        observed = adapter.read_wallet_snapshot(wallet.address, selection.contract_address or None)
    except EvmRpcError as exc:
        db.add(AuditLog(actor_type='user', actor_id=actor.user_id, action='terminal.onchain.read_failed',
                        entity_type='Wallet', entity_id=wallet.id,
                        payload_json={'chain_id': selection.chain_id,
                                      'contract_address': selection.contract_address.lower(),
                                      'code': 'onchain_rpc_unavailable'}))
        db.commit()
        raise HTTPException(502, detail={'code': 'onchain_rpc_unavailable'}) from exc
    snapshot = DataSnapshot(user_id=actor.user_id, snapshot_type='terminal_onchain_readonly', as_of=utc_now(),
                            data_json={**observed, 'wallet_id': wallet.id, 'wallet_address': wallet.address.lower(),
                                       'contract_address': selection.contract_address.lower()},
                            metadata_json={'provider': 'evm_rpc_readonly', 'read_only': True,
                                           'execution_available': False, 'signing_available': False,
                                           'usable_for_trading': False})
    db.add(snapshot)
    db.flush()
    db.add(AuditLog(actor_type='user', actor_id=actor.user_id, action='terminal.onchain.read',
                    entity_type='DataSnapshot', entity_id=snapshot.id,
                    payload_json={'wallet_id': wallet.id, 'chain_id': selection.chain_id,
                                  'block_number': observed['block_number'], 'read_only': True}))
    db.commit()
    return packet(db, actor, wallet, selection)
