"""User-owned, read-only RSS/JSON subscriptions. Credentials never leave the secret store."""
import hashlib
import http.client
import ipaddress
import json
import os
import socket
import ssl
import certifi
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlencode
from sqlalchemy import select
from app.models import LocalUserConfig, AuditLog
from app.core.local_secrets import set_user_secret, delete_user_secret
from app.services.news_feed import parse_public_rss, _refresh_lock
from app.services.subscription_data import normalize, DEFAULT_MAPPING
import uuid


def validate_endpoint(value):
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or p.query or p.port not in (None, 443):
        raise ValueError('地址须为 HTTPS，不含账号、查询参数或片段；参数请在独立字段填写')
    return p


def fetch_subscription(config, secret):
    p = validate_endpoint(config['url'])
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('仅支持公网来源')
    # Pin the validated address; preserve TLS hostname verification and never follow redirects.
    connection = http.client.HTTPSConnection(p.hostname, timeout=12)
    raw = socket.create_connection((addresses[0][4][0], 443), timeout=12)
    try:
        connection.sock = ssl.create_default_context(cafile=certifi.where()).wrap_socket(raw, server_hostname=p.hostname)
        headers = {'Accept': 'application/rss+xml, application/atom+xml, application/json', 'User-Agent': 'Trading-Research/1.0'}
        if config['auth'] != 'none':
            if not secret:
                raise ValueError('尚未配置凭证')
            headers[config['header_name']] = ('Bearer ' if config['auth'] == 'bearer' else '') + secret
        path = (p.path or '/') + ('?' + urlencode(config['params']) if config['params'] else '')
        connection.request('GET', path, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('来源未返回成功状态')
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('响应超过 2MB')
        if config['kind'] == 'rss':
            # Existing parser strips markup and rejects XML entities.
            result = parse_public_rss(body, config['name'])
            return normalize(config, result)
        data = json.loads(body)
        return normalize(config, data)
    finally:
        connection.close()
        raw.close()


class SubscriptionService:
    def __init__(self, db, user_id):
        self.db, self.user_id = db, user_id

    def row(self, identifier):
        return self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == self.user_id, LocalUserConfig.config_key == 'subscription:' + identifier))

    def secret_name(self, identifier):
        return 'SUB_' + hashlib.sha256((self.user_id + ':' + identifier).encode()).hexdigest()[:48].upper()

    def view(self, row, include_data=False):
        value = dict(row.value_json)
        if not include_data and 'result' in value:
            value['result']={k:v for k,v in value['result'].items() if k not in ('articles','quotes')}
        value['key_configured'] = bool(os.environ.get(self.secret_name(value['id'])))
        return value

    def list(self):
        return [self.view(row) for row in self.db.scalars(select(LocalUserConfig).where(LocalUserConfig.user_id == self.user_id, LocalUserConfig.config_key.like('subscription:%')))]

    def save(self, identifier, payload):
        import re
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', identifier):
            raise ValueError('订阅 ID 无效')
        if set(payload) - {'name','url','kind','auth','header_name','params','api_key','enabled','refresh_seconds','clear_key','mapping','news_kind'}:
            raise ValueError('存在不支持的字段')
        validate_endpoint(payload.get('url', ''))
        name = payload.get('name', '').strip()
        if not name or len(name) > 80 or payload.get('kind') not in ('rss','json') or payload.get('auth') not in ('none','bearer','header'):
            raise ValueError('名称、格式或认证方式无效')
        header = payload.get('header_name', 'Authorization')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,63}', header) or header.lower() in ('host','cookie','connection','content-length','transfer-encoding','proxy-authorization'):
            raise ValueError('认证 Header 名无效')
        params = payload.get('params', {})
        if not isinstance(params, dict) or len(params) > 20 or any(not isinstance(k,str) or not isinstance(v,str) or len(k)>80 or len(v)>500 for k,v in params.items()):
            raise ValueError('参数须为最多20项的字符串对象')
        if any(re.search(r'key|token|secret|password|credential', k, re.I) for k in params):
            raise ValueError('凭证请填写专用字段，勿放入参数')
        interval = payload.get('refresh_seconds', 300)
        if type(interval) is not int or not (15 if payload.get('kind') == 'json' else 60) <= interval <= 86400 or type(payload.get('enabled', True)) is not bool:
            raise ValueError('RSS刷新间隔须为60–86400秒，JSON最短15秒')
        mapping = payload.get('mapping', {})
        if not isinstance(mapping,dict) or set(mapping)-set(DEFAULT_MAPPING) or any(not isinstance(v,str) or len(v)>120 for v in mapping.values()):
            raise ValueError('字段映射无效')
        mapping = {**DEFAULT_MAPPING,**mapping}
        if mapping['timestamp_unit'] not in ('iso','s','ms') or mapping['market'] not in ('crypto','stocks','forex','other') or payload.get('news_kind','article') not in ('article','flash'):
            raise ValueError('来源类别或时间单位无效')
        row = self.row(identifier)
        value = {k: payload[k] for k in ('name','url','kind','auth')}
        value.update(id=identifier, name=name, header_name=header, params=params, enabled=payload.get('enabled', True), refresh_seconds=interval, status='untested', scheduling='while_page_visible', mapping=mapping, news_kind=payload.get('news_kind','article'), revision=uuid.uuid4().hex)
        key = payload.get('api_key', '')
        if not isinstance(key,str) or len(key)>4096 or '\r' in key or '\n' in key:
            raise ValueError('凭证格式无效')
        if payload.get('clear_key') is True:
            if key: raise ValueError('不能同时清除和更新凭证')
            delete_user_secret(self.secret_name(identifier))
        if key:
            set_user_secret(self.secret_name(identifier), key)
        if row is None:
            if len(self.list()) >= 50:
                raise ValueError('最多50条订阅')
            row = LocalUserConfig(user_id=self.user_id,config_key='subscription:'+identifier,value_json=value)
            self.db.add(row)
        else:
            row.value_json = value
        self.audit(identifier, 'save')
        self.db.commit()
        return self.view(row)

    def audit(self, identifier, action):
        self.db.add(AuditLog(user_id=self.user_id, actor_type='user', actor_id=self.user_id, action='subscription.'+action, entity_type='Subscription',entity_id=identifier,payload_json={'read_only':True}))

    def feed(self, target):
        rows = self.db.scalars(select(LocalUserConfig).where(LocalUserConfig.user_id == self.user_id, LocalUserConfig.config_key.like('subscription:%'))).all()
        return [self.view(row, True) for row in rows if row.value_json.get('enabled') and row.value_json.get('kind') == ('rss' if target == 'news' else 'json')]

    def test(self, identifier):
        return self.refresh(identifier, manual=True)

    def refresh(self, identifier, manual=False):
        lock = _refresh_lock('subscription:'+self.user_id+':'+identifier)
        with lock:
            row = self.row(identifier)
            if not row or not row.value_json.get('enabled'):
                raise ValueError('订阅不存在或已停用')
            self.db.refresh(row)
            value = dict(row.value_json)
            previous = value.get('checked_at')
            if previous:
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(previous)).total_seconds()
                if age < (min(value['refresh_seconds'], 15) if manual else value['refresh_seconds']):
                    return self.view(row, True)
            revision = value.get('revision')
            value['checked_at'] = datetime.now(timezone.utc).isoformat()
            try:
                result = fetch_subscription(value, os.environ.get(self.secret_name(identifier)))
                value.update(status='ready', result=result, fetched_at=datetime.now(timezone.utc).isoformat())
                value.pop('last_error',None)
            except Exception:
                value.update(status='error',last_error='读取失败，请核对地址、字段映射、凭证和网络')
            self.db.refresh(row)
            if row.value_json.get('revision') != revision:
                return self.view(row, True)
            row.value_json = value
            if manual:self.audit(identifier, 'test')
            self.db.commit()
            return self.view(row, True)
