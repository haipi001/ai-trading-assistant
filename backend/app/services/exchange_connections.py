"""User-owned, verified read-only exchange connections; raw credentials never in DB."""
import json
import os
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import select
from app.models import DataSourceConnection
from app.core.local_secrets import set_user_secret, delete_user_secret
from app.services.exchange_connection_probe import BinanceConnectionProbe, OkxConnectionProbe, BybitConnectionProbe, BitgetConnectionProbe, GateConnectionProbe, ExchangeProbeError

class ExchangeConnectionService:
    def __init__(self, db, user_id, probe=None):
        self.db, self.user_id, self.probe = db, user_id, probe

    def _query(self):
        return select(DataSourceConnection).where(DataSourceConnection.user_id == self.user_id, DataSourceConnection.provider.in_(['binance_spot_readonly','cex_readonly']))

    def _get(self, connection_id):
        row = self.db.scalar(self._query().where(DataSourceConnection.id == connection_id))
        if row is None or row.config_json.get('exchange_connection_v1') is not True:
            raise ExchangeProbeError('connection_not_found')
        return row

    def _public(self, row):
        return {'id': row.id, 'label': row.name, 'exchange': row.config_json.get('exchange','binance'), 'status': row.status, 'checked_at': row.last_health_checked_at.isoformat() if row.last_health_checked_at else None, 'last_error': row.last_error, 'balance_scope':row.config_json.get('balance_scope','spot_account'), 'permissions': row.config_json.get('verified_permissions'), 'credentials_persisted': bool(row.credentials_ref), 'order_submission_available': False}

    def list(self):
        return [self._public(row) for row in self.db.scalars(self._query()).all() if row.config_json.get('exchange_connection_v1') is True]

    def rename(self, connection_id, label):
        row = self._get(connection_id)
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in label):
            raise ExchangeProbeError('invalid_connection_label')
        row.name = label.strip()
        self.db.commit()
        return self._public(row)

    def create(self, label, key, secret, exchange="binance", passphrase=None):
        label = str(label).strip()
        if not label or len(label) > 80: raise ExchangeProbeError('invalid_connection_label')
        if exchange not in ("binance","okx","bybit","bitget","gate"):raise ExchangeProbeError("unsupported_exchange")
        probe=self.probe or ({"okx":OkxConnectionProbe,"binance":BinanceConnectionProbe,"bybit":BybitConnectionProbe,"bitget":BitgetConnectionProbe,"gate":GateConnectionProbe}[exchange]())
        result=probe.verify(key,secret,passphrase) if exchange in ("okx","bitget") else probe.verify(key,secret)
        identity = str(uuid4());name = 'USER_EXCHANGE_' + identity.replace('-', '').upper()
        ref = set_user_secret(name, json.dumps({'api_key':key,'api_secret':secret,**({'passphrase':passphrase} if exchange in ('okx','bitget') else {})},separators=(',',':')))
        row = DataSourceConnection(id=identity,user_id=self.user_id,name=label,provider='binance_spot_readonly' if exchange=='binance' else 'cex_readonly',source_type='exchange_account',mode='read_only',status='verified_readonly',credentials_ref=ref,config_json={'exchange_connection_v1':True,'exchange':exchange,'balance_scope':result.get('balance_scope','spot_account'),'verified_permissions':result['permissions']},capabilities_json=['balances_read'],last_health_status='ok',last_health_checked_at=datetime.now(timezone.utc))
        try:
            self.db.add(row);self.db.commit()
        except Exception:
            self.db.rollback();delete_user_secret(name)
            raise ExchangeProbeError('connection_storage_failed') from None
        return {**self._public(row),'balances':result['balances']}

    def check(self, connection_id):
        row=self._get(connection_id)
        if row.status=='disabled':raise ExchangeProbeError('connection_disabled')
        name='USER_EXCHANGE_'+row.id.replace('-','').upper()
        if row.credentials_ref != 'env://'+name:raise ExchangeProbeError('connection_credentials_unavailable')
        try:
            value=json.loads(os.environ.get(name,'null'))
            if not isinstance(value,dict):raise ValueError()
            exchange=row.config_json.get('exchange','binance')
            probe=self.probe or ({"okx":OkxConnectionProbe,"binance":BinanceConnectionProbe,"bybit":BybitConnectionProbe,"bitget":BitgetConnectionProbe,"gate":GateConnectionProbe}[exchange]())
            result=probe.verify(value.get('api_key'),value.get('api_secret'),value.get('passphrase')) if exchange in ('okx','bitget') else probe.verify(value.get('api_key'),value.get('api_secret'))
        except (ValueError,TypeError) as exc:
            code=exc.code if isinstance(exc,ExchangeProbeError) else 'connection_credentials_unavailable'
            row.status='verification_failed';row.last_health_status='error';row.last_error=code;row.last_health_checked_at=datetime.now(timezone.utc);self.db.commit()
            raise ExchangeProbeError(code) from None
        row.status='verified_readonly';row.last_health_status='ok';row.last_error=None;row.last_health_checked_at=datetime.now(timezone.utc)
        row.config_json={**row.config_json,'verified_permissions':result['permissions']};self.db.commit()
        return {**self._public(row),'balances':result['balances']}

    def disable(self, connection_id):
        row=self._get(connection_id);row.status='disabled';self.db.commit()
        name='USER_EXCHANGE_'+row.id.replace('-','').upper()
        delete_user_secret(name);row.credentials_ref=None;self.db.commit()
        return self._public(row)
