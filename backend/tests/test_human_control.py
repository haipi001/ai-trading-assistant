import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai import MockAIProvider
from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.db.base import Base
from app.services.human_control import HumanControlError
from app.services.human_control import HumanControlService
from app.services.research_evals import ResearchEvalDatasetService


def owner(user_id: str = "owner-user") -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, role="owner", permissions=ROLE_PERMISSIONS["owner"], auth_required=True, token_configured=True)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_all_human_control_surfaces_are_implemented_without_claiming_external_evidence(db):
    service = HumanControlService(db)
    status = service.initialize(actor=owner())
    assert status["human_control_implementation_pct"] == 100
    assert len(status["projects"]) == 8
    assert all(project["control_implementation_pct"] == 100 for project in status["projects"])
    assert status["production_execution_allowed"] is False
    assert any(project["external_status"] != "verified" for project in status["projects"])


def test_simulated_data_uses_real_snapshot_contract_but_not_external_evidence(db):
    service = HumanControlService(db)
    service.initialize(actor=owner())
    packet = service.run_simulated_data_sync(actor=owner(), latency_ms=150)
    assert packet["status"] == "simulated_passed"
    assert packet["snapshot_id"]
    assert packet["quality_report_id"]
    assert packet["counts_as_external_evidence"] is False
    stability = service.data_stability(actor=owner())
    assert stability["runs"] == 1
    assert stability["pass_rate"] == 1
    real_stage = next(project for project in service.status(actor=owner())["projects"] if project["key"] == "real_data_verification")
    assert real_stage["external_status"] != "verified"


def test_llm_supports_mock_byok_and_platform_modes_with_human_controls(db):
    service = HumanControlService(db)
    service.initialize(actor=owner())
    assert isinstance(service.configured_ai_provider(actor=owner()), MockAIProvider)

    configured = service.configure(
        actor=owner(),
        project_key="research_evidence",
        payload={
            "mode": "bring_your_own",
            "secret_reference": "vault://research/openai#api_key",
            "model": "gpt-4.1-mini",
            "approved_for_research": False,
            "monthly_budget_usd": 20,
            "per_request_budget_usd": 0.5,
        },
    )
    assert configured["secret_reference"] == "vault://research/openai#api_key"
    assert configured["secret_value_present"] is False
    with pytest.raises(HumanControlError, match="human approval"):
        service.configured_ai_provider(actor=owner())

    platform = service.configure(
        actor=owner(),
        project_key="research_evidence",
        payload={"mode": "platform_managed", "billing_mode": "test", "entitlement_status": "test", "approved_for_research": True},
    )
    assert platform["billing_mode"] == "test"
    with pytest.raises(HumanControlError, match="active paid entitlement"):
        service.configured_ai_provider(actor=owner())


def test_llm_preflight_checks_controls_without_calling_external_model(db):
    service = HumanControlService(db)
    service.initialize(actor=owner())
    service.configure(
        actor=owner(),
        project_key="research_evidence",
        payload={
            "mode": "bring_your_own",
            "secret_reference": "vault://research/openai#api_key",
            "model": "gpt-4.1-mini",
            "approved_for_research": True,
            "monthly_budget_usd": 20,
            "per_request_budget_usd": 0.5,
        },
    )
    packet = service.llm_preflight_dry_run(actor=owner(), prompt="Check NVDA thesis delta")
    assert packet["status"] == "preflight_ready"
    assert packet["external_llm_call_attempted"] is False
    assert packet["external_llm_call_allowed"] is False
    assert packet["secret_value_present"] is False
    assert packet["structured_validation"]["valid"] is True
    assert packet["rate_limit"]["scope"] == "llm_calls"
    assert packet["artifact_id"]


def test_llm_preflight_blocks_missing_human_approval(db):
    service = HumanControlService(db)
    service.initialize(actor=owner())
    service.configure(
        actor=owner(),
        project_key="research_evidence",
        payload={
            "mode": "bring_your_own",
            "secret_reference": "vault://research/openai#api_key",
            "model": "gpt-4.1-mini",
            "approved_for_research": False,
            "monthly_budget_usd": 20,
            "per_request_budget_usd": 0.5,
        },
    )
    packet = service.llm_preflight_dry_run(actor=owner())
    assert packet["status"] == "blocked"
    assert "human_approval_required" in packet["blockers"]
    assert packet["external_llm_call_attempted"] is False


def test_human_control_rejects_inline_secrets_and_records_simulated_drills(db):
    service = HumanControlService(db)
    with pytest.raises(HumanControlError, match="inline secrets"):
        service.configure(actor=owner(), project_key="research_evidence", payload={"api_key": "sk-not-allowed"})
    with pytest.raises(HumanControlError, match="secret_reference"):
        service.configure(actor=owner(), project_key="research_evidence", payload={"mode": "bring_your_own", "secret_reference": "sk-not-allowed"})
    drill = service.run_drill(actor=owner(), project_key="controlled_pilot", scenario="kill_switch")
    assert drill["status"] == "simulated_passed"
    assert drill["counts_as_external_evidence"] is False
    assert drill["production_execution_allowed"] is False


def test_human_control_api_exposes_status_simulation_and_drills(client):
    initialized = client.post("/production/human-control/initialize")
    assert initialized.status_code == 200
    assert initialized.json()["human_control_implementation_pct"] == 100
    simulated = client.post("/production/human-control/data/simulate", json={"latency_ms": 180})
    assert simulated.status_code == 200
    assert simulated.json()["simulation"] is True
    drill = client.post("/production/human-control/projects/broker_sandbox/drills/partial_fill", json={"notes": "operator rehearsal"})
    assert drill.status_code == 200
    assert drill.json()["counts_as_external_evidence"] is False
    llm = client.post("/production/human-control/llm/preflight", json={"prompt": "safe local preflight"})
    assert llm.status_code == 200
    assert llm.json()["external_llm_call_attempted"] is False
    assert llm.json()["structured_validation"]["valid"] is True


def test_reference_eval_dataset_covers_financial_and_ai_task_categories(db):
    result = ResearchEvalDatasetService(db).seed_reference_dataset(actor=owner())
    assert result["total_cases"] == 100
    assert result["created"] == 100
    assert result["eval_domains"] == ["post_trade_review", "research", "risk_explanation", "thesis_capture", "thesis_monitor"]
    assert {"contradictory_facts", "stale_data", "prompt_injection", "mixed_language", "long_text", "unicode_whitespace"}.issubset(result["adversarial_classes"])
    assert result["real_model_runs"] == 0
    second = ResearchEvalDatasetService(db).seed_reference_dataset(actor=owner())
    assert second["created"] == 0


def test_eval_dataset_and_batch_are_available_through_formal_api(client):
    seeded = client.post("/production/research/eval-dataset/seed", json={"dataset_version": "api-eval-v1"})
    assert seeded.status_code == 201
    assert seeded.json()["total_cases"] == 100
    cases = client.get("/production/research/eval-cases?dataset_version=api-eval-v1&limit=200")
    assert cases.status_code == 200
    assert len(cases.json()) == 100
    batch = client.post("/production/research/eval-batches/run", json={"provider": "openai", "dataset_version": "api-eval-v1", "limit": 2})
    assert batch.status_code == 200
    assert batch.json()["attempted"] == 2
    assert batch.json()["failed"] == 2


def test_configured_mock_provider_is_available_to_thesis_workflow(client, trusted_snapshot_factory):
    snapshot_id = trusted_snapshot_factory("configured-thesis-snapshot")
    client.post("/production/human-control/initialize")
    asset = client.post(
        "/assets",
        json={"symbol": "NVDA", "name": "NVIDIA", "asset_type": "stock", "market": "US", "venue": "NASDAQ", "currency": "USD"},
    ).json()
    response = client.post(
        "/theses/capture",
        json={
            "user_id": "default-user",
            "asset_id": asset["id"],
            "data_snapshot_id": snapshot_id,
            "user_rationale": "Data-center growth remains the core driver.",
            "intended_action": "review",
            "current_position": {},
            "market_context": {"key_drivers": ["data-center growth"]},
            "provider": "configured",
        },
    )
    assert response.status_code == 201
    assert response.json()["source"] == "configured_ai_thesis_capture"
