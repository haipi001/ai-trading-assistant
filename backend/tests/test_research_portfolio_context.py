import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
import pytest
from sqlalchemy import select,func
from test_local_secrets_and_llm_credentials import db,isolated_store,owner,configure_chat,report_for
from app.models import Account,Asset,Position,DataSnapshot,OrderIntent
from app.models.core import utc_now
from app.services.research_portfolio_context import prepare_portfolio_context,load_portfolio_context,validate_portfolio_citations,PortfolioContextError
from app.services.human_control import HumanControlService


def seed(db,user='owner-user',account='account-a',kind='brokerage'):
    a=Account(id=account,user_id=user,name='Private account label not sent',account_type=kind,broker='recorded broker',base_currency='USD' if kind=='brokerage' else 'USDT',mode='paper',live_trading_enabled=False)
    asset=Asset(id='asset-'+account,symbol='AAPL' if kind=='brokerage' else 'ETH',name='Recorded asset',asset_type='stock' if kind=='brokerage' else 'crypto',market='US' if kind=='brokerage' else 'GLOBAL',venue='NASDAQ' if kind=='brokerage' else 'CEX',currency='USD' if kind=='brokerage' else 'USDT')
    p=Position(id='position-'+account,user_id=user,account_id=account,asset_id=asset.id,quantity=Decimal('1.1234567890'),average_cost=10,market_price=0,market_value=0)
    db.add_all([a,asset,p]);db.commit();return a,p


def ref(account='account-a',market='stocks',version=2):return {'account_id':account,'market':market,'context_version':version}


def test_prepared_ledger_is_owned_immutable_bounded_and_not_live_valuation(db):
    a,p=seed(db);value=prepare_portfolio_context(db,'owner-user',ref());material=value['provided_portfolio']
    assert value['execution_available'] is False and material['independently_verified'] is False
    assert material['valuation_freshness']=='unknown'
    assert material['entries'][1]['quantity']=='1.123456789'
    assert material['entries'][1]['quote_as_of'] is None
    assert material['entries'][1]['valuation_verified'] is False
    assert a.name not in json.dumps(value)
    assert load_portfolio_context(db,'owner-user',value['reference'])==material
    p.quantity=2;db.commit()
    assert db.get(DataSnapshot,value['reference']['snapshot_id']).data_json==material
    with pytest.raises(PortfolioContextError,match='ai_portfolio_changed'):load_portfolio_context(db,'owner-user',value['reference'])
    assert db.scalar(select(func.count()).select_from(OrderIntent))==0
    from app.services.data_sources import DataSourceService
    from app.services.data_catalog import DataCatalogService
    assert DataSourceService(db).list_snapshots(snapshot_type='terminal_portfolio_ledger')==[]
    assert DataCatalogService(db).snapshot_decision_gate(value['reference']['snapshot_id'],decision_scope='order_draft')['status']!='trusted'


def test_foreign_accounts_snapshots_and_market_rebinding_fail_closed(db):
    seed(db);seed(db,user='other',account='foreign')
    with pytest.raises(PortfolioContextError):prepare_portfolio_context(db,'owner-user',ref('foreign'))
    with pytest.raises(PortfolioContextError):prepare_portfolio_context(db,'owner-user',ref(market='cex'))
    source=prepare_portfolio_context(db,'owner-user',ref())
    with pytest.raises(PortfolioContextError):load_portfolio_context(db,'other',source['reference'])
    for patch in [{'account_id':'foreign'},{'context_version':3},{'market':'cex'},{'balances':[1]}]:
        with pytest.raises(PortfolioContextError):load_portfolio_context(db,'owner-user',{**source['reference'],**patch})
    row=db.get(DataSnapshot,source['reference']['snapshot_id']);row.as_of=utc_now()-timedelta(minutes=11);db.commit()
    with pytest.raises(PortfolioContextError,match='ai_portfolio_stale'):load_portfolio_context(db,'owner-user',source['reference'])


def test_portfolio_source_caps_records_and_unknown_values_without_fabricated_totals(db):
    a,p=seed(db)
    for i in range(24):db.add(Position(id=f'extra-{i:02}',user_id='owner-user',account_id=a.id,asset_id=p.asset_id,quantity=i,average_cost=0,market_price=0,market_value=0))
    db.commit();material=prepare_portfolio_context(db,'owner-user',ref())['provided_portfolio']
    assert material['total_position_count']==25 and material['included_count']==20 and material['truncated'] is True
    assert len(material['entries'])==21
    assert 'total_value' not in material and 'weight' not in material['entries'][1]


@pytest.mark.parametrize('failure',[False,True])
def test_portfolio_research_freezes_effective_reply_or_failure_with_owned_history(db,isolated_store,monkeypatch,failure):
    seed(db);service=HumanControlService(db);configure_chat(service)
    source=service.research_portfolio_prepare(actor=owner(),payload=ref())
    class Provider:
        def generate_report(self,**kwargs):
            if failure:raise RuntimeError('controlled failure')
            assert kwargs['input_facts']['portfolio_context']['account_id']=='account-a'
            assert kwargs['report_type']=='portfolio_daily_review'
            value=report_for(kwargs);value['summary']='Stored ledger claim [H1] and position [H2].'
            value['evidence']={'portfolio_citation_ids':['H1','H2']};return json.dumps(value)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda *_:Provider())
    result=service.research_chat(actor=owner(),payload={'question':'Review stored ledger only','page':'assets','symbol':'AAPL','portfolio_context':source['reference']})
    assert result['status']==('failed' if failure else 'ok')
    assert result['context_scope']=='question_history_workspace_and_portfolio_snapshot'
    assert result['execution_available'] is False
    identifier=result['portfolio_context_snapshot_id']
    history=service.research_portfolio_history(actor=owner(),account_id='account-a',market='stocks')
    assert history['items'][0]['snapshot_id']==identifier
    artifact=service.research_portfolio_snapshot(actor=owner(),snapshot_id=identifier)
    assert artifact['provided_portfolio']==source['provided_portfolio']
    if failure:assert artifact['validated_reply'] is None
    else:assert artifact['validated_reply']['cited_portfolio_ids']==['H1','H2']
    assert service.research_portfolio_history(actor=owner('other'),account_id='account-a',market='stocks')['items']==[]


def test_invalid_portfolio_stops_before_provider_and_citations_cannot_be_rebound(db,isolated_store,monkeypatch):
    seed(db);service=HumanControlService(db);configure_chat(service)
    def unexpected(*args,**kwargs):raise AssertionError('must not construct Provider')
    monkeypatch.setattr(service,'_provider_from_llm_config',unexpected)
    response=service.research_chat(actor=owner(),payload={'question':'No source','portfolio_context':{'invalid':True}})
    assert response['status']=='blocked' and response['external_call_attempted'] is False
    report=SimpleNamespace(evidence={'portfolio_citation_ids':['H9']},summary='Claim [H9]',bullish_case='',bearish_case='',key_risks=[],limitations='',suggested_action='')
    with pytest.raises(PortfolioContextError):validate_portfolio_citations(report,{'entries':[{'id':'H1'}]})


def test_portfolio_news_freezes_both_sources_and_invalid_citations_do_not_save_valid_reply(db,isolated_store,monkeypatch):
    from test_local_secrets_and_llm_credentials import seed_chat_news
    seed(db);seed_chat_news(db);service=HumanControlService(db);configure_chat(service)
    prepared=service.research_portfolio_prepare(actor=owner(),payload=ref());invalid=[False]
    class Provider:
        def generate_report(self,**kwargs):
            value=report_for(kwargs);identifier='H999' if invalid[0] else 'H2'
            value['summary']='Record ['+identifier+'] and source claim [N1].'
            value['evidence']={'portfolio_citation_ids':[identifier],'news_citation_ids':['N1']};return json.dumps(value)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda *_:Provider())
    payload={'question':'Review ledger and news','page':'assets','include_news':True,'portfolio_context':prepared['reference']}
    result=service.research_chat(actor=owner(),payload=payload)
    assert result['status']=='ok' and result['context_scope']=='question_history_workspace_news_and_portfolio_snapshots'
    artifact=service.research_portfolio_snapshot(actor=owner(),snapshot_id=result['portfolio_context_snapshot_id'])
    assert artifact['provided_news']['articles'][0]['id']=='N1'
    invalid[0]=True;failed=service.research_chat(actor=owner(),payload=payload)
    assert failed['status']=='failed'
    assert service.research_portfolio_snapshot(actor=owner(),snapshot_id=failed['portfolio_context_snapshot_id'])['validated_reply'] is None


def test_changed_ledger_and_mixed_material_block_before_provider_construction(db,isolated_store,monkeypatch):
    from test_research_market_context import packet
    a,p=seed(db);service=HumanControlService(db);configure_chat(service)
    prepared=service.research_portfolio_prepare(actor=owner(),payload=ref())
    def unexpected(*args,**kwargs):raise AssertionError('not allowed to construct a model')
    monkeypatch.setattr(service,'_provider_from_llm_config',unexpected)
    mixed=service.research_chat(actor=owner(),payload={'question':'Mixed','symbol':'ETH','market_context':packet(),'portfolio_context':prepared['reference']})
    assert mixed['status']=='blocked' and mixed['reason']=='ai_portfolio_incompatible'
    p.quantity=3;db.commit()
    changed=service.research_chat(actor=owner(),payload={'question':'Old ledger','portfolio_context':prepared['reference']})
    assert changed['status']=='blocked' and changed['reason']=='ai_portfolio_changed' and changed['external_call_attempted'] is False


def test_corrupt_portfolio_material_is_a_controlled_failure(db):
    seed(db);prepared=prepare_portfolio_context(db,'owner-user',ref());source=db.get(DataSnapshot,prepared['reference']['snapshot_id']);source.data_json=['corrupt'];db.commit()
    with pytest.raises(PortfolioContextError,match='ai_portfolio_source_invalid'):load_portfolio_context(db,'owner-user',prepared['reference'])
