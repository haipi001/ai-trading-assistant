"""Probe real HTTP research routes on the isolated controlled UI fixture only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

parser=argparse.ArgumentParser()
parser.add_argument('--base-url',default='http://127.0.0.1:8001')
parser.add_argument('--control-file',required=True)
parser.add_argument('--output',required=True)
a=parser.parse_args()
base=a.base_url.rstrip('/')
parsed=urlsplit(base)
if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
    raise SystemExit('Use a loopback-only controlled fixture URL')
control=Path(a.control_file).resolve()
if not control.is_relative_to(Path('/tmp').resolve()) or not control.is_file():
    raise SystemExit('Use the existing temporary fixture control file')

def request(path,body=None):
    raw=json.dumps(body).encode() if body is not None else None
    req=Request(base+path,data=raw,headers={'Content-Type':'application/json'},method='POST' if raw is not None else 'GET')
    try:
        with urlopen(req,timeout=20) as response:
            return response.status,json.loads(response.read())
    except HTTPError as error:
        return error.code,json.loads(error.read())

code,schema=request('/openapi.json')
assert code==200 and schema['info']['title']=='Controlled Web3 fixture: no network, no execution routes','Not the isolated fixture'
assert '/orders/intents' not in schema['paths']
for path in ('/orders/intents','/paper-executions/drafts/example/execute','/live-execution/execute'):
    assert request(path,{})[0]==404,(path,'must not expose execution')

prefix='/production/human-control/llm/chat'
artifacts=[]
checks=[]

def material(market):
    return {'schema':1,'origin':'browser_chart','data_semantics':'raw_ohlcv','kind':'csv','market_type':market,'symbol':'AAPL' if market=='stock' else 'ETH','venue':'Controlled NASDAQ' if market=='stock' else 'Controlled CEX','quote_currency':'USD' if market=='stock' else 'USDT','timeframe':'1m','source_label':'Controlled acceptance OHLCV; synthetic, not live prices','observed_at':None,'captured_at':datetime.now(timezone.utc).isoformat(),'volume_available':True,'replay_cutoff':None,'bars':[{'time':100+i*60,'open':10,'high':12,'low':9,'close':11,'volume':2} for i in range(3)]}

def payload(market):
    chart=material(market)
    return {'question':'Controlled acceptance: describe the selected historical sample only.','page':'market','symbol':chart['symbol'],'market_context':chart}

def recover(result,market):
    assert result['execution_available'] is False
    identifier=result['market_context_snapshot_id']
    code,listing=request(prefix+'/market-contexts?'+urlencode({'symbol':'AAPL' if market=='stock' else 'ETH','market_type':market}))
    assert code==200 and listing['execution_available'] is False
    row=next(item for item in listing['items'] if item['snapshot_id']==identifier)
    code,artifact=request(prefix+'/market-context/'+identifier)
    assert code==200 and artifact['execution_available'] is False
    assert artifact['provided_market']==result['provided_market']
    assert artifact['provided_market']['source_verified'] is False
    assert artifact['reply_status']==result['status']
    if result['status']=='ok':
        assert artifact['validated_reply']['summary']==result['summary']
        assert artifact['validated_reply']['cited_market_ids']==['M1']
    else:assert artifact['validated_reply'] is None
    artifacts.append({'row':row,'artifact':artifact})
    return identifier

try:
    for market in ('stock','spot'):
        for mode in ('ok','ai-fail','ai-invalid'):
            control.write_text(mode)
            code,result=request(prefix,payload(market))
            assert code==200 and result['status']==('ok' if mode=='ok' else 'failed'),result
            recover(result,market)
            checks.append(market+':'+mode+':persist_and_recover')
    control.write_text('ai-delay')
    body=payload('spot')
    code,before=request(prefix+'/market-contexts?'+urlencode({'symbol':'ETH','market_type':'spot'}))
    assert code==200
    old={item['snapshot_id'] for item in before['items']}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(request,prefix,body)
        pending=None
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            code,listing=request(prefix+'/market-contexts?symbol=ETH&market_type=spot')
            pending=next((item for item in listing['items'] if item['snapshot_id'] not in old),None)
            if pending:break
            time.sleep(.1)
        assert pending and pending['reply_status'] is None,'Frozen material must exist before the response completes'
        code,unfinished=request(prefix+'/market-context/'+pending['snapshot_id'])
        assert code==200 and unfinished['validated_reply'] is None
        code,stocks=request(prefix+'/market-contexts?symbol=AAPL&market_type=stock')
        assert code==200 and pending['snapshot_id'] not in {item['snapshot_id'] for item in stocks['items']}
        code,result=future.result(timeout=20)
        assert code==200 and result['status']=='ok'
        assert recover(result,'spot')==pending['snapshot_id']
    checks.append('pending_source_frozen_before_reply_and_keeps_original_market')
    checks.append('execution_routes_absent')
    output=Path(a.output)
    output.write_text(json.dumps({'status':'passed','fixture':'controlled local Provider; synthetic CSV; no external model','checks':checks,'artifacts':artifacts,'external_model_called':False,'execution_routes_available':False},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'passed','checks':checks,'artifacts':len(artifacts),'output':str(output)},ensure_ascii=False))
finally:
    control.write_text('ok')
