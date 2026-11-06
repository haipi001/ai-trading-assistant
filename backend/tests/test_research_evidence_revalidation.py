"""No stored passing research verdict survives a change to its cited evidence."""
import pytest
from sqlalchemy import select
from app.models import AuditLog, DataCatalogEntry, DataQualityReport, DataSnapshot, DecisionGate, ResearchReport
from test_decision_gates import setup_gate_ready_order, create_report, passing_gate_payload
from test_risk_approval import risk_payload
from test_server_account_risk import edit_db


def preview(client):
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot_id))
    assert response.status_code == 201 and response.json()['all_passed'], response.text
    gates = response.json()['gates']
    gate = next(item for item in reversed(gates) if item['gate_type'] == 'RESEARCH_GATE')
    return intent, snapshot_id, gate


def draft(client, intent):
    response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent['id']))
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, record):
    return client.post(f"/orders/drafts/{record['id']}/approve", json={})


def execute(client, record):
    return client.post(f"/paper-executions/drafts/{record['id']}/execute", json={'fill_price': 225.12})


def change_evidence(kind, snapshot_id, report_id):
    def change(db):
        if kind == 'report':
            # Still a valid report: even a nonblocking revision needs a new preview.
            db.get(ResearchReport, report_id).summary = 'Revised report after preview'
        elif kind == 'snapshot':
            snapshot = db.get(DataSnapshot, snapshot_id)
            snapshot.metadata_json = dict(snapshot.metadata_json) | {'revision': 'after-preview'}
        elif kind == 'snapshot_numeric_type':
            snapshot = db.get(DataSnapshot, snapshot_id)
            rows = [dict(row) for row in snapshot.data_json['quotes']]
            rows[0]['price'] = str(rows[0]['price'])
            snapshot.data_json = dict(snapshot.data_json) | {'quotes': rows}
        elif kind == 'quality':
            quality = db.scalar(select(DataQualityReport).where(DataQualityReport.data_snapshot_id == snapshot_id))
            quality.score = 0.96
        elif kind == 'catalog':
            catalog = db.scalar(select(DataCatalogEntry).where(DataCatalogEntry.data_snapshot_id == snapshot_id))
            catalog.usable_for_trading = False
        elif kind == 'deleted_report':
            db.delete(db.get(ResearchReport, report_id))
        elif kind == 'legacy_gate':
            gate = db.scalar(select(DecisionGate).where(
                DecisionGate.gate_type == 'RESEARCH_GATE',
                DecisionGate.evidence_json['research_report_id'].as_string() == report_id,
            ))
            gate.evidence_json = {k: v for k, v in gate.evidence_json.items() if not k.startswith('research_fingerprint')}
    edit_db(change)


@pytest.mark.parametrize('stage', ['draft', 'approval', 'execution'])
@pytest.mark.parametrize('kind', ['report', 'snapshot', 'snapshot_numeric_type', 'quality', 'catalog', 'deleted_report', 'legacy_gate'])
def test_evidence_changes_block_every_order_boundary_and_leave_audit(client, stage, kind):
    intent, snapshot_id, gate = preview(client)
    record = draft(client, intent) if stage != 'draft' else None
    if stage == 'execution':
        response = approve(client, record)
        assert response.status_code == 201, response.text
    change_evidence(kind, snapshot_id, gate['evidence_json']['research_report_id'])
    if stage == 'draft':
        response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent['id']))
    elif stage == 'approval':
        response = approve(client, record)
    else:
        response = execute(client, record)
    assert response.status_code == 422, response.text
    assert 'research evidence' in response.json()['detail']
    assert client.get('/paper-executions').json() == []
    def inspect(db):
        audit = db.scalar(select(AuditLog).where(
            AuditLog.entity_id == intent['id'], AuditLog.action == 'research_evidence.blocked',
        ))
        assert audit is not None
    edit_db(inspect)


def test_unchanged_pinned_report_survives_unrelated_new_report(client):
    intent, snapshot_id, _ = preview(client)
    record = draft(client, intent)
    create_report(client, snapshot_id)
    assert approve(client, record).status_code == 201
    response = execute(client, record)
    assert response.status_code == 201, response.text
    assert len(client.get('/paper-executions').json()) == 1


def test_new_preview_does_not_silently_reauthorize_old_draft(client):
    intent, snapshot_id, gate = preview(client)
    old = draft(client, intent)
    assert approve(client, old).status_code == 201
    change_evidence('report', snapshot_id, gate['evidence_json']['research_report_id'])
    response = client.post('/decision-gates/evaluate', json=passing_gate_payload(intent['id'], snapshot_id))
    assert response.status_code == 201 and response.json()['all_passed']
    assert execute(client, old).status_code == 422
    assert approve(client, old).status_code == 422
    new = draft(client, intent)
    assert approve(client, new).status_code == 201
    response = execute(client, new)
    assert response.status_code == 201, response.text


def test_latest_quality_record_cannot_replace_preview_evidence(client):
    intent, snapshot_id, _ = preview(client)
    record = draft(client, intent)
    assert approve(client, record).status_code == 201
    def replace(db):
        original = db.scalar(select(DataQualityReport).where(DataQualityReport.data_snapshot_id == snapshot_id))
        db.add(DataQualityReport(
            data_snapshot_id=snapshot_id, source=original.source, metric_type=original.metric_type,
            score=1, details_json={'status': 'ok'},
        ))
    edit_db(replace)
    response = execute(client, record)
    assert response.status_code == 422
    assert 'research evidence changed' in response.json()['detail']


def test_order_evidence_reference_mutation_invalidates_approval(client):
    from app.models import OrderIntent
    intent, _, _ = preview(client)
    record = draft(client, intent)
    assert approve(client, record).status_code == 201
    edit_db(lambda db: setattr(db.get(OrderIntent, intent['id']), 'evidence_json', {'report_id': 'changed-reference'}))
    response = execute(client, record)
    assert response.status_code == 422
    assert 'approved order terms changed' in response.json()['detail']
    assert client.get('/paper-executions').json() == []
