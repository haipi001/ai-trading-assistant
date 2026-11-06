"""Imports and mark-to-market must follow instrument IDs, never ticker alone."""
from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from app.adapters.market_data_readonly import AdapterHealth
from app.adapters.types import AdapterQuote, AdapterCandle
from app.models import Asset, Position, Quote
from app.services.data_sources import DataSourceService
from test_server_account_risk import edit_db
from test_decision_gates import create_account


class FixtureAdapter:
    price = 300
    currency = 'USD'
    source = 'identity_fixture'
    quote_symbol = None
    candle_symbol = None
    candle_timeframe = None

    def health_check(self):
        return AdapterHealth(provider='identity_fixture', status='ok', checked_at=datetime.now(timezone.utc),
                             latency_ms=0, message='Isolated fixture', details={})

    def get_quote(self, symbol):
        return AdapterQuote(symbol=self.quote_symbol or symbol, price=self.price, source=self.source,
                            as_of=datetime.now(timezone.utc), currency=self.currency)

    def get_candles(self, symbol, timeframe, limit):
        return [AdapterCandle(symbol=self.candle_symbol or symbol, timeframe=self.candle_timeframe or timeframe,
                              timestamp=datetime(2026, 11, 1, tzinfo=timezone.utc), open=1, high=2,
                              low=1, close=2, volume=3, source=self.source, currency=self.currency)]


@pytest.fixture
def feed(client, monkeypatch):
    adapter = FixtureAdapter()
    monkeypatch.setattr(DataSourceService, '_adapter_for', lambda self, connection: adapter)
    response = client.post('/data-sources/connections', json={
        'name': 'Identity fixture', 'provider': 'yfinance_public', 'mode': 'read_only',
    })
    assert response.status_code == 201
    return response.json()['id'], adapter


def asset(client, **changes):
    response = client.post('/assets', json=dict(
        symbol='AAPL', name='Identity test', asset_type='stock', market='US', venue='NASDAQ', currency='USD',
        tradable=True, manual_enabled=True, auto_enabled=False,
    ) | changes)
    assert response.status_code == 201, response.text
    return response.json()


def load(client, feed, kind='quotes', **changes):
    params = dict(symbols=['AAPL'], asset_type='stock', market='US', venue='NASDAQ', currency='USD') | changes
    if kind == 'candles':
        params |= {'timeframe': '1h', 'limit': 1}
    return client.post(f'/data-sources/connections/{feed[0]}/import-{kind}', json=params)


def quote_assets():
    ids = []
    edit_db(lambda db: ids.extend(db.scalars(select(Quote.asset_id)).all()))
    return ids


@pytest.mark.parametrize('field,value', [
    ('venue', 'OTHER'), ('currency', 'EUR'), ('market', 'EU'), ('asset_type', 'etf'),
])
@pytest.mark.parametrize('kind', ['quotes', 'candles'])
def test_same_ticker_different_identity_is_never_reused(client, feed, field, value, kind):
    original = asset(client)
    if field == 'currency':
        feed[1].currency = value
    response = load(client, feed, kind, **{field: value})
    assert response.status_code == 201, response.text
    rows = client.get('/assets').json()
    assert len(rows) == 2
    imported = next(row for row in rows if row['id'] != original['id'])
    assert imported[field] == value
    assert not imported['tradable'] and not imported['manual_enabled'] and not imported['auto_enabled']
    key = 'quotes' if kind == 'quotes' else 'symbols'
    assert response.json()['snapshot']['data_json'][key][0]['asset_id'] == imported['id']


def test_import_updates_only_positions_of_exact_asset_and_preserves_existing_flags(client, feed):
    first, second = asset(client), asset(client, venue='OTHER')
    account = create_account(client)
    def positions(db):
        for item in (first, second):
            db.add(Position(account_id=account['id'], asset_id=item['id'], quantity=2, average_cost=80,
                            market_price=100, market_value=200, unrealized_pnl=40, realized_pnl=0, weight=0.5))
    edit_db(positions)
    response = load(client, feed)
    assert response.status_code == 201, response.text
    def inspect(db):
        for item, expected in ((first, 300), (second, 100)):
            position = db.scalar(select(Position).where(Position.asset_id == item['id']))
            assert float(position.market_price) == expected
            assert float(position.market_value) == expected * 2
            assert float(position.unrealized_pnl) == (expected - 80) * 2
        assert db.get(Asset, first['id']).manual_enabled
    edit_db(inspect)


@pytest.mark.parametrize('kind', ['quotes', 'candles'])
def test_provider_mismatched_symbol_or_currency_is_rejected_before_writing(client, feed, kind):
    if kind == 'quotes':
        feed[1].quote_symbol = 'NVDA'
    else:
        feed[1].candle_symbol = 'NVDA'
    assert load(client, feed, kind).status_code == 422
    feed[1].quote_symbol = feed[1].candle_symbol = None
    feed[1].currency = 'EUR'
    assert load(client, feed, kind).status_code == 422
    assert client.get('/assets').json() == []
    assert quote_assets() == []


def test_provider_candle_timeframe_mismatch_is_rejected(client, feed):
    feed[1].candle_timeframe = '1d'
    assert load(client, feed, 'candles').status_code == 422
    assert client.get('/assets').json() == []


def test_duplicate_exact_identity_requires_resolution_instead_of_picking_first(client, feed):
    asset(client)
    asset(client)
    response = load(client, feed)
    assert response.status_code == 422
    assert 'ambiguous instrument identity' in response.json()['detail']
    assert quote_assets() == []


def test_real_provider_does_not_inherit_mock_metadata_even_with_spoofed_source_label(client, feed):
    asset(client)
    feed[1].source = 'mock_market_data'
    response = load(client, feed, venue='REAL_PROVIDER', market='EU')
    assert response.status_code == 201, response.text
    row = response.json()['snapshot']['data_json']['quotes'][0]
    assert (row['venue'], row['market']) == ('REAL_PROVIDER', 'EU')


def test_case_and_outer_space_normalization_reuses_exact_identity(client, feed):
    original = asset(client, symbol='aapl', venue='nasdaq')
    response = load(client, feed, venue=' NASDAQ ')
    assert response.status_code == 201, response.text
    assert response.json()['snapshot']['data_json']['quotes'][0]['asset_id'] == original['id']
    assert len(client.get('/assets').json()) == 1


def test_onchain_contracts_and_native_assets_are_separate_and_existing_metadata_is_preserved(client):
    ids = []
    def sync(db):
        service = DataSourceService(db)
        for chain, contract in [('1', '0xaaa'), ('2', '0xaaa'), ('1', '0xbbb'), ('1', None)]:
            row = service._get_or_create_read_only_asset_from_position(symbol='TOKEN', source='wallet_readonly', row={
                'asset_type': 'crypto', 'market': 'GLOBAL', 'venue': 'ONCHAIN', 'currency': 'USD',
                'chain_id': chain, 'contract_address': contract,
            })
            ids.append(row.id)
        original = db.get(Asset, ids[0])
        original.name, original.manual_enabled, original.tradable = 'User name', True, True
        row = service._get_or_create_read_only_asset_from_position(symbol='TOKEN', source='wallet_readonly', row={
            'asset_type': 'crypto', 'market': 'GLOBAL', 'venue': 'ONCHAIN', 'currency': 'USD',
            'chain_id': '1', 'contract_address': '0xaaa', 'name': 'Provider overwrite',
        })
        assert row.id == ids[0] and row.name == 'User name' and row.manual_enabled and row.tradable
    edit_db(sync)
    assert len(set(ids)) == 4


def test_mock_quote_refresh_does_not_touch_same_symbol_other_venue(client):
    target, unrelated = asset(client), asset(client, venue='OTHER')
    response = client.post('/mock/update-quotes')
    assert response.status_code == 200, response.text
    quotes = quote_assets()
    assert target['id'] in quotes
    assert unrelated['id'] not in quotes


def test_ambiguous_mock_instrument_returns_actionable_422(client):
    asset(client)
    asset(client)
    response = client.post('/mock/update-quotes')
    assert response.status_code == 422
    assert 'ambiguous instrument identity' in response.json()['detail']
    assert quote_assets() == []


@pytest.mark.parametrize('matches', [True, False])
def test_research_gate_checks_candle_snapshot_instrument_identity(client, matches):
    from app.models import DataSnapshot
    from test_decision_gates import setup_gate_ready_order, passing_gate_payload, gate_by_type
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    def change(db):
        snapshot = db.get(DataSnapshot, snapshot_id)
        row = dict(snapshot.data_json['quotes'][0])
        if not matches:
            row['asset_id'] = 'unrelated-instrument'
        snapshot.snapshot_type = 'market_candles'
        snapshot.data_json = {'symbols': [row]}
    edit_db(change)
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot_id))
    assert response.status_code == 201, response.text
    gate = gate_by_type(response.json()['gates'], 'RESEARCH_GATE')
    assert (gate['status'] == 'PASSED') == matches
    if not matches:
        assert 'data_snapshot_asset_mismatch' in gate['blocking_reasons_json']
