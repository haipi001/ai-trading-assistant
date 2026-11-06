"""Ace status is private observation and notification state, never approval."""
import pytest
from sqlalchemy import select,func
from app.models import AgentRun, ScheduledJob, OrderDraft, OrderIntent, Account, Approval, Execution, AuditLog
from test_research_evidence_revalidation import preview, draft
from test_server_account_risk import edit_db


def pending(client):
    intent, _, _ = preview(client)
    record = draft(client, intent)
    return intent, record


def action(client):
    response = client.get('/api/v2/agent/actions')
    assert response.status_code == 200,response.text
    return response.json()['records'][0]


def ack(client, row, status='ACKNOWLEDGED', **headers):
    return client.patch(f"/api/v2/agent/actions/{row['action_id']}/state", headers=headers or None,
        json={'source_revision':row['source_revision'],'expected_version':row['disposition_version'],'status':status})


def test_task_feed_reads_real_records_and_does_not_expose_raw_outputs_or_other_users(client):
    def records(db):
        for user in ['default-user','another-user']:
            db.add(AgentRun(user_id=user,agent_name='Risk reviewer',run_type='mock_research',status='failed',
                input_snapshot_id='fixture-snapshot',output_json={'private':'DO_NOT_EXPOSE'},error_message='DO_NOT_EXPOSE'))
            db.add(ScheduledJob(user_id=user,name='Saved schedule',job_type='report_refresh',status='paused',
                target_json={'private':'DO_NOT_EXPOSE'},schedule_json={'private':'DO_NOT_EXPOSE'}))
    edit_db(records)
    response=client.get('/api/v2/agent/tasks')
    assert response.status_code==200
    packet=response.json(); assert len(packet['records'])==2 and not packet['task_controls_available']
    assert {r['status'] for r in packet['records']}=={'failed','paused'}
    assert {r['record_kind'] for r in packet['records']}=={'agent_run','scheduled_job'}
    assert 'DO_NOT_EXPOSE' not in response.text
    assert all(not r['execution_available'] for r in packet['records'])
    assert len(client.get('/api/v2/agent/tasks?limit=1').json()['records'])==1
    assert client.get('/api/v2/agent/tasks?limit=1').json()['has_more']


def test_notice_acknowledgement_persists_without_changing_order_or_creating_approval(client):
    _, record=pending(client)
    row=action(client)
    assert row['source_id']==record['id'] and row['kind']=='APPROVAL_REQUEST'
    assert not row['execution_available'] and not row['approval_available']
    response=ack(client,row)
    assert response.status_code==200,response.text
    assert response.json()['status']=='ACKNOWLEDGED'
    assert action(client)['status']=='ACKNOWLEDGED'
    def inspect(db):
        assert db.get(OrderDraft,record['id']).approval_status=='pending'
        assert db.scalar(select(func.count()).select_from(Approval))==0
        assert db.scalar(select(func.count()).select_from(Execution))==0
    edit_db(inspect)
    restored=ack(client,response.json(),'OPEN')
    assert restored.status_code==200 and restored.json()['status']=='OPEN'


def test_old_disposition_version_cannot_overwrite_another_update(client):
    pending(client);row=action(client)
    assert ack(client,row).status_code==200
    assert ack(client,row,'DISMISSED').status_code==409
    assert action(client)['status']=='ACKNOWLEDGED'


def test_source_change_reopens_notice_and_stale_confirmation_is_rejected(client):
    _, record=pending(client);row=action(client)
    assert ack(client,row).status_code==200
    edit_db(lambda db:setattr(db.get(OrderDraft,record['id']),'approval_status','rejected'))
    current=action(client)
    assert current['status']=='OPEN' and current['source_revision']!=row['source_revision']
    assert ack(client,row).status_code==409


def test_other_local_user_cannot_read_or_ack_notice(client):
    pending(client);row=action(client)
    assert client.get('/api/v2/agent/actions',headers={'X-AI-Trading-User':'another-user'}).json()['records']==[]
    assert ack(client,row,**{'X-AI-Trading-User':'another-user'}).status_code==404


def test_account_owner_mismatch_is_not_visible_even_when_draft_owner_matches(client):
    intent,_=pending(client)
    edit_db(lambda db:setattr(db.get(Account,intent['account_id']),'user_id','another-user'))
    assert client.get('/api/v2/agent/actions').json()['records']==[]


def test_latest_risk_or_gate_failure_is_observable_without_rerunning_gates(client):
    intent,_=pending(client)
    def blocked(db):
        db.add(AuditLog(user_id='default-user',actor_type='system',actor_id='fixture',action='research_evidence.blocked',
                       entity_type='OrderIntent',entity_id=intent['id'],payload_json={'reason':'snapshot_revoked'}))
    edit_db(blocked)
    row=action(client)
    assert row['last_validation_status']=='blocked' and 'snapshot_revoked' in row['blocking_reasons']
    def inspect(db):
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='research_evidence.blocked'))==1
    edit_db(inspect)


def test_notice_api_rejects_approval_status_and_unknown_fields(client):
    pending(client);row=action(client)
    assert ack(client,row,'approved').status_code==422
    response=client.patch(f"/api/v2/agent/actions/{row['action_id']}/state",json={
        'source_revision':row['source_revision'],'expected_version':0,'status':'ACKNOWLEDGED','approval_status':'approved'})
    assert response.status_code==422


def test_managed_viewer_cannot_change_namespace_with_owner_header(client,monkeypatch):
    from app.core.auth import AuthenticatedUser,ROLE_PERMISSIONS
    from app.core.config import Settings
    pending(client);row=action(client)
    settings=Settings(managed_auth_required=True,beta_auth_required=False,api_rate_limit_enabled=False)
    monkeypatch.setattr('app.core.auth_middleware.get_settings',lambda:settings)
    monkeypatch.setattr('app.core.auth.get_settings',lambda:settings)
    actor=AuthenticatedUser('isolated-viewer','viewer',ROLE_PERMISSIONS['viewer'],True,True)
    monkeypatch.setattr('app.core.auth_middleware.ManagedAuthService.authenticate',lambda *_:actor)
    headers={'Authorization':'Bearer isolated-session','X-AI-Trading-User':'default-user','X-AI-Trading-Role':'owner'}
    assert client.get('/api/v2/agent/actions',headers=headers).json()['records']==[]
    assert ack(client,row,**headers).status_code==404
    assert client.get('/api/v2/agent/tasks').status_code==401


def test_managed_viewer_can_ack_own_notice_but_still_cannot_approve_trade(client,monkeypatch):
    from app.core.auth import AuthenticatedUser,ROLE_PERMISSIONS
    from app.core.config import Settings
    _,record=pending(client);row=action(client)
    settings=Settings(managed_auth_required=True,beta_auth_required=False,api_rate_limit_enabled=False)
    monkeypatch.setattr('app.core.auth_middleware.get_settings',lambda:settings)
    monkeypatch.setattr('app.core.auth.get_settings',lambda:settings)
    actor=AuthenticatedUser('default-user','viewer',ROLE_PERMISSIONS['viewer'],True,True)
    monkeypatch.setattr('app.core.auth_middleware.ManagedAuthService.authenticate',lambda *_:actor)
    headers={'Authorization':'Bearer own-viewer-session'}
    response=ack(client,row,**headers)
    assert response.status_code==200 and response.json()['status']=='ACKNOWLEDGED'
    assert client.post(f"/orders/drafts/{record['id']}/approve",json={},headers=headers).status_code==403


def test_notice_references_the_exact_saved_research_gate_evidence(client):
    _,record=pending(client)
    row=action(client)
    from app.models import DecisionGate
    def inspect(db):
        saved=db.get(OrderDraft,record['id'])
        gate=db.get(DecisionGate,saved.decision_gate_results['RESEARCH_GATE']['gate_id'])
        assert gate.evidence_json['data_snapshot_id'] in row['evidence_ids']
        assert gate.evidence_json['research_report_id'] in row['evidence_ids']
    edit_db(inspect)
