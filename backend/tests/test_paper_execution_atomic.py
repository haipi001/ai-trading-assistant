"""File-backed DB, independent HTTP request sessions, and real competing writers."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models import Execution, Position, Asset, PaperTaxLot, PostTradeReview, TradeJournalEntry, AuditLog, Approval
from app.services.paper_execution import PaperExecutionService
from test_paper_execution import create_approved_draft
from test_decision_gates import create_account, create_asset


@pytest.fixture
def persisted(tmp_path):
    engine = create_engine(f'sqlite+pysqlite:///{tmp_path}/concurrent.sqlite',
                           connect_args={'check_same_thread': False, 'timeout': 15})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    previous = app.dependency_overrides.get(get_db)
    def dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        if previous is None: app.dependency_overrides.pop(get_db, None)
        else: app.dependency_overrides[get_db] = previous
        engine.dispose()


def send(client, draft, **body):
    return client.post(f"/paper-executions/drafts/{draft['id']}/execute", json={'fill_price': 225.12} | body)


def parallel(client, requests):
    barrier = Barrier(len(requests))
    def call(pair):
        barrier.wait(timeout=10)
        draft, body = pair
        return send(client, draft, **body)
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(call, requests))


def ledger(factory, expected_fills, quantity):
    with factory() as db:
        fills = list(db.scalars(select(Execution)).all())
        assert len(fills) == expected_fills
        assert db.scalar(select(func.count()).select_from(PostTradeReview)) == expected_fills
        assert db.scalar(select(func.count()).select_from(TradeJournalEntry)) == expected_fills
        assert db.scalar(select(func.sum(Position.quantity)).join(Asset, Position.asset_id == Asset.id)
                         .where(Asset.asset_type != 'cash')) == quantity
        cash = db.scalar(select(Position).join(Asset, Position.asset_id == Asset.id).where(Asset.asset_type == 'cash'))
        assert float(cash.quantity) == pytest.approx(100000 + sum(float(fill.cash_effect) for fill in fills))
        assert all(fill.fill_sequence is not None for fill in fills)


@pytest.mark.parametrize('keys', [None, ('same', 'same'), ('first', 'second')])
def test_competing_full_requests_cannot_double_fill(persisted, monkeypatch, keys):
    client, factory = persisted
    draft = create_approved_draft(client)
    active, maximum = 0, 0
    guard = Lock()
    original = PaperExecutionService._execute_draft_locked
    def slow(self, *args, **kwargs):
        nonlocal active, maximum
        with guard:
            active += 1; maximum = max(maximum, active)
        try:
            time.sleep(0.05)  # Force overlap while the DB account/write lock is held.
            return original(self, *args, **kwargs)
        finally:
            with guard: active -= 1
    monkeypatch.setattr(PaperExecutionService, '_execute_draft_locked', slow)
    bodies = [{}, {}] if keys is None else [{'idempotency_key': key} for key in keys]
    responses = parallel(client, [(draft, body) for body in bodies])
    if keys == ('same', 'same'):
        assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
        assert sorted(r.json()['replayed'] for r in responses) == [False, True]
        assert responses[0].json()['execution']['id'] == responses[1].json()['execution']['id']
    else:
        assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    assert maximum == 1
    ledger(factory, 1, 1)


def test_partial_same_key_replays_and_new_key_finishes_without_overfill(persisted):
    client, factory = persisted
    draft = create_approved_draft(client, quantity=2, notional=450.24)
    first = send(client, draft, fill_quantity=1, idempotency_key='part-one')
    assert first.status_code == 201, first.text
    replay = send(client, draft, fill_quantity=1, idempotency_key='part-one')
    assert replay.status_code == 201 and replay.json()['replayed']
    assert replay.json()['execution']['id'] == first.json()['execution']['id']
    second = send(client, draft, fill_quantity=1, idempotency_key='part-two')
    assert second.status_code == 201 and not second.json()['replayed']
    assert second.json()['execution']['fill_sequence'] == 2
    assert second.json()['order_draft']['execution_status'] == 'paper_filled'
    late = send(client, draft, fill_quantity=1, idempotency_key='part-one')
    assert late.status_code == 201 and late.json()['replayed']
    assert late.json()['execution']['id'] == first.json()['execution']['id']
    ledger(factory, 2, 2)


def test_competing_partial_requests_use_fresh_remaining_quantity(persisted):
    client, factory = persisted
    draft = create_approved_draft(client, quantity=2, notional=450.24)
    responses = parallel(client, [(draft, {'fill_quantity': 1, 'idempotency_key': key}) for key in ('one', 'two', 'three')])
    assert sorted(r.status_code for r in responses) == [201, 201, 422], [r.text for r in responses]
    assert sorted(r.json()['execution']['fill_sequence'] for r in responses if r.status_code == 201) == [1, 2]
    ledger(factory, 2, 2)


def test_distinct_drafts_share_account_lock_and_do_not_lose_cash_or_position_updates(persisted):
    client, factory = persisted
    asset, account = create_asset(client), create_account(client)
    drafts = [create_approved_draft(client, asset=asset, account=account) for _ in range(2)]
    responses = parallel(client, [(draft, {'idempotency_key': 'one'}) for draft in drafts])
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    ledger(factory, 2, 2)


def test_reused_key_with_changed_parameters_is_not_a_new_fill(persisted):
    client, factory = persisted
    draft = create_approved_draft(client, quantity=2, notional=450.24)
    assert send(client, draft, fill_quantity=1, idempotency_key='same').status_code == 201
    response = send(client, draft, fill_quantity=1, fee_bps=5, idempotency_key='same')
    assert response.status_code == 422
    assert 'different execution parameters' in response.json()['detail']
    ledger(factory, 1, 1)


def test_committed_receipt_can_be_read_by_retry_after_approval_expires(persisted):
    from datetime import datetime, timedelta, timezone
    client, factory = persisted
    draft = create_approved_draft(client)
    first = send(client, draft, idempotency_key='stable')
    assert first.status_code == 201
    with factory() as db:
        approval = db.scalar(select(Approval).where(Approval.order_draft_id == draft['id']))
        approval.decided_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    replay = send(client, draft, idempotency_key='stable')
    assert replay.status_code == 201 and replay.json()['replayed']
    assert replay.json()['execution']['id'] == first.json()['execution']['id']
    ledger(factory, 1, 1)


def test_failure_after_cash_lots_and_journal_flush_rolls_everything_back_then_same_key_can_retry(persisted, monkeypatch):
    client, factory = persisted
    draft = create_approved_draft(client)
    original = PaperExecutionService._write_audit_log
    def fail(self, **kwargs):
        if kwargs['action'] == 'post_trade_review.created_from_paper_execution':
            raise RuntimeError('injected failure after ledger mutation')
        return original(self, **kwargs)
    monkeypatch.setattr(PaperExecutionService, '_write_audit_log', fail)
    with pytest.raises(RuntimeError, match='injected failure'):
        send(client, draft, idempotency_key='retry-after-rollback')
    ledger(factory, 0, None)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PaperTaxLot)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'paper_execution.filled')) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'paper_execution.attempt_failed')) == 1
    monkeypatch.setattr(PaperExecutionService, '_write_audit_log', original)
    response = send(client, draft, idempotency_key='retry-after-rollback')
    assert response.status_code == 201 and response.json()['execution']['fill_sequence'] == 1
    ledger(factory, 1, 1)


def test_database_rejects_missing_sequence_and_duplicate_fill_identity(persisted):
    client, factory = persisted
    draft = create_approved_draft(client)
    first = send(client, draft, idempotency_key='unique')
    assert first.status_code == 201
    for sequence, key in [(None, 'new'), (1, 'other'), (2, 'unique')]:
        with factory() as db:
            db.add(Execution(order_draft_id=draft['id'], execution_mode='paper', fill_sequence=sequence, idempotency_key=key))
            with pytest.raises(IntegrityError): db.commit()
            db.rollback()
    ledger(factory, 1, 1)


def test_lost_response_after_commit_retries_the_committed_receipt_without_second_fill(persisted, monkeypatch):
    from sqlalchemy.orm import Session
    client, factory = persisted
    draft = create_approved_draft(client)
    original = Session.refresh
    lost = False
    def lose_response(db, instance, *args, **kwargs):
        nonlocal lost
        if isinstance(instance, Execution) and not lost:
            lost = True
            raise RuntimeError('injected lost response after commit')
        return original(db, instance, *args, **kwargs)
    monkeypatch.setattr(Session, 'refresh', lose_response)
    with pytest.raises(RuntimeError, match='lost response after commit'):
        send(client, draft, idempotency_key='committed-but-response-lost')
    assert lost
    ledger(factory, 1, 1)
    monkeypatch.setattr(Session, 'refresh', original)
    response = send(client, draft, idempotency_key='committed-but-response-lost')
    assert response.status_code == 201 and response.json()['replayed']
    ledger(factory, 1, 1)


def test_database_conflict_is_reported_as_unknown_outcome_not_a_risk_rejection(persisted, monkeypatch):
    from sqlalchemy.exc import OperationalError
    client, factory = persisted
    draft = create_approved_draft(client)
    def conflict(*args, **kwargs):
        raise OperationalError('injected write conflict', {}, Exception('busy'))
    monkeypatch.setattr(PaperExecutionService, '_execute_draft_locked', conflict)
    response = send(client, draft, idempotency_key='recoverable-conflict')
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'paper_execution_outcome_unknown'
    ledger(factory, 0, None)
