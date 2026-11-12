"""Controlled real business APIs; mock data/model, never a live-account acceptance."""
import pytest
from app.models import InvestmentConstitution,Quote
from sqlalchemy import select
from test_decision_gates import create_constitution,create_report
from test_server_account_risk import edit_db


def ok(response,status=201):
    assert response.status_code==status,response.text
    return response.json()


def run_loop(client,market,symbol,asset_type,asset_market,venue,quantity):
    previous_executions=ok(client.get('/paper-executions'),200)
    account=ok(client.post('/accounts',json={'name':f'Controlled {market} loop','account_type':'brokerage' if market=='stocks' else 'exchange_account','broker':'mock','base_currency':'USD','mode':'paper'}))
    # Explicit operator-created Paper test asset; importing research does not enable trading.
    existing=[a for a in ok(client.get('/assets'),200) if (a['symbol'],a['asset_type'],a['market'],a['venue'],a['currency'])==(symbol,asset_type,asset_market,venue,'USD')]
    assert len(existing)<=1
    if not existing:
        ok(client.post('/assets',json={'symbol':symbol,'name':f'Controlled {market} instrument','asset_type':asset_type,'market':asset_market,'venue':venue,'currency':'USD','tradable':True,'manual_enabled':True,'auto_enabled':False,'risk_level':'medium'}))
    constitution=create_constitution(client)
    edit_db(lambda db:setattr(db.get(InvestmentConstitution,constitution['id']),'allowed_markets',['US','GLOBAL']))
    ok(client.post('/risk-budgets',json={'user_id':'default-user','constitution_id':constitution['id'],'account_id':account['id'],'asset_class':asset_type,'max_allocation_pct':.8,'max_loss_pct':.08,'max_order_notional':1000,'max_leverage':1,'rebalance_threshold_pct':.05}))
    connection=ok(client.post('/data-sources/connections',json={'name':f'Controlled {market} source','provider':'mock_market_data','source_type':'market_data','mode':'read_only'}))
    imported=ok(client.post(f"/data-sources/connections/{connection['id']}/import-quotes",json={'symbols':[symbol],'asset_type':asset_type,'market':asset_market,'venue':venue,'currency':'USD'}))
    for stage in ['reviewed','trusted']:
        promoted=ok(client.post(f"/data-catalog/entries/{imported['catalog_entry']['id']}/promote"),200)
        assert promoted['current_stage']==stage
    report=create_report(client,imported['snapshot']['id'])
    assets=ok(client.get('/assets'),200)
    candidates=[a for a in assets if (a['symbol'],a['asset_type'],a['market'],a['venue'],a['currency'])==(symbol,asset_type,asset_market,venue,'USD')]
    assert len(candidates)==1
    asset=candidates[0]
    thesis=ok(client.post('/theses/manual-paper',json={'asset_id':asset['id'],'account_id':account['id'],'entry_reason':'Explicit human investment rationale for the controlled mock instrument.','key_drivers':['Original evidence to verify'],'invalidation_conditions':['Original evidence breaks'],'expected_horizon':'swing','target_condition':'Reassess after the original evidence changes.','max_loss_tolerance_pct':.02,'confidence':.7}))['thesis']
    checkpoint=ok(client.post(f"/reports/{report['id']}/review-thesis",json={'thesis_id':thesis['id'],'decision':'supports','human_summary':'Controlled mock evidence reviewed by the test user; no claim about current markets.','confidence':.7}))
    assert checkpoint['execution_available'] is False
    ok(client.post('/mock/update-quotes'),200)
    prices=[]
    edit_db(lambda db:prices.append(float(db.scalar(select(Quote).where(Quote.asset_id==asset['id']).order_by(Quote.as_of.desc(),Quote.id.desc()).limit(1)).price)))
    price=prices[0]
    plan=ok(client.post(f"/reports/{report['id']}/create-plan-and-evaluate",json={'thesis_id':thesis['id'],'account_id':account['id'],'side':'buy','order_type':'limit','quantity':quantity,'limit_price':price,'user_rationale':'Explicit controlled human research rationale; Paper only.','risk_context':{'data_quality_status':'acceptable','liquidity_passed':True}}))
    assert all(gate['status']=='PASSED' for gate in plan['gates']), __import__('json').dumps(plan['gates'],ensure_ascii=False)
    assert plan['execution_available'] is False
    intent=plan['order_intent']
    assert intent['evidence_json']['thesis_checkpoint_id']==checkpoint['checkpoint']['id']
    draft=ok(client.post(f"/orders/intents/{intent['id']}/draft",json={'order_intent_id':intent['id']}))
    assert draft['approval_status']=='pending'
    refused=client.post(f"/paper-executions/drafts/{draft['id']}/execute",json={'fill_price':price})
    assert refused.status_code==422
    assert ok(client.get('/paper-executions'),200)==previous_executions
    approved=ok(client.post(f"/orders/drafts/{draft['id']}/approve",json={'decision_reason':'Explicit separate controlled Paper approval.'}))
    assert approved['status']=='approved'
    assert ok(client.get(f"/orders/drafts/{draft['id']}"),200)['approval_status']=='approved'
    filled=ok(client.post(f"/paper-executions/drafts/{draft['id']}/execute",json={'fill_price':price,'idempotency_key':f'controlled-{market}-loop'}))
    execution=filled['execution']
    assert execution['execution_mode']=='paper'
    context=ok(client.get(f"/paper-executions/{execution['id']}/review-context"),200)
    review=context['post_trade_review']
    assert context['journal_entry']['account_id']==account['id']
    assert context['journal_entry']['asset_id']==asset['id']
    saved=ok(client.patch(f"/post-trade-reviews/{review['id']}",json={'expected_updated_at':review['updated_at'],'status':'completed','review_json':{'terminal_manual_review':{'notes':'Controlled human review of rationale and mock fill.','source':'human'}}}),200)
    reloaded=ok(client.get(f"/paper-executions/{execution['id']}/review-context"),200)
    assert reloaded['post_trade_review']==saved
    assert saved['status']=='completed'
    replay=ok(client.post(f"/paper-executions/drafts/{draft['id']}/execute",json={'fill_price':price,'idempotency_key':f'controlled-{market}-loop'}))
    assert replay['execution']['id']==execution['id']
    assert len(ok(client.get('/paper-executions'),200))==len(previous_executions)+1
    return {'account':account,'asset':asset,'report':report,'execution':execution,'review':saved,'plan':plan,'draft':draft,'thesis':thesis,'price':price,'quantity':quantity}


@pytest.mark.parametrize('args',[
    ('stocks','AAPL','stock','US','NASDAQ',1),
    ('cex','BTC','crypto','GLOBAL','CEX',.001),
])
def test_research_to_human_approval_paper_and_saved_review(client,args):
    run_loop(client,*args)


def test_same_user_keeps_stock_and_cex_execution_and_review_material_separate(client):
    stock=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1)
    cex=run_loop(client,'cex','BTC','crypto','GLOBAL','CEX',.001)
    assert stock['account']['id']!=cex['account']['id']
    assert stock['asset']['id']!=cex['asset']['id']
    assert stock['report']['data_snapshot_id']!=cex['report']['data_snapshot_id']
    for item in [stock,cex]:
        restored=ok(client.get(f"/paper-executions/{item['execution']['id']}/review-context"),200)
        assert restored['post_trade_review']==item['review']
        assert restored['journal_entry']['account_id']==item['account']['id']
        assert restored['journal_entry']['asset_id']==item['asset']['id']
