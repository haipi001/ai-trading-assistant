from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.services.complete_product_readiness import CompleteProductReadinessService


class MissingSchemaSession:
    rollback_calls = 0

    def execute(self, statement):  # noqa: ANN001
        raise SQLAlchemyError("missing table")

    def scalar(self, statement):  # noqa: ANN001
        raise SQLAlchemyError("missing table")

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_complete_product_readiness_summary_returns_twenty_safe_blocks(client: TestClient) -> None:
    response = client.get("/complete-product/readiness/summary")

    assert response.status_code == 200
    packet = response.json()
    assert packet["status"] == "developed_safe_slice"
    assert packet["target"] == "complete_personal_financial_terminal"
    assert packet["developed_items"] == 20
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False
    assert packet["wallet_signing_available"] is False
    assert packet["cex_trading_available"] is False
    assert [item["item_no"] for item in packet["items"]] == list(range(1, 21))
    assert all(item["development_status"] == "developed_safe_slice" for item in packet["items"])


def test_complete_product_readiness_items_match_requested_blocks(client: TestClient) -> None:
    response = client.get("/complete-product/readiness/items")

    assert response.status_code == 200
    items = response.json()
    assert [item["key"] for item in items] == [
        "daily_use_loop",
        "complete_investment_ledger",
        "deep_data_trust",
        "research_terminal_depth",
        "portfolio_management_depth",
        "strategy_backtest_lab_depth",
        "decision_gate_explainability",
        "journal_review_productization",
        "notifications_calendar",
        "complete_user_system",
        "commercialization_foundation",
        "product_ops_admin",
        "security_engineering",
        "ai_safety",
        "ai_governance",
        "deployment_operability",
        "testing_system",
        "frontend_experience",
        "open_ecosystem",
        "pre_live_execution_stack",
    ]
    assert items[0]["user_problem"]
    assert items[0]["logic_principle"]
    assert items[0]["ui_principle"]
    assert items[19]["execution_available"] is False
    assert "broker_sandbox_adapter_missing" in items[19]["blockers"]


def test_complete_product_readiness_single_item_and_missing_item(client: TestClient) -> None:
    response = client.get("/complete-product/readiness/items/18")

    assert response.status_code == 200
    packet = response.json()
    assert packet["key"] == "frontend_experience"
    assert packet["item_no"] == 18
    assert packet["product_status"] == "blocked"

    missing = client.get("/complete-product/readiness/items/99")
    assert missing.status_code == 404


def test_completed_local_onboarding_resolves_daily_loop_blocker(client: TestClient) -> None:
    started = client.post(
        "/daily-use/local-start?user_id=onboarded-user",
        json={
            "data_mode": "simulation",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
            "workspace_goal": "daily_investment_review",
        },
    )
    assert started.status_code == 200
    watchlist = client.post(
        "/daily-use/watchlist",
        json={"user_id": "onboarded-user", "symbol": "AAPL", "priority": "normal"},
    )
    assert watchlist.status_code == 201

    item = client.get(
        "/complete-product/readiness/items/1",
        headers={"X-AI-Trading-User": "onboarded-user"},
    ).json()

    assert "daily_user_onboarding_completion_required" not in item["blockers"]
    assert item["product_status"] == "ready", item["blockers"]
    assert item["metrics"]["onboarding_completed_steps"] == 5


def test_complete_product_readiness_degrades_when_schema_is_missing() -> None:
    db = MissingSchemaSession()
    service = CompleteProductReadinessService(db)  # type: ignore[arg-type]

    items = service.items(user_id="local-dev-user")

    assert len(items) == 20
    assert db.rollback_calls > 0
    deployment_packet = items[15]
    assert deployment_packet["key"] == "deployment_operability"
    assert any(blocker.startswith("schema_unavailable:") for blocker in deployment_packet["blockers"])


def test_complete_product_buildout_summary_models_next_projects(client: TestClient) -> None:
    response = client.get("/complete-product/readiness/buildout/summary")

    assert response.status_code == 200
    packet = response.json()
    assert packet["status"] == "developed_safe_slice"
    assert packet["product_stage"] == "pre_private_beta"
    assert packet["projects_total"] == 12
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False
    assert packet["wallet_signing_available"] is False
    assert packet["cex_trading_available"] is False
    assert [item["key"] for item in packet["projects"]] == [
        "onboarding_daily_loop",
        "authenticated_readonly_adapter",
        "ledger_repair_workflow",
        "dataset_version_replay",
        "research_event_terminal",
        "portfolio_risk_terminal",
        "notifications_calendar",
        "auth_rbac_privacy",
        "billing_admin_ops",
        "security_ai_governance",
        "test_release_recovery",
        "broker_sandbox_execution_stack",
    ]
    assert packet["release_stages"][-1]["key"] == "sandbox_execution_pilot"


def test_complete_product_launch_private_core_and_safety_boundaries(client: TestClient) -> None:
    launch = client.get("/complete-product/readiness/launch-preparation")
    private_core = client.get("/complete-product/readiness/private-core")
    safety = client.get("/complete-product/readiness/safety-limited-capabilities")

    assert launch.status_code == 200
    assert private_core.status_code == 200
    assert safety.status_code == 200
    launch_packet = launch.json()
    private_packet = private_core.json()
    safety_packet = safety.json()
    assert launch_packet["launch_status"] == "blocked"
    assert "private_beta" in launch_packet["recommended_launch_order"]
    assert private_packet["default_license_strategy"] == "open_interfaces_private_core"
    assert any(item["key"] == "gate_policy_engine" for item in private_packet["proprietary_modules"])
    assert safety_packet["boundary_status"] == "enforced"
    assert "real_broker_order_submission" in safety_packet["forbidden_until_explicit_release_gate"]
    assert "wallet_signing_or_transfer" in safety_packet["forbidden_until_explicit_release_gate"]
    assert safety_packet["execution_available"] is False
