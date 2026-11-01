from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.services.strategy_rules import StrategyRulesService
from test_risk_approval import create_account
from test_risk_approval import create_asset


class MissingStrategyRulesSession:
    rollback_calls = 0

    def scalars(self, statement):  # noqa: ANN001
        raise SQLAlchemyError("missing strategy_rules")

    def rollback(self) -> None:
        self.rollback_calls += 1


def create_playbook(client: TestClient) -> dict:
    response = client.post(
        "/strategy-playbooks",
        json={
            "user_id": "default-user",
            "name": "Route Parity Playbook",
            "strategy_type": "swing",
            "applicable_markets": ["US"],
            "applicable_assets": ["stock"],
            "entry_conditions_json": {"setup": "quality pullback"},
            "exit_conditions_json": {"exit": "thesis break"},
            "risk_rules_json": {"max_position_pct": 0.1},
            "automation_level": "A1_RESEARCH",
            "requires_human_approval": True,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_strategy_rules_crud_is_metadata_only(client: TestClient) -> None:
    playbook = create_playbook(client)

    created = client.post(
        "/strategy-rules",
        json={
            "strategy_playbook_id": playbook["id"],
            "rule_type": "entry",
            "priority": 3,
            "description": "Require a thesis and confirmed data quality before considering a draft.",
            "conditions_json": {"requires_thesis": True, "data_quality_min": "GOOD"},
            "actions_json": {"next_action": "create_research_task"},
        },
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["strategy_playbook_id"] == playbook["id"]
    assert rule["is_active"] is True

    listed = client.get(f"/strategy-rules?strategy_playbook_id={playbook['id']}").json()
    assert [item["id"] for item in listed] == [rule["id"]]

    patched = client.patch(
        f"/strategy-rules/{rule['id']}",
        json={"priority": 1, "description": "Tightened metadata-only entry rule."},
    )
    assert patched.status_code == 200
    assert patched.json()["priority"] == 1

    deleted = client.delete(f"/strategy-rules/{rule['id']}")
    assert deleted.status_code == 204

    listed_after_delete = client.get(f"/strategy-rules?strategy_playbook_id={playbook['id']}").json()
    assert listed_after_delete[0]["is_active"] is False

    actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert {"strategy_rule.created", "strategy_rule.updated", "strategy_rule.disabled"}.issubset(actions)


def test_strategy_rules_list_degrades_when_schema_is_missing() -> None:
    db = MissingStrategyRulesSession()

    rules = StrategyRulesService(db).list_rules()  # type: ignore[arg-type]

    assert rules == []
    assert db.rollback_calls == 1


def test_backtest_runs_record_experiment_but_missing_asset_fails_closed(client: TestClient) -> None:
    playbook = create_playbook(client)

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Read-only backtest shell",
            "date_from": "2026-01-01",
            "date_to": "2026-03-31",
            "initial_capital": "100000",
            "parameters_json": {"timeframe": "1d"},
        },
    )
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "pending"
    assert run["results_json"]["execution_available"] is False

    started = client.post(f"/backtest-runs/{run['id']}/start")
    assert started.status_code == 200
    started_run = started.json()
    assert started_run["status"] == "blocked"
    assert started_run["results_json"]["execution_available"] is False
    assert started_run["results_json"]["real_orders_created"] == 0
    assert "missing_asset_id" in started_run["results_json"]["blocking_reasons"]
    assert started_run["results_json"]["simulated_trades_created"] == 0

    fetched = client.get(f"/backtest-runs/{run['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "blocked"


def test_controlled_auto_evaluate_and_execute_are_blocked_without_order_intent(client: TestClient) -> None:
    asset = create_asset(client, auto_enabled=True)
    account = create_account(client)
    playbook = create_playbook(client)

    payload = {
        "asset_id": asset["id"],
        "account_id": account["id"],
        "strategy_playbook_id": playbook["id"],
        "target_quantity": "2",
        "max_price": "125.50",
    }
    evaluated = client.post("/controlled-auto/evaluate/dca", json=payload)
    assert evaluated.status_code == 200
    evaluation = evaluated.json()
    assert evaluation["passed"] is False
    assert evaluation["details"]["execution_available"] is False
    assert evaluation["details"]["order_intent_created"] is False
    assert "controlled_auto_execution_not_implemented" in evaluation["blocking_reasons"]
    assert "controlled_auto_requires_gates_passed" in evaluation["blocking_reasons"]

    executed = client.post("/controlled-auto/execute/dca", json=payload)
    assert executed.status_code == 200
    execution = executed.json()
    assert execution["status"] == "blocked"
    assert execution["order_intent_id"] == "not-created"
    assert execution["details"]["controlled_auto_execution_performed"] is False

    missing_intent = client.get("/orders/intents/not-created")
    assert missing_intent.status_code == 404

    actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert "controlled_auto.evaluated" in actions
    assert "controlled_auto.execution_blocked" in actions


def test_broker_connections_alias_rejects_inline_secret_and_stays_reference_only(client: TestClient) -> None:
    rejected = client.post(
        "/broker-connections",
        json={"broker_type": "ibkr", "label": "Inline secret", "api_key_ref": "sk-live-inline-secret"},
    )
    assert rejected.status_code == 422

    created = client.post(
        "/broker-connections",
        json={"broker_type": "ibkr", "label": "IBKR reference", "api_key_ref": "env:IBKR_READONLY_KEY_REF"},
    )
    assert created.status_code == 201
    connection = created.json()
    assert connection["broker_type"] == "ibkr"
    assert connection["api_key_ref"] == "env:IBKR_READONLY_KEY_REF"
    assert connection["status"] == "active"

    listed = client.get("/broker-connections").json()
    assert listed[0]["id"] == connection["id"]

    deleted = client.delete(f"/broker-connections/{connection['id']}")
    assert deleted.status_code == 204
    listed_after_delete = client.get("/broker-connections").json()
    assert listed_after_delete[0]["status"] == "inactive"


def test_modules_registry_reports_safe_gate_compliance(client: TestClient) -> None:
    modules_response = client.get("/modules")
    assert modules_response.status_code == 200
    modules = modules_response.json()
    module_types = {module["module_type"] for module in modules}
    assert {"ai_sidecar_policy", "strategy_rules", "backtest_lab", "controlled_auto", "broker_connections"}.issubset(module_types)

    health = client.get("/modules/controlled_auto/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["registered"] is True
    assert health_payload["available"] is False
    assert "cannot execute" in health_payload["details"]

    compliance = client.get("/modules/controlled_auto/gate-compliance")
    assert compliance.status_code == 200
    compliance_payload = compliance.json()
    assert compliance_payload["registered"] is True
    assert compliance_payload["gate_compliant"] is True
    assert "blocked by design" in compliance_payload["message"]


def test_sidecar_policy_evaluator_approves_read_only_research_sidecar(client: TestClient) -> None:
    response = client.post(
        "/modules/sidecar-policy/evaluate",
        json={
            "name": "OpenBB research bridge",
            "sidecar_type": "research",
            "capabilities": ["data_ingestion", "research_generation"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["allowed"] is True
    assert payload["execution_available"] is False
    assert payload["real_broker_call_allowed"] is False
    assert "local_gates_before_sidecar" in payload["required_controls"]


def test_sidecar_policy_evaluator_blocks_control_plane_bypass(client: TestClient) -> None:
    response = client.post(
        "/modules/sidecar-policy/evaluate",
        json={
            "name": "Unsafe execution copier",
            "sidecar_type": "execution",
            "capabilities": ["execution"],
            "control_pattern": "sidecar_direct_control",
            "creates_orders": True,
            "executes_trades": True,
            "stores_secrets": True,
            "mutates_core_state": True,
            "source_of_truth_for": ["approvals", "ledger"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["allowed"] is False
    assert "invalid_control_pattern" in payload["blockers"]
    assert "sidecar_must_not_create_orders" in payload["blockers"]
    assert "sidecar_must_not_store_local_secrets" in payload["blockers"]
    assert "sidecar_cannot_be_source_of_truth_for:approvals" in payload["blockers"]

    actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert "sidecar_policy.evaluated" in actions


def test_sidecar_contract_report_requires_contract_and_blocks_control_plane_bypass(client: TestClient) -> None:
    approved = client.post(
        "/modules/sidecar-contract/report",
        json={
            "name": "Research summarizer",
            "sidecar_type": "research",
            "capabilities": ["research_generation"],
            "control_pattern": "local_self_logic_to_sidecar_callback",
            "request_schema": {"symbol": "string", "context": "object"},
            "response_schema": {"summary": "string", "evidence": "array"},
            "audit_callback": "local_audit_log",
        },
    )
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["status"] == "contract_ready"
    assert approved_payload["allowed_for_integration_review"] is True
    assert approved_payload["execution_available"] is False
    assert approved_payload["mutates_core_state_allowed"] is False

    blocked = client.post(
        "/modules/sidecar-contract/report",
        json={
            "name": "Unsafe controller",
            "sidecar_type": "execution",
            "control_pattern": "sidecar_direct_control",
            "creates_orders": True,
            "mutates_core_state": True,
            "source_of_truth_for": ["approvals"],
        },
    )
    assert blocked.status_code == 200
    blocked_payload = blocked.json()
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["allowed_for_integration_review"] is False
    assert "invalid_control_pattern" in blocked_payload["blockers"]
    assert "sidecar_must_not_create_orders" in blocked_payload["blockers"]

    actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert "sidecar_contract.reported" in actions
