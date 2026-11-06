"""Exercise actual trade routes behind verified managed-session middleware."""
import pytest
from app.core.auth import AuthenticatedUser, ROLE_PERMISSIONS
from app.core.config import Settings

@pytest.fixture
def managed_actor(monkeypatch):
    settings = Settings(managed_auth_required=True, beta_auth_required=False, api_rate_limit_enabled=False)
    monkeypatch.setattr('app.core.auth_middleware.get_settings', lambda: settings)
    monkeypatch.setattr('app.core.auth.get_settings', lambda: settings)
    def set_role(role):
        actor = AuthenticatedUser('tenant-trade-test', role, ROLE_PERMISSIONS[role], True, True)
        monkeypatch.setattr('app.core.auth_middleware.ManagedAuthService.authenticate', lambda *_: actor)
    set_role('viewer')
    return set_role

@pytest.mark.parametrize('path', [
    '/orders/intents/missing/manual-evidence',
    '/risk/check-order', '/decision-gates/evaluate', '/orders/intents', '/orders/drafts',
    '/controlled-auto/execute/strategy',
    '/orders/intents/missing/draft', '/orders/drafts/missing/approve',
    '/orders/drafts/missing/reject', '/orders/drafts/missing/modify',
    '/paper-executions/drafts/missing/execute', '/live-execution/configs',
    '/live-execution/prepare', '/live-execution/approve', '/live-execution/execute', '/production/broker-sandbox/orders',
    '/kill-switch/engage', '/kill-switch/disengage',
])
def test_viewer_cannot_mutate_trade_workflow_even_with_spoofed_owner_header(client, managed_actor, path):
    response = client.post(path, json={}, headers={'Authorization': 'Bearer test-session', 'X-AI-Trading-Role': 'owner'})
    assert response.status_code == 403
    assert 'missing permission' in response.json()['detail']

@pytest.mark.parametrize('path', [
    '/orders/drafts/missing/approve', '/live-execution/approve',
    '/live-execution/execute', '/live-execution/configs', '/kill-switch/disengage', '/production/broker-sandbox/orders',
])
def test_operator_cannot_approve_execute_configure_or_resume(client, managed_actor, path):
    managed_actor('operator')
    assert client.post(path, json={}, headers={'Authorization': 'Bearer test-session'}).status_code == 403

def test_operator_can_preview_but_not_supply_a_missing_order(client, managed_actor):
    managed_actor('operator')
    response = client.post('/risk/check-order', json={'order_intent_id': 'missing'}, headers={'Authorization': 'Bearer test-session'})
    assert response.status_code == 404

def test_managed_trading_requires_real_session_before_role_header(client, managed_actor):
    assert client.post('/live-execution/execute', json={}, headers={'X-AI-Trading-Role': 'owner'}).status_code == 401

def test_viewer_can_read_order_history(client, managed_actor):
    assert client.get('/live-execution/history', headers={'Authorization': 'Bearer test-session'}).status_code == 200

def test_owner_permission_does_not_bypass_resource_or_execution_gates(client, managed_actor):
    managed_actor('owner')
    assert client.post('/orders/drafts/missing/approve', json={}, headers={'Authorization': 'Bearer test-session'}).status_code == 404


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_hosted_misconfiguration_fails_closed_without_affecting_health(client, monkeypatch, environment):
    settings = Settings(environment=environment, managed_auth_required=False, api_rate_limit_enabled=False)
    monkeypatch.setattr('app.core.auth_middleware.get_settings', lambda: settings)
    for path in ['/accounts', '/live-execution/history', '/health-private', '/docs-private']:
        response = client.get(path, headers={'X-AI-Trading-Role': 'owner'})
        assert response.status_code == 503
        assert response.json()['code'] == 'hosted_auth_misconfigured'
    assert client.post('/production/auth/login', json={}).status_code == 503
    assert client.get('/health').status_code != 503


def test_public_looking_path_does_not_skip_managed_auth(client, managed_actor):
    for path in ['/health-private', '/docs-private', '/openapi.json-private', '/production/auth/login-private', '/production/auth/login/private', '/openapi.json/private']:
        assert client.get(path).status_code == 401


def test_sandbox_service_also_refuses_operator_before_touching_broker():
    from app.services.broker_sandbox import BrokerSandboxProofService, BrokerSandboxProofError
    actor = AuthenticatedUser('operator-test', 'operator', ROLE_PERMISSIONS['operator'], True, True)
    with pytest.raises(BrokerSandboxProofError, match='trade:submit'):
        BrokerSandboxProofService(None).submit(actor=actor, order_draft_id='any', idempotency_key='any')

@pytest.mark.parametrize('role', ['owner', 'admin'])
@pytest.mark.parametrize('path,body', [
    ('/orders/drafts/missing/approve', {'approver_id':'someone-else'}),
    ('/orders/drafts/missing/reject', {'approver_id':'someone-else'}),
    ('/paper-executions/drafts/missing/execute', {'approver_id':'someone-else'}),
    ('/live-execution/approve', {'order_draft_id':'missing', 'approver_id':'someone-else'}),
    ('/live-execution/execute', {'order_draft_id':'missing', 'approver_id':'someone-else'}),
    ('/kill-switch/engage', {'reason':'test', 'engaged_by':'someone-else'}),
])
def test_managed_admin_cannot_impersonate_transaction_actor(client, managed_actor, role, path, body):
    managed_actor(role)
    response = client.post(path, json=body, headers={'Authorization':'Bearer test-session'})
    assert response.status_code == 403
    assert response.json()['code'] == 'actor_identity_mismatch'


def test_managed_stop_record_uses_actual_session_actor_when_omitted(client, managed_actor):
    managed_actor('operator')
    response = client.post('/kill-switch/engage', json={'reason':'operator stop'}, headers={'Authorization':'Bearer test-session'})
    assert response.status_code == 201
    assert response.json()['engaged_by'] == 'tenant-trade-test'


def test_managed_auth_denial_retains_public_frontend_cors(client, managed_actor):
    origin = 'https://haipi001.github.io'
    response = client.get('/api/v2/workspaces/session/options', headers={'Origin': origin})
    assert response.status_code == 401
    assert response.headers.get('access-control-allow-origin') == origin
    assert response.headers.get('access-control-allow-credentials') == 'true'
    denied = client.get('/api/v2/workspaces/session/options', headers={'Origin':'https://untrusted.invalid'})
    assert denied.status_code == 401
    assert 'access-control-allow-origin' not in denied.headers
