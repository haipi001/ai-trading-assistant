"""Persisted research evidence must correspond to the order it supports."""
import pytest
from app.models import DataSnapshot, OrderIntent, ResearchReport
from test_decision_gates import (
    setup_gate_ready_order, create_asset, create_report, create_quality_snapshot,
    passing_gate_payload, gate_by_type,
)
from test_server_account_risk import edit_db


def evaluate(client, intent, snapshot_id):
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot_id))
    assert response.status_code == 201
    return gate_by_type(response.json()['gates'], 'RESEARCH_GATE')


def select_report(intent, report_id):
    edit_db(lambda db: setattr(db.get(OrderIntent, intent['id']), 'evidence_json', {'report_id': report_id}))


@pytest.mark.parametrize("reference_key", ["report_id", "research_report_id"])
def test_selected_report_is_used_instead_of_latest(client, reference_key):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    selected = create_report(client, snapshot_id)
    create_report(client, snapshot_id)
    edit_db(lambda db: setattr(db.get(OrderIntent, intent['id']), 'evidence_json', {reference_key: selected['id']}))
    result = evaluate(client, intent, snapshot_id)
    assert result['status'] == 'PASSED'
    assert result['evidence_json']['research_report_id'] == selected['id']


def test_missing_selected_report_cannot_fall_back_to_valid_report(client):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    select_report(intent, 'missing-report')
    assert 'selected_research_report_missing' in evaluate(client, intent, snapshot_id)['blocking_reasons_json']


def test_selected_report_cannot_cite_another_snapshot(client):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    other = create_quality_snapshot(client)
    report = create_report(client, other)
    select_report(intent, report['id'])
    assert 'research_report_snapshot_mismatch' in evaluate(client, intent, snapshot_id)['blocking_reasons_json']


def test_selected_report_for_another_asset_is_blocked(client):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    other = create_asset(client, symbol='NVDA')
    report = create_report(client, snapshot_id)
    edit_db(lambda db: setattr(db.get(ResearchReport, report['id']), 'asset_id', other['id']))
    select_report(intent, report['id'])
    assert 'research_report_asset_mismatch' in evaluate(client, intent, snapshot_id)['blocking_reasons_json']


def test_fallback_ignores_newer_report_for_another_asset(client):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    other = create_asset(client, symbol='NVDA')
    report = create_report(client, snapshot_id)
    edit_db(lambda db: setattr(db.get(ResearchReport, report['id']), 'asset_id', other['id']))
    result = evaluate(client, intent, snapshot_id)
    assert result['status'] == 'PASSED'
    assert result['evidence_json']['research_report_id'] != report['id']


@pytest.mark.parametrize('change', [
    {'symbol': 'NVDA'}, {'asset_id': 'other-asset'}, {'venue': 'OTHER'}, {'currency': 'EUR'},
])
def test_quote_scope_must_match_order_even_if_requested_symbols_include_it(client, change):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    def mutate(db):
        snapshot = db.get(DataSnapshot, snapshot_id)
        row = dict(snapshot.data_json['quotes'][0]) | change
        snapshot.data_json = dict(snapshot.data_json) | {'quotes': [row]}
        snapshot.metadata_json = dict(snapshot.metadata_json) | {'symbols_requested': ['AAPL', 'NVDA']}
    edit_db(mutate)
    assert 'data_snapshot_asset_mismatch' in evaluate(client, intent, snapshot_id)['blocking_reasons_json']


def test_multi_asset_snapshot_covers_actual_order_and_import_stores_identity(client):
    asset, _, intent, _ = setup_gate_ready_order(client)
    snapshot_id = create_quality_snapshot(client, ['NVDA', 'AAPL'])
    create_report(client, snapshot_id)
    def inspect(db):
        rows = db.get(DataSnapshot, snapshot_id).data_json['quotes']
        row = next(row for row in rows if row['symbol'] == 'AAPL')
        assert (row['asset_id'], row['venue'], row['currency']) == (asset['id'], 'NASDAQ', 'USD')
    edit_db(inspect)
    assert evaluate(client, intent, snapshot_id)['status'] == 'PASSED'


def test_conflicting_report_references_block_research(client):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    first, second = create_report(client, snapshot_id), create_report(client, snapshot_id)
    edit_db(lambda db: setattr(db.get(OrderIntent, intent['id']), 'evidence_json', {
        'report_id': first['id'], 'research_report_id': second['id'],
    }))
    result = evaluate(client, intent, snapshot_id)
    assert result['status'] == 'BLOCKED'
    assert 'research_report_reference_conflict' in result['blocking_reasons_json']
