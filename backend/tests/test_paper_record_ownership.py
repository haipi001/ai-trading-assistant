from sqlalchemy import select
from app.models import Account,OrderDraft,OrderIntent,Position,PaperTaxLot,AuditLog
from app.services.paper_execution import PaperExecutionService,PaperExecutionBlockedError
from test_paper_execution import create_approved_draft
from test_onchain_history_http import database
import pytest


def test_paper_writer_without_request_tenant_uses_account_owner_for_all_generated_records(client,monkeypatch):
    draft=create_approved_draft(client)
    with database() as db:
        stored=db.get(OrderDraft,draft['id'])
        intent=db.get(OrderIntent,stored.order_intent_id);account=db.get(Account,intent.account_id)
        # Isolate the ledger writer from policy fixtures tied to default-user.
        owner='record-owner';stored.user_id=owner;intent.user_id=owner;account.user_id=owner
        for position in db.scalars(select(Position).where(Position.account_id==account.id)):position.user_id=owner
        db.commit()
        monkeypatch.setattr(PaperExecutionService,'_ensure_paper_executable',lambda *_:None)
        result=PaperExecutionService(db).execute_draft(stored,approver_id='human-user',decision_reason='Controlled ownership regression',fill_price=225.12,fee_bps=0)
        execution,journal,review,_,lots,_=result
        assert {execution.user_id,journal.user_id,review.user_id}=={owner}
        assert all(lot.user_id==owner for lot in lots)
        assert all(position.user_id==owner for position in db.scalars(select(Position).where(Position.account_id==journal.account_id)))
        assert all(audit.user_id==owner for audit in db.scalars(select(AuditLog).where(AuditLog.entity_id==execution.id)))


def test_paper_service_rejects_mismatched_owner_chain_before_execution(client):
    draft=create_approved_draft(client)
    with database() as db:
        stored=db.get(OrderDraft,draft['id']);stored.user_id='foreign';db.commit()
        with pytest.raises(PaperExecutionBlockedError,match='owner mismatch'):
            PaperExecutionService(db).execute_draft(stored,approver_id='human-user',decision_reason='Must refuse',fill_price=225.12,fee_bps=0)


@pytest.mark.parametrize('entity',['review','journal'])
def test_idempotent_receipt_refuses_foreign_related_records_without_a_second_fill(client,entity):
    from app.models import PostTradeReview,TradeJournalEntry,Execution
    from sqlalchemy import func
    draft=create_approved_draft(client)
    body={'fill_price':225.12,'idempotency_key':'owner-check'}
    response=client.post('/paper-executions/drafts/'+draft['id']+'/execute',json=body)
    assert response.status_code==201
    value=response.json()
    with database() as db:
        record=db.get(PostTradeReview,value['post_trade_review']['id']) if entity=='review' else db.get(TradeJournalEntry,value['journal_entry']['id'])
        record.user_id='foreign';db.commit()
    replay=client.post('/paper-executions/drafts/'+draft['id']+'/execute',json=body)
    assert replay.status_code==422
    assert 'receipt incomplete' in replay.text
    with database() as db:assert db.scalar(select(func.count()).select_from(Execution))==1
