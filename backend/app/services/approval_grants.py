"""Bind a persisted human approval to exact order terms for a bounded lifetime."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import Approval, OrderIntent


class ApprovalGrantError(ValueError):
    pass


def order_fingerprint(db: Session, draft) -> str:
    intent = db.get(OrderIntent, draft.order_intent_id)
    if intent is None:
        raise ApprovalGrantError('approval order intent unavailable')
    keys = ['id', 'account_id', 'asset_id', 'side', 'order_type', 'source_type', 'source_id',
            'investment_thesis_id', 'strategy_playbook_id', 'automation_policy_id',
            'rationale', 'user_rationale', 'source_signal_id']
    terms = {key: getattr(intent, key) for key in keys}
    for key in ['quantity', 'notional', 'limit_price']:
        value = getattr(intent, key)
        terms[key] = str(Decimal(str(value)).normalize()) if value is not None else None
    terms['evidence_json'] = intent.evidence_json or {}
    terms['draft_id'] = draft.id
    terms['gate_results'] = draft.decision_gate_results
    terms['approval_required'] = True
    return hashlib.sha256(json.dumps(terms, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def issue_approval_grant(db: Session, draft, approval) -> None:
    draft.approval_policy = {**(draft.approval_policy or {}), 'required': True, 'grant': {
        'approval_id': approval.id, 'order_fingerprint': order_fingerprint(db, draft),
        'ttl_seconds': get_settings().order_approval_ttl_seconds,
    }}


def require_approval_grant(db: Session, draft) -> None:
    grant = (draft.approval_policy or {}).get('grant') or {}
    approval = db.get(Approval, grant.get('approval_id')) if grant.get('approval_id') else None
    if approval is None or approval.order_draft_id != draft.id or approval.status != 'approved':
        raise ApprovalGrantError('persisted approval grant missing; approve this draft again')
    if approval.decided_at is None:
        raise ApprovalGrantError('approval decision timestamp missing')
    decided_at = approval.decided_at if approval.decided_at.tzinfo else approval.decided_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - decided_at).total_seconds()
    try:
        ttl = min(int(grant['ttl_seconds']), get_settings().order_approval_ttl_seconds)
    except (KeyError, TypeError, ValueError):
        raise ApprovalGrantError('approval lifetime invalid')
    if ttl <= 0 or age < 0 or age >= ttl:
        raise ApprovalGrantError('approval expired; preview and approve this draft again')
    if grant.get('order_fingerprint') != order_fingerprint(db, draft):
        raise ApprovalGrantError('approved order terms changed; preview and approve this draft again')
