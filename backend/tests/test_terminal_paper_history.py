import json
import subprocess
import shutil
from pathlib import Path
import pytest
from test_terminal_research_paper_loop import run_loop
from test_manual_paper_thesis import business_counts

@pytest.mark.parametrize('market,symbol,asset_type,region,venue,quantity',[('stocks','AAPL','stock','US','NASDAQ',1),('cex','BTC','crypto','GLOBAL','CEX',.001)])
def test_owned_paper_history_reads_actual_records_without_creating_trades(client,market,symbol,asset_type,region,venue,quantity):
    result=run_loop(client,market,symbol,asset_type,region,venue,quantity)
    before=business_counts();account_id=result['account']['id']
    response=client.get('/api/v2/workspaces/research/paper-trades',params={'account_id':account_id,'market':market})
    assert response.status_code==200,response.text
    packet=response.json();assert response.headers['cache-control']=='no-store'
    assert packet['source']=='owned_application_paper_ledger' and packet['execution_available'] is False
    row=next(row for row in packet['entries'] if row['execution_id']==result['execution']['id'])
    assert row['symbol']==symbol and row['execution_mode']=='paper'
    assert row['review_available'] is True
    assert isinstance(row['quantity'],str) and isinstance(row['fee'],str)
    review=client.get('/paper-executions/'+row['execution_id']+'/review-context')
    assert review.status_code==200
    assert review.json()['journal_entry']['account_id']==account_id
    assert client.get('/api/v2/workspaces/research/paper-trades',params={'account_id':account_id,'market':market},headers={'X-AI-Trading-User':'foreign'}).status_code==404
    assert client.get('/api/v2/workspaces/research/paper-trades',params={'account_id':account_id,'market':'cex' if market=='stocks' else 'stocks'}).status_code==422
    assert business_counts()==before
    if shutil.which('node'):
        source=Path(__file__).resolve().parents[2]/'src'/'paper-trade-history.js'
        code="import {readFileSync} from 'node:fs';const {paperTradeHistory,paperTradeCsv,paperHistoryReview}=await import(process.argv[1]);const d=JSON.parse(readFileSync(0,'utf8'));paperTradeHistory(d.packet,d.context);paperHistoryReview(d.review,d.row,d.context);if(!paperTradeCsv(d.packet).includes('paper'))throw Error('missing Paper label');"
        checked=subprocess.run(['node','--input-type=module','-e',code,source.as_uri()],input=json.dumps({'packet':packet,'context':{'accountId':account_id,'market':market},'review':review.json(),'row':row}),text=True,capture_output=True,timeout=20)
        assert checked.returncode==0,checked.stderr


def test_missing_owned_review_is_reported_without_fabricating_history_records(client):
    from app.models import PostTradeReview
    from test_server_account_risk import edit_db
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1)
    edit_db(lambda db:setattr(db.get(PostTradeReview,result['review']['id']),'user_id','other-user'))
    packet=client.get('/api/v2/workspaces/research/paper-trades',params={'account_id':result['account']['id'],'market':'stocks'}).json()
    row=next(row for row in packet['entries'] if row['execution_id']==result['execution']['id'])
    assert row['review_available'] is False
    assert client.get('/paper-executions/'+row['execution_id']+'/review-context').status_code==409


@pytest.mark.parametrize('same_time',[False,True])
def test_paper_history_keyset_pages_are_owned(client,same_time):
    from datetime import timedelta
    from app.models import Execution
    from test_server_account_risk import edit_db
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1)
    def populate(db):
        original=db.get(Execution,result['execution']['id'])
        for index in range(104):
            values={column.name:getattr(original,column.name) for column in Execution.__table__.columns if column.name!='id'}
            values['created_at']=original.created_at-timedelta(seconds=1 if same_time else index+1)
            values['fill_sequence']=index+2
            values['idempotency_key']=f'pagination-key-{index}'
            db.add(Execution(id=f'pagination-{index:03}',**values))
    edit_db(populate)
    params={'account_id':result['account']['id'],'market':'stocks'}
    first=client.get('/api/v2/workspaces/research/paper-trades',params=params)
    assert first.status_code==200,first.text
    page=first.json();assert len(page['entries'])==100 and page['has_more']
    cursor=page['next_cursor'];assert cursor==page['entries'][-1]['execution_id']
    # Newer inserts must not shift the older-page boundary.
    def insert_newer(db):
        original=db.get(Execution,result['execution']['id'])
        values={column.name:getattr(original,column.name) for column in Execution.__table__.columns if column.name!='id'}
        values.update(created_at=original.created_at+timedelta(seconds=1),fill_sequence=106,idempotency_key='new-between-pages')
        db.add(Execution(id='new-between-pages',**values))
        foreign=dict(values,user_id='foreign-user',fill_sequence=107,idempotency_key='foreign-anchor')
        db.add(Execution(id='foreign-anchor',**foreign))
    edit_db(insert_newer)
    second=client.get('/api/v2/workspaces/research/paper-trades',params={**params,'after':cursor})
    assert second.status_code==200,second.text
    tail=second.json();assert len(tail['entries'])==5 and not tail['has_more'] and tail['next_cursor'] is None
    assert not {row['execution_id'] for row in page['entries']} & {row['execution_id'] for row in tail['entries']}
    assert client.get('/api/v2/workspaces/research/paper-trades',params={**params,'after':'unknown-fill'}).status_code==422
    assert client.get('/api/v2/workspaces/research/paper-trades',params={**params,'after':cursor},headers={'X-AI-Trading-User':'foreign'}).status_code==404

    assert client.get('/api/v2/workspaces/research/paper-trades',params={**params,'after':'foreign-anchor'}).status_code==422
    combined=page['entries']+tail['entries']
    assert len({row['execution_id'] for row in combined})==105
    assert 'new-between-pages' not in {row['execution_id'] for row in combined}
    refreshed=client.get('/api/v2/workspaces/research/paper-trades',params=params).json()
    assert refreshed['entries'][0]['execution_id']=='new-between-pages'
