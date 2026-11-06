"""Server-only quote evidence for explicit human Paper limit orders, without AI."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import (
    Account, Asset, AuditLog, DataCatalogEntry, DataQualityReport, DataSnapshot,
    ManualTradeEvidence, OrderIntent, Quote,
)


class ManualEvidenceError(ValueError):
    pass


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def terms(intent: OrderIntent, asset: Asset, quote: Quote) -> dict:
    numeric = lambda value: str(Decimal(str(value)).normalize()) if value is not None else None
    return {
        'order_intent_id': intent.id, 'account_id': intent.account_id, 'asset_id': intent.asset_id,
        'source_type': intent.source_type, 'side': intent.side, 'order_type': intent.order_type,
        'quantity': numeric(intent.quantity), 'limit_price': numeric(intent.limit_price),
        'notional': numeric(intent.notional), 'rationale': intent.user_rationale, 'order_rationale': intent.rationale,
        'investment_thesis_id': intent.investment_thesis_id, 'strategy_playbook_id': intent.strategy_playbook_id,
        'automation_policy_id': intent.automation_policy_id, 'source_id': intent.source_id,
        'quotes': [{
            'quote_id': quote.id, 'asset_id': asset.id, 'symbol': asset.symbol, 'asset_type': asset.asset_type,
            'market': asset.market, 'venue': asset.venue, 'currency': asset.currency,
            'chain_id': asset.chain_id, 'contract_address': asset.contract_address,
            'price': numeric(quote.price), 'source': quote.source, 'as_of': utc(quote.as_of).isoformat(),
        }],
    }


def digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def eligible(db: Session, intent: OrderIntent) -> Asset:
    account, asset = db.get(Account, intent.account_id), db.get(Asset, intent.asset_id)
    if account is None or asset is None:
        raise ManualEvidenceError('manual Paper account or asset unavailable')
    if account.mode != 'paper' or account.live_trading_enabled:
        raise ManualEvidenceError('manual quote evidence supports Paper accounts only')
    if intent.source_type != 'manual' or intent.source_signal_id or intent.order_type != 'limit':
        raise ManualEvidenceError('manual quote evidence requires a human limit order')
    if not (intent.user_rationale or '').strip():
        raise ManualEvidenceError('explicit user rationale is required')
    if intent.side not in {'buy', 'sell'}:
        raise ManualEvidenceError('manual order side is invalid')
    for value in (intent.quantity, intent.limit_price):
        if value is None or not Decimal(str(value)).is_finite() or Decimal(str(value)) <= 0:
            raise ManualEvidenceError('manual quantity and limit price must be positive')
    if (intent.evidence_json or {}).get('report_id') or (intent.evidence_json or {}).get('research_report_id'):
        raise ManualEvidenceError('use either a selected research report or manual quote evidence')
    return asset


def valid_quote(quote: Quote | None, asset: Asset) -> None:
    if quote is None or quote.asset_id != asset.id:
        raise ManualEvidenceError('manual quote evidence requires a matching server quote')
    age = (datetime.now(timezone.utc) - utc(quote.as_of)).total_seconds()
    if not 0 <= age < 900 or not Decimal(str(quote.price)).is_finite() or Decimal(str(quote.price)) <= 0:
        raise ManualEvidenceError('manual quote evidence requires a fresh positive server quote')


def prepare_manual_evidence(db: Session, order_intent_id: str) -> dict:
    intent = db.get(OrderIntent, order_intent_id)
    if intent is None:
        raise ManualEvidenceError('order intent unavailable')
    asset = eligible(db, intent)
    quote = db.scalar(select(Quote).where(Quote.asset_id == asset.id).order_by(Quote.as_of.desc(), Quote.id.desc()).limit(1))
    valid_quote(quote, asset)
    payload = terms(intent, asset, quote)
    snapshot = DataSnapshot(snapshot_type='manual_paper_quote', as_of=quote.as_of, data_json=payload,
                            metadata_json={'mode': 'paper', 'provider': quote.source, 'ai_used': False})
    db.add(snapshot)
    db.flush()
    db.add(DataQualityReport(data_snapshot_id=snapshot.id, source='manual_paper_quote', metric_type='quote_identity_freshness',
                             score=1, details_json={'status': 'ok', 'research_evaluated': False}))
    db.add(DataCatalogEntry(dataset_type='manual_paper_quote', source=quote.source, data_snapshot_id=snapshot.id,
                            row_count=1, quality_status='VALID', usable_for_trading=True,
                            lineage_json={'quote_id': quote.id, 'asset_id': asset.id},
                            contract_json={'mode': 'paper', 'ai_used': False, 'live_execution_available': False}))
    evidence = ManualTradeEvidence(data_snapshot_id=snapshot.id, order_intent_id=intent.id, quote_id=quote.id,
                                   user_id=intent.user_id, content_hash=digest(payload), expires_at=utc(quote.as_of) + timedelta(seconds=900))
    db.add(evidence)
    intent.evidence_json = dict(intent.evidence_json or {}) | {'manual_snapshot_id': snapshot.id}
    db.add(AuditLog(actor_type='system', actor_id='manual-paper-evidence', action='manual_trade_evidence.prepared',
                    entity_type='OrderIntent', entity_id=intent.id,
                    payload_json={'snapshot_id': snapshot.id, 'quote_id': quote.id, 'ai_used': False, 'mode': 'paper'}))
    db.commit()
    return {'order_intent_id': intent.id, 'data_snapshot_id': snapshot.id, 'quote_id': quote.id,
            'price': float(quote.price), 'quote_source': quote.source, 'quote_as_of': utc(quote.as_of),
            'expires_at': utc(evidence.expires_at), 'evidence_mode': 'manual_paper_quote'}


def validate_manual_evidence(db: Session, intent: OrderIntent, snapshot: DataSnapshot) -> ManualTradeEvidence:
    evidence = db.get(ManualTradeEvidence, snapshot.id)
    if evidence is None or evidence.order_intent_id != intent.id or evidence.user_id != intent.user_id:
        raise ManualEvidenceError('server-issued manual evidence for this order is missing')
    asset = eligible(db, intent)
    quote = db.get(Quote, evidence.quote_id)
    valid_quote(quote, asset)
    if utc(evidence.expires_at) <= datetime.now(timezone.utc):
        raise ManualEvidenceError('manual evidence expired; preview a new draft')
    if (intent.evidence_json or {}).get('manual_snapshot_id') != snapshot.id:
        raise ManualEvidenceError('manual evidence reference changed')
    if evidence.content_hash != digest(snapshot.data_json) or evidence.content_hash != digest(terms(intent, asset, quote)):
        raise ManualEvidenceError('manual evidence content or order terms changed')
    return evidence


def read_manual_evidence(db: Session, order_intent_id: str) -> dict:
    if db.get(OrderIntent, order_intent_id) is None:
        raise ManualEvidenceError('order intent unavailable')
    evidence = db.scalar(select(ManualTradeEvidence).where(ManualTradeEvidence.order_intent_id == order_intent_id)
                         .order_by(ManualTradeEvidence.created_at.desc(), ManualTradeEvidence.data_snapshot_id.desc()).limit(1))
    snapshot = db.get(DataSnapshot, evidence.data_snapshot_id) if evidence else None
    if snapshot is None:
        raise ManualEvidenceError('manual evidence unavailable')
    if evidence.content_hash != digest(snapshot.data_json):
        raise ManualEvidenceError('stored manual evidence is inconsistent; preview a new draft')
    row = snapshot.data_json['quotes'][0]
    return {'order_intent_id': order_intent_id, 'data_snapshot_id': snapshot.id, 'quote_id': evidence.quote_id,
            'price': float(row['price']), 'quote_source': row['source'], 'quote_as_of': row['as_of'],
            'expires_at': utc(evidence.expires_at), 'evidence_mode': 'manual_paper_quote'}
