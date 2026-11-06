"""Read existing run/schedule/order records; acknowledge notices, never trade."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, case, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.auth import AuthenticatedUser, require_permission
from app.db.session import get_db
from app.models import Account, Asset, AgentRun, ScheduledJob, OrderDraft, OrderIntent, AceActionState, AuditLog, RiskCheck, DecisionGate
from app.models.core import utc_now

router = APIRouter(prefix='/api/v2/agent', tags=['ace-status'])


class TaskRecord(BaseModel):
    record_id: str
    record_kind: Literal['agent_run', 'scheduled_job']
    name: str
    status: str
    source_id: str
    snapshot_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    error_present: bool = False
    execution_available: Literal[False] = False


class TasksResponse(BaseModel):
    source: Literal['persisted_agent_runs_and_schedules'] = 'persisted_agent_runs_and_schedules'
    generated_at: datetime
    records: list[TaskRecord]
    has_more: bool
    task_controls_available: Literal[False] = False


class OrderInstrument(BaseModel):
    asset_id: str
    symbol: str
    asset_type: str
    market: str
    venue: str
    currency: str


class OrderNotice(BaseModel):
    action_id: str
    source_kind: Literal['order_draft'] = 'order_draft'
    source_id: str
    source_revision: str
    kind: Literal['APPROVAL_REQUEST', 'INFO']
    title: str
    status: Literal['OPEN', 'ACKNOWLEDGED', 'DISMISSED']
    disposition_version: int
    created_at: datetime
    instrument: OrderInstrument
    account_id: str
    account_name: str
    mode: str
    side: str
    order_type: str
    notional: float | None
    quantity: float | None
    limit_price: float | None
    risk_status: str
    behavior_status: str
    approval_status: str
    execution_status: str
    evidence_ids: list[str]
    blocking_reasons: list[str]
    last_validation_status: str | None = None
    last_validation_at: datetime | None = None
    execution_available: Literal[False] = False
    approval_available: Literal[False] = False


class NoticesResponse(BaseModel):
    source: Literal['persisted_order_workflow_status'] = 'persisted_order_workflow_status'
    generated_at: datetime
    records: list[OrderNotice]
    has_more: bool


class NoticeUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    source_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_version: int = Field(ge=0)
    status: Literal['OPEN', 'ACKNOWLEDGED', 'DISMISSED']


def owned_orders(user_id: str):
    return (select(OrderDraft, OrderIntent, Account, Asset)
            .join(OrderIntent, OrderDraft.order_intent_id == OrderIntent.id)
            .join(Account, OrderIntent.account_id == Account.id).join(Asset, OrderIntent.asset_id == Asset.id)
            .where(OrderDraft.user_id == user_id, OrderIntent.user_id == user_id, Account.user_id == user_id))


def validation_for(db: Session, user_id: str, intent_id: str, draft: OrderDraft) -> dict:
    risk = db.scalar(select(RiskCheck).where(RiskCheck.user_id == user_id, RiskCheck.order_intent_id == intent_id)
                     .order_by(RiskCheck.created_at.desc(), RiskCheck.id.desc()).limit(1))
    audit = db.scalar(select(AuditLog).where(AuditLog.user_id == user_id, AuditLog.entity_id == intent_id,
        AuditLog.action.in_(['research_evidence.blocked', 'research_evidence.revalidated',
                             'decision_gate.revalidation_blocked', 'decision_gate.revalidated']))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1))
    references = []
    gate_id = (draft.decision_gate_results or {}).get('RESEARCH_GATE', {}).get('gate_id')
    gate = db.scalar(select(DecisionGate).where(DecisionGate.id == gate_id, DecisionGate.user_id == user_id,
                                               DecisionGate.order_intent_id == intent_id)) if gate_id else None
    if gate:
        references = [str(value) for key, value in (gate.evidence_json or {}).items()
                      if key in {'data_snapshot_id', 'research_report_id', 'quality_report_id'} and isinstance(value, str)]
    reasons = []
    if risk and not risk.hard_rule_passed:
        reasons.append(str(risk.reason or 'risk_check_blocked')[:400])
    if audit and audit.action.endswith('blocked'):
        payload = audit.payload_json or {}
        reasons += [str(reason)[:400] for reason in (payload.get('reasons') or [payload.get('reason')]) if reason]
    return {'evidence_ids': references, 'revision_ids': [risk.id if risk else None, audit.id if audit else None], 'reasons': reasons[:20],
            'status': 'blocked' if reasons else 'passed' if risk or audit else None,
            'at': audit.created_at if audit else risk.created_at if risk else None}


def notice(row, state: AceActionState | None, validation: dict) -> OrderNotice:
    draft, intent, account, asset = row
    revision = hashlib.sha256(json.dumps({
        'validation_records': validation['revision_ids'], 'evidence_ids': validation['evidence_ids'],
        'draft_id': draft.id, 'intent_id': intent.id, 'account_id': account.id,
        'asset_id': asset.id, 'instrument': [asset.symbol, asset.asset_type, asset.market, asset.venue, asset.currency],
        'mode': account.mode, 'live_enabled': account.live_trading_enabled,
        'side': intent.side, 'order_type': intent.order_type, 'notional': str(intent.notional),
        'quantity': str(intent.quantity), 'limit_price': str(intent.limit_price),
        'risk': draft.risk_status, 'validation_reasons': validation['reasons'], 'behavior': draft.behavior_status,
        'approval': draft.approval_status, 'execution': draft.execution_status,
        'gates': draft.decision_gate_results, 'policy': draft.approval_policy, 'evidence': intent.evidence_json,
    }, sort_keys=True, default=str).encode()).hexdigest()
    pending = draft.approval_status in {'pending', 'modified'} and draft.execution_status != 'paper_filled'
    kind = 'APPROVAL_REQUEST' if pending and not validation['reasons'] and draft.risk_status == draft.behavior_status == 'passed' else 'INFO'
    title = '最近复核存在阻止原因' if validation['reasons'] else '待人工审查的订单草稿' if kind == 'APPROVAL_REQUEST' else '订单工作流状态'
    evidence_ids = [str(value) for key, value in (intent.evidence_json or {}).items()
                    if key in {'report_id', 'research_report_id', 'manual_snapshot_id'} and isinstance(value, str)]
    evidence_ids = list(dict.fromkeys(evidence_ids + validation['evidence_ids']))
    return OrderNotice(action_id=f'order-draft:{draft.id}', source_id=draft.id, source_revision=revision,
        kind=kind, title=title, status=state.status if state and state.source_revision == revision else 'OPEN',
        disposition_version=state.version if state else 0, created_at=draft.created_at,
        instrument=OrderInstrument(asset_id=asset.id, symbol=asset.symbol, asset_type=asset.asset_type,
                                   market=asset.market, venue=asset.venue, currency=asset.currency),
        account_id=account.id, account_name=account.name, mode=account.mode,
        side=intent.side, order_type=intent.order_type, notional=float(intent.notional) if intent.notional is not None else None, quantity=float(intent.quantity) if intent.quantity is not None else None,
        limit_price=float(intent.limit_price) if intent.limit_price is not None else None,
        risk_status=draft.risk_status, behavior_status=draft.behavior_status,
        approval_status=draft.approval_status, execution_status=draft.execution_status, evidence_ids=evidence_ids, blocking_reasons=validation['reasons'],
        last_validation_status=validation['status'], last_validation_at=validation['at'])


@router.get('/tasks', response_model=TasksResponse)
def tasks(limit: int = Query(default=40, ge=1, le=100), actor: AuthenticatedUser = Depends(require_permission('read')),
          db: Session = Depends(get_db)):
    runs = list(db.scalars(select(AgentRun).where(AgentRun.user_id == actor.user_id)
                         .order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(limit + 1)).all())
    jobs = list(db.scalars(select(ScheduledJob).where(ScheduledJob.user_id == actor.user_id)
                         .order_by(ScheduledJob.created_at.desc(), ScheduledJob.id.desc()).limit(limit + 1)).all())
    records = [TaskRecord(record_id=f'run:{r.id}', record_kind='agent_run', source_id=r.id,
                         name=r.agent_name, status=r.status, snapshot_id=r.input_snapshot_id,
                         created_at=r.created_at, completed_at=r.completed_at, error_present=bool(r.error_message)) for r in runs]
    records += [TaskRecord(record_id=f'job:{j.id}', record_kind='scheduled_job', source_id=j.id, name=j.name,
                          status=j.status, created_at=j.created_at, last_run_at=j.last_run_at,
                          last_run_status=j.last_run_status) for j in jobs]
    # ISO strings avoid comparing timezone-aware and legacy naive UTC rows.
    records.sort(key=lambda r: ((r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)).timestamp(), r.record_id), reverse=True)
    return TasksResponse(generated_at=utc_now(), records=records[:limit], has_more=len(records) > limit)


@router.get('/actions', response_model=NoticesResponse)
def actions(limit: int = Query(default=40, ge=1, le=100), actor: AuthenticatedUser = Depends(require_permission('read')),
            db: Session = Depends(get_db)):
    rows = db.execute(owned_orders(actor.user_id).order_by(
        case((OrderDraft.approval_status.in_(['pending', 'modified']), 0), else_=1),
        OrderDraft.created_at.desc(), OrderDraft.id.desc()).limit(limit + 1)).all()
    ids = [f'order-draft:{row[0].id}' for row in rows[:limit]]
    states = {s.action_id: s for s in db.scalars(select(AceActionState).where(
        AceActionState.user_id == actor.user_id, AceActionState.action_id.in_(ids))).all()}
    return NoticesResponse(generated_at=utc_now(), records=[notice(row, states.get(f'order-draft:{row[0].id}'), validation_for(db, actor.user_id, row[1].id, row[0]))
                                                          for row in rows[:limit]], has_more=len(rows) > limit)


@router.patch('/actions/{action_id}/state', response_model=OrderNotice)
def set_action_state(action_id: str, payload: NoticeUpdate,
                     actor: AuthenticatedUser = Depends(require_permission('read')), db: Session = Depends(get_db)):
    if not action_id.startswith('order-draft:') or len(action_id) > 128:
        raise HTTPException(404, 'action not found')
    row = db.execute(owned_orders(actor.user_id).where(OrderDraft.id == action_id[len('order-draft:'):])).first()
    if row is None: raise HTTPException(404, 'action not found')
    state = db.get(AceActionState, (actor.user_id, action_id))
    current = notice(row, state, validation_for(db, actor.user_id, row[1].id, row[0]))
    if current.source_revision != payload.source_revision:
        raise HTTPException(409, 'order status changed; refresh the notice before acknowledging')
    if (state.version if state else 0) != payload.expected_version:
        raise HTTPException(409, 'notice disposition changed; refresh first')
    try:
        values = dict(source_revision=current.source_revision, status=payload.status, updated_at=utc_now(),
                      version=payload.expected_version + 1)
        if payload.expected_version == 0:
            db.add(AceActionState(user_id=actor.user_id, action_id=action_id, **values))
            db.flush()
        else:
            changed = db.execute(update(AceActionState).where(AceActionState.user_id == actor.user_id,
                AceActionState.action_id == action_id, AceActionState.version == payload.expected_version).values(**values))
            if changed.rowcount != 1: raise HTTPException(409, 'notice disposition changed; refresh first')
        db.add(AuditLog(actor_type='user', actor_id=actor.user_id, action='ace_action.disposition_changed',
                        entity_type='OrderDraft', entity_id=row[0].id,
                        payload_json={'status': payload.status, 'source_revision': current.source_revision,
                                      'order_approval_changed': False}))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'notice disposition changed; refresh first') from exc
    db.expire_all()
    row = db.execute(owned_orders(actor.user_id).where(OrderDraft.id == action_id[len('order-draft:'):])).first()
    if row is None: raise HTTPException(404, 'action not found')
    return notice(row, db.get(AceActionState, (actor.user_id, action_id)), validation_for(db, actor.user_id, row[1].id, row[0]))
