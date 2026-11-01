"""Validate an explicit browser-provided raw chart snapshot; never certify its source."""
import hashlib
import json
import math
import re
from datetime import datetime, timezone, timedelta

class MarketContextError(ValueError):
    pass


def _instant(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else None
        if result is None or result.tzinfo is None:raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError):
        raise MarketContextError('ai_market_invalid') from None


def _close_time(stamp,timeframe):
    amount,unit=re.fullmatch(r'([1-9]\d{0,3})(s|m|h|d|wk|mo|y)',timeframe).groups()
    amount=int(amount)
    if unit not in {'mo','y'}:
        seconds=amount*{'s':1,'m':60,'h':3600,'d':86400,'wk':604800}[unit]
        anchor=345600 if unit=='wk' else 0
        return math.floor((stamp-anchor)/seconds)*seconds+anchor+seconds
    date=datetime.fromtimestamp(stamp,timezone.utc)
    months=amount*(12 if unit=='y' else 1)
    month=date.year*12+date.month-1
    year,index=divmod((month//months+1)*months,12)
    return datetime(year,index+1,1,tzinfo=timezone.utc).timestamp()



def validate_market_context(raw, *, symbol, now=None):
    now=now or datetime.now(timezone.utc)
    allowed={'schema','origin','data_semantics','kind','market_type','symbol','venue','quote_currency','timeframe','source_label','observed_at','captured_at','replay_cutoff','volume_available','bars'}
    if not isinstance(raw,dict) or set(raw)!=allowed or (type(raw['schema']) is not int or raw['schema']!=1) or raw['origin']!='browser_chart' or raw['data_semantics']!='raw_ohlcv' or raw['kind'] not in ('online','csv','replay') or raw['market_type'] not in ('spot','stock'):
        raise MarketContextError('ai_market_invalid')
    if raw['symbol']!=symbol or not isinstance(symbol,str) or not re.fullmatch(r'[A-Za-z0-9.^_-]{1,24}',symbol) or raw['quote_currency'] not in ('USDT','USD'):
        raise MarketContextError('ai_market_identity_mismatch')
    if (raw['market_type']=='spot')!=(raw['quote_currency']=='USDT'):
        raise MarketContextError('ai_market_identity_mismatch')
    for name,maximum in [('venue',50),('source_label',300)]:
        if not isinstance(raw[name],str) or not 1<=len(raw[name])<=maximum or any(ord(char)<32 for char in raw[name]):raise MarketContextError('ai_market_invalid')
    if re.search(r'demo|mock|seed|演示|模拟',raw['source_label'],re.I):raise MarketContextError('ai_market_demo_rejected')
    if not isinstance(raw['timeframe'],str) or not re.fullmatch(r'[1-9]\d{0,3}(s|m|h|d|wk|mo|y)',raw['timeframe']):raise MarketContextError('ai_market_invalid')
    captured=_instant(raw['captured_at'])
    observed=_instant(raw['observed_at']) if raw['observed_at'] is not None else None
    if captured>now+timedelta(minutes=5) or observed and observed>captured+timedelta(minutes=5):raise MarketContextError('ai_market_invalid')
    if type(raw['volume_available']) is not bool:raise MarketContextError('ai_market_invalid')
    cutoff=raw['replay_cutoff']
    if raw['kind']=='replay':
        if type(cutoff) not in (int,float) or not math.isfinite(cutoff) or cutoff<0:raise MarketContextError('ai_market_invalid')
    elif cutoff is not None:raise MarketContextError('ai_market_invalid')
    rows=raw['bars']
    if not isinstance(rows,list) or not 1<=len(rows)<=240:raise MarketContextError('ai_market_invalid')
    bars=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'time','open','high','low','close','volume'} or type(row['time']) is not int or not 0<=row['time']<=253402300799 or bars and row['time']<=bars[-1]['time']:raise MarketContextError('ai_market_invalid')
        for key in ('open','high','low','close','volume'):
            try:
                if type(row[key]) not in (int,float) or not math.isfinite(float(row[key])) or row[key]<(0 if key=='volume' else 1e-300):raise MarketContextError('ai_market_invalid')
            except OverflowError:raise MarketContextError('ai_market_invalid') from None
        if row['low']>min(row['open'],row['close']) or row['high']<max(row['open'],row['close']) or row['low']>row['high']:raise MarketContextError('ai_market_invalid')
        if raw['kind']=='online' and row['time']>captured.timestamp()+1:raise MarketContextError('ai_market_invalid')
        if raw['kind']=='replay':
            try:
                close_time=_close_time(row['time'],raw['timeframe'])
            except (ValueError,OverflowError):raise MarketContextError('ai_market_invalid') from None
            if close_time>cutoff:raise MarketContextError('ai_market_future_rejected')
        bars.append(dict(row))
    try:
        stats={'first_open':bars[0]['open'],'last_close':bars[-1]['close'],'sample_high':max(row['high'] for row in bars),'sample_low':min(row['low'] for row in bars),'sample_change_pct':(bars[-1]['close']/bars[0]['open']-1)*100,'sample_volume':sum(row['volume'] for row in bars) if raw['volume_available'] else None}
        if any(value is not None and not math.isfinite(value) for value in stats.values()):raise MarketContextError('ai_market_invalid')
    except (OverflowError,ZeroDivisionError):raise MarketContextError('ai_market_invalid') from None
    try:
        last_end=_close_time(bars[-1]['time'],raw['timeframe'])
    except (ValueError,OverflowError):last_end=None
    bars_stale=raw['kind']=='online' and (last_end is None or now.timestamp()>last_end+120)
    result={**raw,'bars':bars,'statistics':stats,'volume_unit':'source_raw','received_at':now.isoformat(),'source_age_seconds':max(0,(now-observed).total_seconds()) if observed else None,'last_bar_period_end':last_end,'bars_stale':bars_stale,'stale':bars_stale or observed is None or (now-observed).total_seconds()>120,'source_verified':False,'limitations':'Browser-provided raw OHLCV, structurally validated but not independently retrieved/verified by this server. Only the primary chart and supplied sample are included, not all panes, chart transformations, indicators, drawings, current account positions or order flow. Capture/receive time does not establish quote freshness. CSV/exchange labels are user chart labels; replay is historical only. When volume_available is false, volume zeroes are placeholders and must not be analyzed.'}
    result['content_hash']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    return result


def validate_market_citations(report, context):
    ids=report.evidence.get('market_citation_ids',[])
    if not isinstance(ids,list) or len(ids)>1 or any(value!='M1' for value in ids):raise MarketContextError('ai_market_citation_invalid')
    referenced=set(re.findall(r'\[(M\d+)\]','\n'.join([report.summary,report.bullish_case,report.bearish_case,*report.key_risks,report.limitations,report.suggested_action])))
    if (ids or referenced) and (not context or set(ids)!=referenced):raise MarketContextError('ai_market_citation_invalid')
    return list(dict.fromkeys(ids))
