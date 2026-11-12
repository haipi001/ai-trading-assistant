"""Owned ledger/AI/history checks against the explicitly isolated local fixture."""
import argparse,json,sqlite3,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError
p=argparse.ArgumentParser();p.add_argument('--base-url',default='http://127.0.0.1:8001');p.add_argument('--control-file',required=True);p.add_argument('--database',required=True);p.add_argument('--output',required=True);a=p.parse_args()
base=a.base_url.rstrip('/');url=urlsplit(base);control=Path(a.control_file).resolve();database=Path(a.database).resolve()
if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost') or url.username or url.password or url.path or url.query or url.fragment:raise SystemExit('Use loopback fixture only')
if not all(path.is_relative_to(Path('/tmp').resolve()) and path.is_file() for path in (control,database)):raise SystemExit('Use existing isolated fixture files under /tmp')
def request(path,body=None):
    raw=json.dumps(body).encode() if body is not None else None
    try:
        with urlopen(Request(base+path,data=raw,headers={'Content-Type':'application/json'},method='POST' if raw is not None else 'GET'),timeout=25) as r:return r.status,json.loads(r.read())
    except HTTPError as e:return e.code,json.loads(e.read())
code,schema=request('/openapi.json');assert code==200 and schema['info']['title']=='Controlled Web3 fixture: no network, no execution routes'
assert '/orders/intents' not in schema['paths']
with sqlite3.connect(database) as db:
    names=[row[0] for row in db.execute("select name from accounts where id in ('fixture-stocks-ledger','fixture-cex-ledger')")]
    assert len(names)==2 and all('非真实账户' in name for name in names),'Not the controlled ledger database'
basepath='/production/human-control/llm/chat';artifacts=[];checks=[]
def prepare(market,version):
    code,value=request(basepath+'/portfolio-context/prepare',{'account_id':'fixture-'+market+'-ledger','market':market,'context_version':version});assert code==200,value
    assert value['execution_available'] is False
    return value

def recover(result,market):
    code,listing=request(basepath+'/portfolio-contexts?'+urlencode({'account_id':'fixture-'+market+'-ledger','market':market}));assert code==200
    row=next(row for row in listing['items'] if row['snapshot_id']==result['portfolio_context_snapshot_id'])
    code,value=request(basepath+'/portfolio-context/'+row['snapshot_id']);assert code==200,value
    assert value['provided_portfolio']==result['provided_portfolio'] and value['execution_available'] is False
    assert value['provided_portfolio']['valuation_freshness']=='unknown'
    if result['status']=='ok':assert value['validated_reply']['cited_portfolio_ids']==['H1','H2']
    else:assert value['validated_reply'] is None
    artifacts.append({'row':row,'artifact':value});return value
original=None
try:
    for market in ('stocks','cex'):
        source=prepare(market,42)
        for mode in ('ok','ai-fail','ai-invalid'):
            control.write_text(mode)
            code,result=request(basepath,{'question':'Controlled account-ledger review, not live balances.','page':'assets','portfolio_context':source['reference']})
            assert code==200 and result['status']==('ok' if mode=='ok' else 'failed'),result
            recover(result,market);checks.append(market+':'+mode+':persist_restore')
    source=prepare('stocks',43);control.write_text('ai-delay')
    query='/portfolio-contexts?account_id=fixture-stocks-ledger&market=stocks'
    _,before=request(basepath+query);old={row['snapshot_id'] for row in before['items']}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(request,basepath,{'question':'Controlled delayed ledger snapshot','page':'assets','portfolio_context':source['reference']})
        pending=None;deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            _,listing=request(basepath+query);pending=next((row for row in listing['items'] if row['snapshot_id'] not in old),None)
            if pending:break
            time.sleep(.1)
        assert pending and pending['reply_status'] is None
        with sqlite3.connect(database) as db:
            original=db.execute("select quantity from positions where id='fixture-position-stocks'").fetchone()[0]
            db.execute("update positions set quantity=2.5,updated_at=? where id='fixture-position-stocks'",(datetime.now(timezone.utc).isoformat(),));db.commit()
        code,result=future.result(timeout=25);assert code==200 and result['status']=='ok',result
        history=recover(result,'stocks')
        assert history['provided_portfolio']['entries'][1]['quantity']==source['provided_portfolio']['entries'][1]['quantity']
        assert history['snapshot_id']==pending['snapshot_id']
    control.write_text('ok')
    code,blocked=request(basepath,{'question':'Old ledger must not be reused','portfolio_context':source['reference']})
    assert code==200 and blocked['status']=='blocked' and blocked['reason']=='ai_portfolio_changed' and blocked['external_call_attempted'] is False
    checks.append('delayed_reply_keeps_original_ledger_and_changed_source_cannot_be_reused')
    fresh=prepare('stocks',44);assert fresh['provided_portfolio']['entries'][1]['quantity']=='2.5'
    for path in ('/orders/intents','/live-execution/execute'):
        assert request(path,{})[0]==404
    with sqlite3.connect(database) as db:
        counts={table:db.execute('select count(*) from '+table).fetchone()[0] for table in ['order_intents','order_drafts','executions']}
    assert all(value==0 for value in counts.values())
    Path(a.output).write_text(json.dumps({'status':'passed','fixture':'controlled Provider and ledger records; no external model or live balances','checks':checks,'artifacts':artifacts,'zero_execution_checks':counts,'external_model_called':False},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'passed','artifacts':len(artifacts),'checks':checks,'zero_execution_checks':counts}))
finally:
    control.write_text('ok')
    if original is not None:
        with sqlite3.connect(database) as db:db.execute("update positions set quantity=?,updated_at=? where id='fixture-position-stocks'",(original,datetime.now(timezone.utc).isoformat()));db.commit()
