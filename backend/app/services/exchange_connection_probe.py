"""Live read-only credential verification. No persistence, trading or arbitrary URLs."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
import ssl
import certifi


class ExchangeProbeError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

class NoCredentialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExchangeProbeError('exchange_redirect_rejected')

def open_probe_url(request, *, timeout):
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())), NoCredentialRedirect())
    return opener.open(request, timeout=timeout)

DANGEROUS_FLAGS = ('enableWithdrawals', 'enableInternalTransfer', 'permitsUniversalTransfer', 'enableSpotAndMarginTrading', 'enableMargin', 'enableFutures', 'enableVanillaOptions', 'enableFixApiTrade', 'enablePortfolioMarginTrading')

class BinanceConnectionProbe:
    def __init__(self, transport=None):
        self.transport = transport or open_probe_url

    def _get(self, path, key=None, secret=None, timestamp=None):
        if path not in ('/api/v3/time', '/sapi/v1/account/apiRestrictions', '/api/v3/account'):
            raise ExchangeProbeError('unsupported_endpoint')
        query = ''
        headers = {'User-Agent': 'ai-trading-readonly-probe'}
        if key is not None:
            query = urlencode({'timestamp': timestamp, 'recvWindow': 5000})
            signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            query += '&signature=' + signature
            headers['X-MBX-APIKEY'] = key
        request = Request('https://api.binance.com' + path + ('?' + query if query else ''), headers=headers, method='GET')
        try:
            with self.transport(request, timeout=8) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ExchangeProbeError('response_too_large')
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ExchangeProbeError('invalid_exchange_response')
            return payload
        except HTTPError as exc:
            # Never reflect exchange error text or exception URLs containing signatures.
            code = 'exchange_request_rejected'
            if exc.code in (401, 403): code = 'key_ip_or_permissions_rejected'
            if exc.code in (418, 429): code = 'exchange_rate_limited'
            raise ExchangeProbeError(code) from None
        except (URLError, TimeoutError, OSError):
            raise ExchangeProbeError('exchange_network_unavailable') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ExchangeProbeError('invalid_exchange_response') from None

    def verify(self, key, secret):
        if not all(isinstance(value, str) and 8 <= len(value) <= 512 and not any(c.isspace() for c in value) for value in (key, secret)):
            raise ExchangeProbeError('invalid_credentials_format')
        clock = self._get('/api/v3/time').get('serverTime')
        if type(clock) is not int or clock <= 0:
            raise ExchangeProbeError('invalid_server_time')
        permissions = self._get('/sapi/v1/account/apiRestrictions', key, secret, clock)
        if permissions.get('enableReading') is not True:
            raise ExchangeProbeError('reading_permission_missing')
        if permissions.get('enableWithdrawals') is not False:
            raise ExchangeProbeError('withdrawal_permission_not_disabled')
        if any(permissions.get(flag) is not False for flag in ('enableSpotAndMarginTrading', 'enableFutures', 'enableInternalTransfer', 'permitsUniversalTransfer')):
            raise ExchangeProbeError('readonly_permissions_incomplete_or_enabled')
        if any(permissions.get(flag) is not None and permissions.get(flag) is not False for flag in DANGEROUS_FLAGS):
            raise ExchangeProbeError('readonly_key_required')
        clock = self._get('/api/v3/time').get('serverTime')
        if type(clock) is not int or clock <= 0:
            raise ExchangeProbeError('invalid_server_time')
        account = self._get('/api/v3/account', key, secret, clock)
        rows = account.get('balances')
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ExchangeProbeError('invalid_account_balances')
        balances = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('asset'), str) or not row['asset'].isalnum() or len(row['asset']) > 32:
                raise ExchangeProbeError('invalid_account_balances')
            try:
                free, locked = Decimal(str(row['free'])), Decimal(str(row['locked']))
                if not all(x.is_finite() and x >= 0 for x in (free, locked)):
                    raise InvalidOperation
            except (KeyError, InvalidOperation, ValueError):
                raise ExchangeProbeError('invalid_account_balances') from None
            if free or locked:
                balances.append({'asset': row['asset'], 'free': str(free), 'locked': str(locked)})
        return {'exchange': 'binance', 'status': 'verified_readonly', 'checked_at': datetime.now(timezone.utc).isoformat(), 'permissions': {'reading': True, 'trading': False, 'transfers': False, 'withdrawals': False}, 'balances': balances, 'credentials_persisted': False, 'order_submission_available': False}

class OkxConnectionProbe(BinanceConnectionProbe):
    """OKX global-region account config + trading balance, read-only permission only."""
    def _get_okx(self,path,key=None,secret=None,passphrase=None,timestamp=None):
        import base64
        if path not in ('/api/v5/public/time','/api/v5/account/config','/api/v5/account/balance'):
            raise ExchangeProbeError('unsupported_endpoint')
        headers={'User-Agent':'ai-trading-readonly-probe'}
        if key is not None:
            prehash=timestamp+'GET'+path
            signature=base64.b64encode(hmac.new(secret.encode(),prehash.encode(),hashlib.sha256).digest()).decode()
            headers.update({'OK-ACCESS-KEY':key,'OK-ACCESS-SIGN':signature,'OK-ACCESS-TIMESTAMP':timestamp,'OK-ACCESS-PASSPHRASE':passphrase})
        request=Request('https://www.okx.com'+path,headers=headers,method='GET')
        try:
            with self.transport(request,timeout=8) as response:raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ExchangeProbeError('response_too_large')
            value=json.loads(raw)
            if not isinstance(value,dict) or value.get('code')!='0':
                code=value.get('code') if isinstance(value,dict) else None
                raise ExchangeProbeError('key_ip_or_permissions_rejected' if code in ('50111','50113','50114','50119','50105') else 'exchange_request_rejected')
            rows=value.get('data')
            if not isinstance(rows,list):raise ExchangeProbeError('invalid_exchange_response')
            return rows
        except HTTPError as exc:
            raise ExchangeProbeError('exchange_rate_limited' if exc.code in (418,429) else 'exchange_request_rejected') from None
        except (URLError,TimeoutError,OSError):raise ExchangeProbeError('exchange_network_unavailable') from None
        except (json.JSONDecodeError,UnicodeDecodeError):raise ExchangeProbeError('invalid_exchange_response') from None

    def _timestamp(self):
        rows=self._get_okx('/api/v5/public/time')
        try:
            if len(rows)!=1 or not isinstance(rows[0],dict):raise ValueError()
            milliseconds=int(rows[0]['ts'])
            if milliseconds<=0:raise ValueError()
            return datetime.fromtimestamp(milliseconds/1000,timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
        except (KeyError,ValueError,TypeError,OverflowError):raise ExchangeProbeError('invalid_server_time') from None

    def verify(self,key,secret,passphrase):
        if not all(isinstance(x,str) and x.isascii() and 8<=len(x)<=512 and not any(c.isspace() for c in x) for x in (key,secret)):
            raise ExchangeProbeError('invalid_credentials_format')
        if not isinstance(passphrase,str) or not 1<=len(passphrase)<=128 or not passphrase.isascii() or any(ord(c)<32 or ord(c)==127 for c in passphrase):
            raise ExchangeProbeError('invalid_passphrase')
        config=self._get_okx('/api/v5/account/config',key,secret,passphrase,self._timestamp())
        if len(config)!=1 or not isinstance(config[0],dict) or not isinstance(config[0].get('perm'),str):
            raise ExchangeProbeError('readonly_permissions_incomplete_or_enabled')
        if {x.strip() for x in config[0]['perm'].split(',')}!={'read_only'}:
            raise ExchangeProbeError('readonly_key_required')
        accounts=self._get_okx('/api/v5/account/balance',key,secret,passphrase,self._timestamp())
        if len(accounts)!=1 or not isinstance(accounts[0],dict) or not isinstance(accounts[0].get('details'),list) or len(accounts[0]['details'])>10000:
            raise ExchangeProbeError('invalid_account_balances')
        balances=[]
        for row in accounts[0]['details']:
            if not isinstance(row,dict) or not isinstance(row.get('ccy'),str) or not row['ccy'].isalnum() or len(row['ccy'])>32:
                raise ExchangeProbeError('invalid_account_balances')
            try:
                free,locked=Decimal(str(row['availBal'])),Decimal(str(row['frozenBal']))
                if not free.is_finite() or not locked.is_finite() or locked<0:raise InvalidOperation
            except (KeyError,InvalidOperation,ValueError):raise ExchangeProbeError('invalid_account_balances') from None
            if free or locked:balances.append({'asset':row['ccy'],'free':str(free),'locked':str(locked)})
        return {'exchange':'okx','status':'verified_readonly','checked_at':datetime.now(timezone.utc).isoformat(),'permissions':{'reading':True,'trading':False,'transfers':False,'withdrawals':False},'balances':balances,'balance_scope':'trading_account','credentials_persisted':False,'order_submission_available':False}

class BybitConnectionProbe(BinanceConnectionProbe):
    def _get_bybit(self,path,key=None,secret=None,timestamp=None,query=''):
        if path not in ('/v5/market/time','/v5/user/query-api','/v5/account/wallet-balance'):
            raise ExchangeProbeError('unsupported_endpoint')
        headers={'User-Agent':'ai-trading-readonly-probe'}
        if key is not None:
            signature=hmac.new(secret.encode(),(str(timestamp)+key+'5000'+query).encode(),hashlib.sha256).hexdigest()
            headers.update({'X-BAPI-API-KEY':key,'X-BAPI-TIMESTAMP':str(timestamp),'X-BAPI-RECV-WINDOW':'5000','X-BAPI-SIGN':signature})
        request=Request('https://api.bybit.com'+path+('?' + query if query else ''),headers=headers,method='GET')
        try:
            with self.transport(request,timeout=8) as response:raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ExchangeProbeError('response_too_large')
            value=json.loads(raw)
            if not isinstance(value,dict) or type(value.get('retCode')) is not int or value['retCode']!=0:
                code=value.get('retCode') if isinstance(value,dict) else None
                raise ExchangeProbeError('key_ip_or_permissions_rejected' if code in (10003,10004,10005,10007,10010) else 'exchange_request_rejected')
            result=value.get('result')
            if not isinstance(result,dict):raise ExchangeProbeError('invalid_exchange_response')
            return result
        except HTTPError as exc:
            raise ExchangeProbeError('exchange_access_restricted' if exc.code==403 else 'exchange_rate_limited' if exc.code in (418,429) else 'exchange_request_rejected') from None
        except (URLError,TimeoutError,OSError):raise ExchangeProbeError('exchange_network_unavailable') from None
        except (json.JSONDecodeError,UnicodeDecodeError):raise ExchangeProbeError('invalid_exchange_response') from None

    def _clock(self):
        value=self._get_bybit('/v5/market/time')
        try:
            milliseconds=int(value['timeNano'])//1000000
            if milliseconds<=0:raise ValueError()
            return milliseconds
        except (KeyError,ValueError,TypeError):raise ExchangeProbeError('invalid_server_time') from None

    def verify(self,key,secret):
        if not all(isinstance(x,str) and x.isascii() and 8<=len(x)<=512 and not any(c.isspace() for c in x) for x in (key,secret)):
            raise ExchangeProbeError('invalid_credentials_format')
        info=self._get_bybit('/v5/user/query-api',key,secret,self._clock())
        if type(info.get('readOnly')) is not int or info['readOnly']!=1:
            raise ExchangeProbeError('readonly_key_required')
        permissions=info.get('permissions')
        if not isinstance(permissions,dict):raise ExchangeProbeError('readonly_permissions_incomplete_or_enabled')
        for name in ('Wallet','Withdraw'):
            values=permissions.get(name,[])
            if values is None:values=[]
            if not isinstance(values,list) or any(not isinstance(x,str) or x.strip() for x in values):
                raise ExchangeProbeError('readonly_key_required')
        payload=self._get_bybit('/v5/account/wallet-balance',key,secret,self._clock(),'accountType=UNIFIED')
        accounts=payload.get('list')
        if not isinstance(accounts,list) or len(accounts)!=1 or not isinstance(accounts[0],dict) or accounts[0].get('accountType')!='UNIFIED':
            raise ExchangeProbeError('invalid_account_balances')
        coins=accounts[0].get('coin')
        if not isinstance(coins,list) or len(coins)>10000:raise ExchangeProbeError('invalid_account_balances')
        balances=[]
        for coin in coins:
            if not isinstance(coin,dict) or not isinstance(coin.get('coin'),str) or not coin['coin'].isalnum() or len(coin['coin'])>32:
                raise ExchangeProbeError('invalid_account_balances')
            try:
                wallet,equity=Decimal(str(coin['walletBalance'])),Decimal(str(coin['equity']))
                locked=None if coin.get('locked') in ('',None) else Decimal(str(coin['locked']))
                if not wallet.is_finite() or not equity.is_finite() or (locked is not None and (not locked.is_finite() or locked<0)):raise InvalidOperation
            except (KeyError,InvalidOperation,ValueError):raise ExchangeProbeError('invalid_account_balances') from None
            if wallet or equity or locked:
                balances.append({'asset':coin['coin'],'free':None,'locked':str(locked) if locked is not None else None,'wallet_balance':str(wallet),'equity':str(equity)})
        return {'exchange':'bybit','status':'verified_readonly','checked_at':datetime.now(timezone.utc).isoformat(),'permissions':{'reading':True,'trading':False,'transfers':False,'withdrawals':False},'balances':balances,'balance_scope':'unified_account','credentials_persisted':False,'order_submission_available':False}

class BitgetConnectionProbe(BinanceConnectionProbe):
    def _get_bitget(self,path,key=None,secret=None,passphrase=None,timestamp=None):
        import base64
        if path not in ('/api/v2/public/time','/api/v3/account/info','/api/v3/account/assets'):
            raise ExchangeProbeError('unsupported_endpoint')
        headers={'User-Agent':'ai-trading-readonly-probe'}
        if key is not None:
            signature=base64.b64encode(hmac.new(secret.encode(),(str(timestamp)+'GET'+path).encode(),hashlib.sha256).digest()).decode()
            headers.update({'ACCESS-KEY':key,'ACCESS-SIGN':signature,'ACCESS-TIMESTAMP':str(timestamp),'ACCESS-PASSPHRASE':passphrase})
        request=Request('https://api.bitget.com'+path,headers=headers,method='GET')
        try:
            with self.transport(request,timeout=8) as response:raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ExchangeProbeError('response_too_large')
            value=json.loads(raw)
            if not isinstance(value,dict) or value.get('code')!='00000':raise ExchangeProbeError('exchange_request_rejected')
            if not isinstance(value.get('data'),dict):raise ExchangeProbeError('invalid_exchange_response')
            return value['data']
        except HTTPError as exc:
            raise ExchangeProbeError('exchange_rate_limited' if exc.code in (418,429) else 'exchange_request_rejected') from None
        except (URLError,TimeoutError,OSError):raise ExchangeProbeError('exchange_network_unavailable') from None
        except (json.JSONDecodeError,UnicodeDecodeError):raise ExchangeProbeError('invalid_exchange_response') from None

    def _clock(self):
        value=self._get_bitget('/api/v2/public/time')
        try:
            timestamp=int(value['serverTime'])
            if timestamp<=0:raise ValueError()
            return timestamp
        except (KeyError,ValueError,TypeError):raise ExchangeProbeError('invalid_server_time') from None

    def verify(self,key,secret,passphrase):
        if not all(isinstance(x,str) and x.isascii() and 8<=len(x)<=512 and not any(c.isspace() for c in x) for x in (key,secret)):
            raise ExchangeProbeError('invalid_credentials_format')
        if not isinstance(passphrase,str) or not 1<=len(passphrase)<=128 or not passphrase.isascii() or any(ord(c)<32 or ord(c)==127 for c in passphrase):
            raise ExchangeProbeError('invalid_passphrase')
        info=self._get_bitget('/api/v3/account/info',key,secret,passphrase,self._clock())
        permissions=info.get('permissions')
        if info.get('permType') not in ('read-only','readonly') or not isinstance(permissions,list) or any(x not in ('uta_mgt','uta_trade','copy_futures_position','copy_futures_order') for x in permissions):
            raise ExchangeProbeError('readonly_key_required')
        payload=self._get_bitget('/api/v3/account/assets',key,secret,passphrase,self._clock())
        assets=payload.get('assets')
        if not isinstance(assets,list) or len(assets)>10000:raise ExchangeProbeError('invalid_account_balances')
        balances=[]
        for asset in assets:
            if not isinstance(asset,dict) or not isinstance(asset.get('coin'),str) or not asset['coin'].isalnum() or len(asset['coin'])>32:
                raise ExchangeProbeError('invalid_account_balances')
            try:
                available,locked,balance,equity=(Decimal(str(asset[x])) for x in ('available','locked','balance','equity'))
                if not all(x.is_finite() for x in (available,locked,balance,equity)) or locked<0:raise InvalidOperation
            except (KeyError,ValueError,InvalidOperation):raise ExchangeProbeError('invalid_account_balances') from None
            if any((available,locked,balance,equity)):balances.append({'asset':asset['coin'],'free':str(available),'locked':str(locked),'wallet_balance':str(balance),'equity':str(equity)})
        return {'exchange':'bitget','status':'verified_readonly','checked_at':datetime.now(timezone.utc).isoformat(),'permissions':{'reading':True,'trading':False,'transfers':False,'withdrawals':False},'balances':balances,'balance_scope':'bitget_unified_account','credentials_persisted':False,'order_submission_available':False}

class GateConnectionProbe(BinanceConnectionProbe):
    def _get_gate(self,path,key=None,secret=None,timestamp=None):
        if path not in ('/api/v4/spot/time','/api/v4/account/main_keys','/api/v4/spot/accounts'):
            raise ExchangeProbeError('unsupported_endpoint')
        headers={'User-Agent':'ai-trading-readonly-probe'}
        if key is not None:
            prehash='\n'.join(['GET',path,'',hashlib.sha512(b'').hexdigest(),str(timestamp)])
            signature=hmac.new(secret.encode(),prehash.encode(),hashlib.sha512).hexdigest()
            headers.update({'KEY':key,'Timestamp':str(timestamp),'SIGN':signature})
        request=Request('https://api.gateio.ws'+path,headers=headers,method='GET')
        try:
            with self.transport(request,timeout=8) as response:raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ExchangeProbeError('response_too_large')
            value=json.loads(raw)
            if not isinstance(value,(dict,list)):raise ExchangeProbeError('invalid_exchange_response')
            return value
        except HTTPError as exc:
            raise ExchangeProbeError('key_ip_or_permissions_rejected' if exc.code in (401,403) else 'exchange_rate_limited' if exc.code in (418,429) else 'exchange_request_rejected') from None
        except (URLError,TimeoutError,OSError):raise ExchangeProbeError('exchange_network_unavailable') from None
        except (json.JSONDecodeError,UnicodeDecodeError):raise ExchangeProbeError('invalid_exchange_response') from None

    def _clock(self):
        value=self._get_gate('/api/v4/spot/time')
        milliseconds=value.get('server_time') if isinstance(value,dict) else None
        if type(milliseconds) is not int or milliseconds<1000000000000:raise ExchangeProbeError('invalid_server_time')
        return milliseconds//1000

    def verify(self,key,secret):
        if not all(isinstance(x,str) and x.isascii() and 8<=len(x)<=512 and not any(c.isspace() for c in x) for x in (key,secret)):
            raise ExchangeProbeError('invalid_credentials_format')
        keys=self._get_gate('/api/v4/account/main_keys',key,secret,self._clock())
        if not isinstance(keys,list) or len(keys)>1000:raise ExchangeProbeError('invalid_exchange_response')
        matches=[row for row in keys if isinstance(row,dict) and isinstance(row.get('key'),str) and hmac.compare_digest(row['key'].encode(),key.encode())]
        if len(matches)!=1:raise ExchangeProbeError('key_permission_identity_unavailable')
        info=matches[0]
        if type(info.get('state')) is not int or info['state']!=1:raise ExchangeProbeError('key_ip_or_permissions_rejected')
        if type(info.get('mode')) is not int or info['mode']!=1:raise ExchangeProbeError('unsupported_account_mode')
        permissions=info.get('perms')
        if not isinstance(permissions,list) or not permissions or any(not isinstance(p,dict) or not isinstance(p.get('name'),str) or not p['name'] or p.get('read_only') is not True for p in permissions):
            raise ExchangeProbeError('readonly_key_required')
        if not any(p['name']=='spot' for p in permissions):raise ExchangeProbeError('reading_permission_missing')
        assets=self._get_gate('/api/v4/spot/accounts',key,secret,self._clock())
        if not isinstance(assets,list) or len(assets)>10000:raise ExchangeProbeError('invalid_account_balances')
        balances=[]
        for asset in assets:
            if not isinstance(asset,dict) or not isinstance(asset.get('currency'),str) or not asset['currency'].isalnum() or len(asset['currency'])>32:
                raise ExchangeProbeError('invalid_account_balances')
            try:
                free,locked=Decimal(str(asset['available'])),Decimal(str(asset['locked']))
                if not all(x.is_finite() and x>=0 for x in (free,locked)):raise InvalidOperation
            except (KeyError,ValueError,InvalidOperation):raise ExchangeProbeError('invalid_account_balances') from None
            if free or locked:balances.append({'asset':asset['currency'],'free':str(free),'locked':str(locked)})
        return {'exchange':'gate','status':'verified_readonly','checked_at':datetime.now(timezone.utc).isoformat(),'permissions':{'reading':True,'trading':False,'transfers':False,'withdrawals':False},'balances':balances,'balance_scope':'classic_spot_main_account','credentials_persisted':False,'order_submission_available':False}
