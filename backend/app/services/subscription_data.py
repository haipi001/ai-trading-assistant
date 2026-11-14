"""Normalize subscription responses into explicit, bounded display records."""
import math
from datetime import datetime, timezone
from app.services.news_feed import normalize_articles

DEFAULT_MAPPING = {'root':'','symbol':'symbol','price':'price','change':'change','volume':'volume','timestamp':'timestamp','timestamp_unit':'iso','currency':'USD','market':'crypto','venue':'custom','symbol_value':''}


def field(value, path):
    for key in path.split('.') if path else []:
        if isinstance(value, dict): value=value.get(key)
        elif isinstance(value,list) and key.isdigit() and int(key)<len(value): value=value[int(key)]
        else: return None
    return value


def number(value, positive=False):
    if isinstance(value,bool): return None
    try: value=float(value)
    except (ValueError,TypeError,OverflowError): return None
    return value if math.isfinite(value) and (not positive or value>0) else None


def instant(value, unit):
    try:
        if unit=='iso':
            result=datetime.fromisoformat(value.replace('Z','+00:00'))
            if result.tzinfo is None:return None
        else:
            timestamp=number(value)
            if timestamp is None:return None
            result=datetime.fromtimestamp(timestamp/(1000 if unit=='ms' else 1),timezone.utc)
        if result.timestamp()>datetime.now(timezone.utc).timestamp()+300:return None
        return result.astimezone(timezone.utc).isoformat()
    except (ValueError,TypeError,AttributeError,OverflowError,OSError): return None


def normalize(config, payload):
    if config['kind']=='rss':
        articles=normalize_articles(payload.get('articles',[]),'custom')
        for row in articles:
            row.update(source_id=config['id'],publisher=config['name'],kind=config.get('news_kind','article'))
        return {'items':len(articles),'format':'rss','articles':articles}
    mapping={**DEFAULT_MAPPING,**config.get('mapping',{})}
    rows=field(payload,mapping['root'])
    if isinstance(rows,dict):rows=[rows]
    if not isinstance(rows,list):raise ValueError('JSON 根路径应指向对象或数组')
    quotes=[]
    for row in rows[:200]:
        price=number(field(row,mapping['price']),True)
        symbol=field(row,mapping['symbol']) or mapping['symbol_value']
        if price is None or not isinstance(symbol,str) or not symbol.strip():continue
        quotes.append({'symbol':symbol.strip().upper()[:40],'price':price,'change':number(field(row,mapping['change'])),'volume':number(field(row,mapping['volume'])),'timestamp':instant(field(row,mapping['timestamp']),mapping['timestamp_unit']),'currency':mapping['currency'],'market':mapping['market'],'venue':mapping['venue'],'source_id':config['id'],'publisher':config['name']})
    if rows and not quotes:raise ValueError('没有可用报价，请配置字段映射')
    return {'items':len(quotes),'format':'json','quotes':quotes}
