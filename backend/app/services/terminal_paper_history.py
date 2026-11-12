"""Owned application Paper records; no broker/live-fill or valuation claims."""
from datetime import timezone
from decimal import Decimal
from sqlalchemy import select, or_, and_
from fastapi import HTTPException
from app.models import Execution,OrderDraft,OrderIntent,Asset,PostTradeReview,TradeJournalEntry
from app.models.core import utc_now
from app.services.strategy_research_material import owned_account


def paper_trade_history(db,user_id,account_id,market,after=None):
    owned_account(db,user_id,account_id,market)
    asset_types=['stock','etf'] if market=='stocks' else ['crypto','crypto_spot']
    query=select(Execution,OrderIntent,Asset).join(OrderDraft,Execution.order_draft_id==OrderDraft.id).join(OrderIntent,OrderDraft.order_intent_id==OrderIntent.id).join(Asset,OrderIntent.asset_id==Asset.id).where(Execution.user_id==user_id,OrderDraft.user_id==user_id,OrderIntent.user_id==user_id,OrderIntent.account_id==account_id,Execution.execution_mode=='paper',Asset.asset_type.in_(asset_types),Asset.chain_id.is_(None),Asset.contract_address.is_(None)).order_by(Execution.created_at.desc(),Execution.id.desc())
    if after is not None:
        anchor=db.execute(query.where(Execution.id==after)).first()
        if anchor is None:
            raise HTTPException(status_code=422,detail="Paper history cursor is unavailable in this account and market")
        fill=anchor[0]
        query=query.where(or_(Execution.created_at<fill.created_at,and_(Execution.created_at==fill.created_at,Execution.id<fill.id)))
    rows=list(db.execute(query.limit(101)).all())
    ids=[fill.id for fill,intent,asset in rows[:100]]
    review_ids=set(db.scalars(select(PostTradeReview.execution_id).join(TradeJournalEntry,PostTradeReview.trade_journal_entry_id==TradeJournalEntry.id).join(Execution,PostTradeReview.execution_id==Execution.id).join(OrderDraft,Execution.order_draft_id==OrderDraft.id).join(OrderIntent,OrderDraft.order_intent_id==OrderIntent.id).where(PostTradeReview.execution_id.in_(ids),PostTradeReview.user_id==user_id,TradeJournalEntry.user_id==user_id,TradeJournalEntry.account_id==account_id,TradeJournalEntry.asset_id==OrderIntent.asset_id,PostTradeReview.order_draft_id==Execution.order_draft_id,Execution.user_id==user_id,OrderDraft.user_id==user_id,OrderIntent.user_id==user_id,OrderIntent.account_id==account_id))) if ids else set()
    def number(value):return None if value is None else format(Decimal(str(value)),'f')
    return {'source':'owned_application_paper_ledger','account_id':account_id,'market':market,'captured_at':utc_now().isoformat(),'execution_available':False,'has_more':len(rows)>100,'next_cursor':rows[99][0].id if len(rows)>100 else None,'entries':[{'execution_id':fill.id,'review_available':fill.id in review_ids,'order_draft_id':fill.order_draft_id,'asset_id':asset.id,'symbol':asset.symbol,'venue':asset.venue,'asset_currency':asset.currency,'side':intent.side,'status':fill.status,'execution_mode':'paper','quantity':number(fill.filled_quantity),'price':number(fill.average_fill_price),'fee':number(fill.fee_amount),'realized_pnl':number(fill.realized_pnl),'recorded_at':fill.created_at.replace(tzinfo=timezone.utc).isoformat() if fill.created_at.tzinfo is None else fill.created_at.isoformat()} for fill,intent,asset in rows[:100]],'limitations':'Saved application Paper records only. No broker fills, live prices, FX conversion or complete account-wide return calculation.'}
