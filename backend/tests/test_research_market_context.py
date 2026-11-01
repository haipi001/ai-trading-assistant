import json
from types import SimpleNamespace
from datetime import datetime,timedelta,timezone
import pytest
from test_local_secrets_and_llm_credentials import db,isolated_store,owner,configure_chat,report_for,seed_chat_news
from app.services.research_market_context import validate_market_context,validate_market_citations,MarketContextError,_close_time
from app.services.human_control import HumanControlService,HumanControlError
from app.models import DataSnapshot
from app.services.data_sources import DataSourceService


def packet(kind='online'):
    now=datetime.now(timezone.utc)
    start=int(now.timestamp()//60)*60-120
    return {'schema':1,'origin':'browser_chart','data_semantics':'raw_ohlcv','kind':kind,'market_type':'spot','symbol':'ETH','venue':'币安','quote_currency':'USDT','timeframe':'1m','source_label':'Public fixture OHLCV','observed_at':now.isoformat(),'captured_at':now.isoformat(),'volume_available':True,'replay_cutoff':start+180 if kind=='replay' else None,'bars':[{'time':start+i*60,'open':10,'high':12,'low':9,'close':11,'volume':2} for i in range(3)]}


@pytest.mark.parametrize('ids,text,has_context',[
    (['M1'],'Price [M1]',False),
    (['M1'],'Price [M2]',True),
    ([], 'Price [M1]',True),
    (['M1'],'No citation',True),
    (['M2'],'Price [M2]',True),
    ('M1','Price [M1]',True),
])
def test_unbound_or_fabricated_market_citations_are_rejected(ids,text,has_context):
    report=SimpleNamespace(evidence={'market_citation_ids':ids},summary=text,
        bullish_case='',bearish_case='',key_risks=[],limitations='',suggested_action='')
    with pytest.raises(MarketContextError,match='ai_market_citation_invalid'):
        validate_market_citations(report,packet() if has_context else None)


def test_market_citations_must_match_supplied_material():
    report=SimpleNamespace(evidence={'market_citation_ids':['M1']},summary='Price [M1]',
        bullish_case='',bearish_case='',key_risks=[],limitations='',suggested_action='')
    assert validate_market_citations(report,packet())==['M1']


def test_structural_context_keeps_identity_stats_and_unverified_boundary():
    value=validate_market_context(packet(),symbol='ETH')
    assert value['source_verified'] is False
    assert value['statistics']['sample_volume']==6
    assert value['statistics']['last_close']==11
    assert value['statistics']['sample_change_pct']==pytest.approx(10)
    assert value['volume_unit']=='source_raw'
    assert value['stale'] is False


@pytest.mark.parametrize('change',[{'symbol':'BTC'},{'quote_currency':'USD'},{'source_verified':True},{'source_label':'mock seed'},{'kind':'demo'},{'schema':True},{'timeframe':'1h&secret=x'}])
def test_bad_identity_or_demo_is_rejected(change):
    value=packet();value.update(change)
    with pytest.raises(MarketContextError):validate_market_context(value,symbol='ETH')


@pytest.mark.parametrize('change',[{'open':True},{'close':0},{'high':8},{'volume':float('inf')},{'volume':10**400},{'time':True}])
def test_invalid_bar_never_enters_context(change):
    value=packet();value['bars'][0].update(change)
    with pytest.raises(MarketContextError):validate_market_context(value,symbol='ETH')


def test_duplicates_and_future_replay_bar_are_rejected():
    value=packet();value['bars'][1]['time']=value['bars'][0]['time']
    with pytest.raises(MarketContextError):validate_market_context(value,symbol='ETH')
    value=packet('replay');value['replay_cutoff']=value['bars'][-1]['time']
    with pytest.raises(MarketContextError,match='future'):validate_market_context(value,symbol='ETH')


def test_calendar_and_irregular_open_times_follow_chart_period_boundaries():
    stamp=int(datetime(2026,1,31,12,tzinfo=timezone.utc).timestamp())
    assert _close_time(stamp,'1mo')==datetime(2026,2,1,tzinfo=timezone.utc).timestamp()
    assert _close_time(stamp,'3mo')==datetime(2026,4,1,tzinfo=timezone.utc).timestamp()
    assert _close_time(stamp,'1h')==datetime(2026,1,31,13,tzinfo=timezone.utc).timestamp()


def test_csv_missing_volume_is_not_reported_as_actual_zero_and_old_bars_are_marked():
    value=packet('csv');value['volume_available']=False;value['observed_at']=None
    context=validate_market_context(value,symbol='ETH')
    assert context['statistics']['sample_volume'] is None
    assert context['source_age_seconds'] is None
    value=packet()
    for row in value['bars']:row['time']-=86400
    context=validate_market_context(value,symbol='ETH')
    assert context['bars_stale'] is True and context['stale'] is True


def test_chat_persists_both_materials_and_binds_market_identity(db,isolated_store,monkeypatch):
    seed_chat_news(db);service=HumanControlService(db);configure_chat(service)
    captured={}
    class Provider:
        def generate_report(self,**kwargs):
            captured.update(kwargs);value=report_for(kwargs)
            value['summary']='Source claim [N1], raw price sample [M1].'
            value['evidence']={'news_citation_ids':['N1'],'market_citation_ids':['M1']}
            return json.dumps(value)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:Provider())
    value=service.research_chat(actor=owner(),payload={'question':'Review supplied data','page':'market','symbol':'ETH','include_news':True,'market_context':packet()})
    assert value['status']=='ok'
    assert value['cited_market_ids']==['M1']
    assert value['context_scope']=='question_history_workspace_news_and_market_snapshots'
    market=db.get(DataSnapshot,value['market_context_snapshot_id'])
    assert market.user_id=='owner-user'
    assert market.id==captured['data_snapshot_id']
    assert market.data_json['bars']==value['provided_market']['bars']
    assert market.metadata_json['news_context_snapshot_id']==value['news_context_snapshot_id']
    assert DataSourceService(db).list_snapshots(snapshot_type='research_chat_market_context')==[]
    assert service.research_market_snapshot(actor=owner(),snapshot_id=market.id)['provided_market']['symbol']=='ETH'
    with pytest.raises(HumanControlError):service.research_market_snapshot(actor=owner('other'),snapshot_id=market.id)


def test_bad_market_packet_stops_before_preflight_or_provider(db,isolated_store,monkeypatch):
    service=HumanControlService(db);configure_chat(service)
    def unexpected(*args,**kwargs):raise AssertionError('invalid material must not call model')
    monkeypatch.setattr(service,'llm_preflight_dry_run',unexpected)
    value=packet();value['symbol']='BTC'
    result=service.research_chat(actor=owner(),payload={'question':'Question','symbol':'ETH','market_context':value})
    assert result['status']=='blocked' and result['external_call_attempted'] is False
    assert result['reason']=='ai_market_identity_mismatch'
