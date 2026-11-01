import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.adapters.broker_sandbox import HttpSandboxBrokerAdapter
from app.adapters.broker_sandbox import SandboxBrokerError
from app.ai.providers import DeepSeekProvider
from app.ai.providers import OpenAIProvider
from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.core.config import Settings
from app.core.secrets import SecretManagerResolver
from app.core.secrets import SecretResolution
from app.db.base import Base
from app.models import DataSnapshot
from app.models import ExportArtifact
from app.models import OperationalEvent
from app.services.daily_use import DailyUseService
from app.services.daily_use import DailyUseError
from app.services.beta_analytics import BetaAnalyticsService
from app.services.privacy_center import PrivacyCenterService
from app.services.production_foundation import ManagedAuthService
from app.services.production_foundation import ProductionFoundationError
from app.services.production_foundation import ProductionFoundationService
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


def test_env_secret_resolver_never_returns_secret_in_verify(monkeypatch):
    monkeypatch.setenv("ATOS_TEST_SECRET", "sensitive-value")
    resolver = SecretManagerResolver(Settings())
    assert resolver.resolve("env://ATOS_TEST_SECRET").value == "sensitive-value"
    verified = resolver.verify("env://ATOS_TEST_SECRET")
    assert verified["resolved"] is True
    assert "sensitive-value" not in json.dumps(verified)


def test_openai_provider_requires_allowlist_and_returns_structured_output():
    settings = Settings(
        external_llm_calls_enabled=True,
        openai_api_key_ref="env://IGNORED",
        openai_model="gpt-4.1-mini",
        llm_provider_allowlist_raw="openai:gpt-4.1-mini",
    )

    class Resolver:
        def resolve(self, reference):
            return SecretResolution(reference=reference, backend="test", value="redacted-test-key")

    captured = {}

    def transport(payload, api_key):
        captured.update(payload)
        assert api_key == "redacted-test-key"
        return {
            "usage": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
            "output_text": json.dumps(
                {
                    "report_id": "real-snapshot-1",
                    "report_type": "single_asset_research",
                    "agent_name": "allowlisted",
                    "data_snapshot_id": "snapshot-1",
                    "input_facts": json.dumps({"symbol": "NVDA"}),
                    "summary": "Structured summary.",
                    "bullish_case": "Structured bullish case.",
                    "bearish_case": "Structured bearish case.",
                    "key_risks": ["Valuation"],
                    "suggested_action": "review_only",
                    "confidence": 0.61,
                    "evidence": json.dumps({"source": "snapshot-1"}),
                    "limitations": "Snapshot facts only.",
                }
            )
        }

    provider = OpenAIProvider(settings=settings, secret_resolver=Resolver(), transport=transport)
    result = provider.generate_report(
        report_type="single_asset_research",
        agent_name="allowlisted",
        data_snapshot_id="snapshot-1",
        input_facts={"symbol": "NVDA"},
        prompt_template="Use structured facts.",
    )
    assert json.loads(result)["suggested_action"] == "review_only"
    assert captured["text"]["format"]["strict"] is True
    schema=captured["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"])==set(schema["properties"])
    assert schema["properties"]["input_facts"]["type"]=="string"
    assert json.loads(result)["input_facts"]=={"symbol":"NVDA"}
    assert json.loads(result)["evidence"]=={"source":"snapshot-1"}
    assert provider.last_usage == {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150, "provider_reported": True}


def test_deepseek_provider_requires_allowlist_and_returns_structured_output():
    settings = Settings(
        external_llm_calls_enabled=True,
        deepseek_api_key_ref="env://IGNORED",
        deepseek_model="deepseek-chat",
        llm_provider_allowlist_raw="deepseek:deepseek-chat",
    )

    class Resolver:
        def resolve(self, reference):
            return SecretResolution(reference=reference, backend="test", value="redacted-test-key")

    captured = {}

    def transport(payload, api_key):
        captured.update(payload)
        assert api_key == "redacted-test-key"
        tool_name = payload["tool_choice"]["name"]
        return {
            "usage": {"input_tokens": 90, "output_tokens": 20},
            "content": [
                {
                    "type": "tool_use",
                    "name": tool_name,
                    "input": {
                        "report_id": "real-snapshot-1",
                        "report_type": "single_asset_research",
                        "agent_name": "allowlisted",
                        "data_snapshot_id": "snapshot-1",
                        "input_facts": {"symbol": "NVDA"},
                        "summary": "Structured summary.",
                        "bullish_case": "Structured bullish case.",
                        "bearish_case": "Structured bearish case.",
                        "key_risks": ["Valuation"],
                        "suggested_action": "review_only",
                        "confidence": 0.61,
                        "evidence": {"source": "snapshot-1"},
                        "limitations": "Snapshot facts only.",
                    },
                }
            ]
        }

    provider = DeepSeekProvider(settings=settings, secret_resolver=Resolver(), transport=transport)
    result = provider.generate_report(
        report_type="single_asset_research",
        agent_name="allowlisted",
        data_snapshot_id="snapshot-1",
        input_facts={"symbol": "NVDA"},
        prompt_template="Use structured facts.",
    )
    assert json.loads(result)["suggested_action"] == "review_only"
    assert captured["tool_choice"] == {"type": "tool", "name": "emit_research_report"}
    assert captured["thinking"] == {"type":"disabled"}
    assert provider.last_usage == {"input_tokens": 90, "output_tokens": 20, "total_tokens": 110, "provider_reported": True}


def test_deepseek_provider_rejects_model_outside_allowlist():
    settings = Settings(
        external_llm_calls_enabled=True,
        deepseek_api_key_ref="env://IGNORED",
        deepseek_model="deepseek-chat",
        llm_provider_allowlist_raw="openai:gpt-4.1-mini",
    )

    class Resolver:
        def resolve(self, reference):
            return SecretResolution(reference=reference, backend="test", value="redacted-test-key")

    provider = DeepSeekProvider(settings=settings, secret_resolver=Resolver(), transport=lambda payload, api_key: {})
    with pytest.raises(ValueError, match="allowlist"):
        provider.generate_report(
            report_type="single_asset_research",
            agent_name="blocked",
            data_snapshot_id="snapshot-1",
            input_facts={"symbol": "NVDA"},
            prompt_template="Use structured facts.",
        )


def test_optional_pricing_rates_accept_blank_managed_environment_values():
    settings = Settings(
        OPENAI_INPUT_COST_PER_MILLION_USD="",
        OPENAI_OUTPUT_COST_PER_MILLION_USD="",
        DEEPSEEK_INPUT_COST_PER_MILLION_USD="",
        DEEPSEEK_OUTPUT_COST_PER_MILLION_USD="",
    )
    assert settings.openai_input_cost_per_million_usd is None
    assert settings.openai_output_cost_per_million_usd is None
    assert settings.deepseek_input_cost_per_million_usd is None
    assert settings.deepseek_output_cost_per_million_usd is None


def test_managed_oidc_session_can_be_revoked(db, monkeypatch):
    monkeypatch.setenv("ATOS_SESSION_KEY", "long-session-signing-secret")
    settings = Settings(
        oidc_issuer="https://identity.example.test",
        oidc_userinfo_url="https://identity.example.test/userinfo",
        oidc_client_id="ai-trading-os",
        auth_session_secret_ref="env://ATOS_SESSION_KEY",
    )
    service = ManagedAuthService(
        db,
        settings,
        transport=lambda _: {"sub": "managed-user", "iss": settings.oidc_issuer, "aud": settings.oidc_client_id, "role": "operator", "email_verified": True},
    )
    login = service.login("provider-access-token-not-stored")
    current = service.authenticate(login["session_token"])
    assert current.user_id == "managed-user"
    assert current.role == "operator"
    service.revoke(login["session_token"])
    with pytest.raises(ProductionFoundationError, match="revoked"):
        service.authenticate(login["session_token"])


def test_managed_oidc_can_require_preissued_invitation(db, monkeypatch):
    monkeypatch.setenv("ATOS_SESSION_KEY", "long-session-signing-secret")
    settings = Settings(
        managed_auth_invitation_required=True,
        oidc_issuer="https://identity.example.test",
        oidc_userinfo_url="https://identity.example.test/userinfo",
        oidc_client_id="ai-trading-os",
        auth_session_secret_ref="env://ATOS_SESSION_KEY",
    )
    service = ManagedAuthService(
        db,
        settings,
        transport=lambda _: {"sub": "unknown-user", "iss": settings.oidc_issuer, "aud": settings.oidc_client_id, "role": "owner"},
    )
    with pytest.raises(ProductionFoundationError, match="valid invitation"):
        service.login("provider-token")


def test_invitation_activation_data_room_and_pilot_evidence(db):
    actor = owner()
    service = ProductionFoundationService(db)
    invite = service.record_invitation(actor=actor, invitee_id="beta-user", role="viewer")
    assert invite["shown_once"] is True
    invitee = AuthenticatedUser(user_id="beta-user", role="viewer", permissions=ROLE_PERMISSIONS["viewer"], auth_required=True, token_configured=True)
    status = service.invitation_status(actor=invitee)
    assert status["onboarding_required"] is True
    accepted = service.accept_invitation(actor=invitee, code=invite["invite_code"])
    assert accepted["status"] == "active"
    assert accepted["next_route"] == "/settings"
    with pytest.raises(ProductionFoundationError, match="active invitation not found"):
        service.accept_invitation(actor=invitee, code=invite["invite_code"])
    supplemental = service.record_activation(actor=actor, event_name="daily_open")
    assert supplemental["supplemental_only"] is True
    funnel = service.activation_funnel(actor=actor)
    assert funnel["counts"].get("daily_open", 0) == 0
    assert funnel["counts"]["invite_accepted"] == 1
    assert funnel["manual_events_excluded"] is True
    service.set_pricing(actor=actor, config={"plan": "private_beta", "monthly_price": 49})
    data_room = service.create_data_room(actor=actor)
    assert service.get_data_room(actor=actor, artifact_id=data_room.id)["payload"]["redacted"] is True

    for gate in service.PILOT_GATES:
        service.record_pilot_evidence(
            actor=actor,
            gate=gate,
            evidence={"artifact_ref": f"artifact://pilot/{gate}", "reviewer": "human-reviewer", "verified_at": "2026-06-20T10:00:00Z"},
        )
    readiness = service.pilot_readiness(actor=actor)
    assert readiness["human_small_pilot_review_allowed"] is True
    assert readiness["pilot_approved"] is False
    assert readiness["production_execution_allowed"] is False


def test_invitation_rejects_bad_codes_and_can_be_revoked(db):
    service = ProductionFoundationService(db, Settings(invitation_max_attempts=2))
    invite = service.record_invitation(actor=owner(), invitee_id="locked-user", role="viewer")
    invitee = AuthenticatedUser(user_id="locked-user", role="viewer", permissions=ROLE_PERMISSIONS["viewer"], auth_required=True, token_configured=True)
    with pytest.raises(ProductionFoundationError, match="invalid or locked"):
        service.accept_invitation(actor=invitee, code="wrong-one")
    with pytest.raises(ProductionFoundationError, match="invalid or locked"):
        service.accept_invitation(actor=invitee, code="wrong-two")
    with pytest.raises(ProductionFoundationError, match="locked"):
        service.accept_invitation(actor=invitee, code=invite["invite_code"])
    service.record_invitation(actor=owner(), invitee_id="locked-user", role="operator")
    revoked = service.revoke_invitation(actor=owner(), invitee_id="locked-user")
    assert revoked["status"] == "revoked"
    with pytest.raises(ProductionFoundationError, match="active invitation not found"):
        service.accept_invitation(actor=invitee, code=invite["invite_code"])


def test_invitation_operator_list_is_sanitized_and_permissioned(db):
    service = ProductionFoundationService(db)
    created = service.record_invitation(actor=owner(), invitee_id="queue-user", role="viewer")
    report = service.list_invitations(actor=owner())
    assert report["counts"]["invited"] == 1
    assert report["raw_codes_included"] is False
    assert report["external_messages_sent"] is False
    assert report["items"][0]["invitee_id"] == "queue-user"
    assert created["invite_code"] not in json.dumps(report)
    viewer = AuthenticatedUser(user_id="viewer", role="viewer", permissions=ROLE_PERMISSIONS["viewer"], auth_required=True, token_configured=True)
    with pytest.raises(ProductionFoundationError, match="operator role"):
        service.list_invitations(actor=viewer)


def test_verified_activation_events_come_from_real_daily_workflow_and_are_idempotent(db):
    daily = DailyUseService(db)
    daily.initialize_local_start(user_id="workflow-user", payload={
        "data_mode": "simulation",
        "risk_boundary_acknowledged": True,
        "daily_review_time": "20:30",
        "workspace_goal": "verify real activation",
    })
    daily.daily_open(user_id="workflow-user")
    daily.daily_open(user_id="workflow-user")
    events = list(db.scalars(select(OperationalEvent).where(OperationalEvent.user_id == "workflow-user", OperationalEvent.event_type.like("activation.%"))).all())
    assert [event.event_type for event in events].count("activation.onboarding_completed") == 1
    assert [event.event_type for event in events].count("activation.daily_open") == 1
    assert all(event.source == "daily_use" for event in events)
    assert all(event.payload_json["verified_business_event"] is True for event in events)
    funnel = ProductionFoundationService(db).activation_funnel(actor=owner())
    assert funnel["counts"]["onboarding_completed"] == 1
    assert funnel["counts"]["daily_open"] == 1


def test_managed_private_beta_first_run_requires_current_consent_and_icp(db):
    settings = Settings(managed_auth_required=True, managed_auth_invitation_required=True)
    daily = DailyUseService(db, settings)
    payload = {"data_mode": "simulation", "risk_boundary_acknowledged": True, "daily_review_time": "20:30"}
    gate = daily.local_start_status(user_id="beta-entry-user")["beta_entry_gate"]
    assert gate["status"] == "blocked"
    with pytest.raises(DailyUseError, match="private Beta terms"):
        daily.initialize_local_start(user_id="beta-entry-user", payload=payload)
    BetaAnalyticsService(db, settings).save_profile(actor=AuthenticatedUser(
        user_id="beta-entry-user", role="viewer", permissions=ROLE_PERMISSIONS["viewer"], auth_required=True, token_configured=True,
    ), payload={
        "holds_us_equity_or_etf": True, "holds_crypto": True, "thesis_driven": True, "self_directed": True,
        "private_beta_consent": True, "risk_disclosure_acknowledged": True,
        "consent_action": BetaAnalyticsService.CONSENT_ACTION,
        "beta_terms_version": BetaAnalyticsService.TERMS_VERSION,
        "privacy_policy_version": PrivacyCenterService.POLICY_VERSION,
    })
    assert daily.local_start_status(user_id="beta-entry-user")["beta_entry_gate"]["status"] == "ready"
    assert daily.initialize_local_start(user_id="beta-entry-user", payload=payload)["initialized"] is True


def test_research_eval_dataset_persists_versioned_case(db):
    snapshot = DataSnapshot(snapshot_type="research_eval", data_json={"symbol": "NVDA"}, metadata_json={"source": "test"})
    db.add(snapshot)
    db.commit()
    case = ResearchEvalDatasetService(db).add_case(
        actor=owner(),
        payload={
            "dataset_version": "2026-06-v1",
            "case_key": "nvda-structured-001",
            "report_type": "single_asset_research",
            "data_snapshot_id": snapshot.id,
            "input_facts": {"symbol": "NVDA"},
            "expected": {"suggested_action": "review_only"},
        },
    )
    assert case["dataset_version"] == "2026-06-v1"
    assert ResearchEvalDatasetService(db).summary(actor=owner(), dataset_version="2026-06-v1")["cases"] == 1


def test_research_eval_run_case_accepts_natural_language_review_only_action(db, monkeypatch):
    """Regression test: run_case() used to require suggested_action to exactly equal the literal
    string "review_only". Only MockAIProvider emits that literal; any real LLM writes a natural
    sentence, which made every real-provider eval run fail regardless of output quality."""

    class NaturalLanguageProvider:
        def generate_report(self, *, report_type, agent_name, data_snapshot_id, input_facts, prompt_template):
            return json.dumps(
                {
                    "report_id": "nl-1",
                    "report_type": report_type,
                    "agent_name": agent_name,
                    "data_snapshot_id": data_snapshot_id,
                    "input_facts": input_facts,
                    "summary": "Structured summary.",
                    "bullish_case": "Structured bullish case.",
                    "bearish_case": "Structured bearish case.",
                    "key_risks": ["Valuation"],
                    "suggested_action": "Hold / Monitor - insufficient data for a directional call.",
                    "confidence": 0.4,
                    "evidence": {"source": data_snapshot_id},
                    "limitations": "Snapshot facts only.",
                }
            )

    monkeypatch.setattr("app.services.reports.OpenAIProvider", NaturalLanguageProvider)

    snapshot = DataSnapshot(snapshot_type="research_eval", data_json={"symbol": "NVDA"}, metadata_json={"source": "test"})
    db.add(snapshot)
    db.commit()
    case = ResearchEvalDatasetService(db).add_case(
        actor=owner(),
        payload={
            "dataset_version": "2026-07-v1",
            "case_key": "nvda-natural-language-001",
            "report_type": "single_asset_research",
            "data_snapshot_id": snapshot.id,
            "input_facts": {"symbol": "NVDA"},
            "expected": {"suggested_action": "review_only"},
        },
    )
    result = ResearchEvalDatasetService(db).run_case(actor=owner(), case_id=case["id"], provider_name="openai")
    assert result["checks"]["suggested_action"] is True
    assert result["passed"] is True


def test_sandbox_adapter_rejects_production_host(monkeypatch):
    settings = Settings(sandbox_broker_base_url="https://api.broker.example.com", sandbox_broker_token_ref="env://BROKER_TOKEN")
    with pytest.raises(SandboxBrokerError, match="sandbox/paper/testnet"):
        HttpSandboxBrokerAdapter(settings)


def test_production_api_commercial_and_pilot_paths_remain_review_only(client):
    invite = client.post("/production/invitations", json={"invitee_id": "api-beta-user", "role": "viewer"})
    assert invite.status_code == 201
    assert invite.json()["status"] == "invited"
    code = invite.json()["invite_code"]
    invited_status = client.get("/production/invitations/me", headers={"X-AI-Trading-User": "api-beta-user", "X-AI-Trading-Role": "viewer"})
    assert invited_status.json()["onboarding_required"] is True
    accepted = client.post("/production/invitations/accept", json={"invite_code": code}, headers={"X-AI-Trading-User": "api-beta-user", "X-AI-Trading-Role": "viewer"})
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "active"
    queue = client.get("/production/invitations")
    assert queue.status_code == 200
    assert queue.json()["raw_codes_included"] is False
    denied_queue = client.get("/production/invitations", headers={"X-AI-Trading-User": "viewer-user", "X-AI-Trading-Role": "viewer"})
    assert denied_queue.status_code == 403

    activation = client.post("/production/activation/events", json={"event_name": "daily_open", "metadata": {"source": "e2e"}})
    assert activation.status_code == 201
    assert activation.json()["supplemental_only"] is True
    funnel = client.get("/production/activation/funnel").json()
    assert funnel["counts"].get("daily_open", 0) == 0
    assert funnel["manual_events_excluded"] is True

    pricing = client.put("/production/pricing", json={"plan": "private_beta", "monthly_price": 49})
    assert pricing.status_code == 200
    assert pricing.json()["billing_enabled"] is False

    data_room = client.post("/production/data-room")
    assert data_room.status_code == 201
    download = client.get(f"/production/data-room/{data_room.json()['id']}/download")
    assert download.status_code == 200
    assert download.json()["payload"]["redacted"] is True

    readiness = client.get("/production/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["production_execution_allowed"] is False


def test_commercial_loop_rehearsal_packet_records_local_loop_without_external_access(client):
    response = client.post("/production/commercial-loop/rehearsal-packet")

    assert response.status_code == 200
    packet = response.json()
    assert packet["packet_type"] == "commercial_loop_rehearsal_packet"
    assert packet["artifact_id"]
    assert packet["packet_status"] == "ready_for_manual_review"
    assert packet["contains_secrets"] is False
    assert packet["email_sent"] is False
    assert packet["stripe_live_billing_enabled"] is False
    assert packet["billing_enabled"] is False
    assert packet["external_user_access_granted"] is False
    assert packet["execution_available"] is False
    assert packet["production_execution_allowed"] is False
    assert packet["steps"][0]["evidence"]["invite_code_redacted"] is True
    assert "invite_code" not in packet["steps"][0]["evidence"]
    assert packet["data_room_artifact_id"]
    assert packet["activation_funnel"]["counts"].get("invite_accepted", 0) == 0
    assert packet["activation_funnel"]["manual_events_excluded"] is True
    assert "no external email" in packet["safe_boundary"].lower()

    events = client.get("/beta/events?limit=50")
    assert events.status_code == 200
    assert any(item["event_type"] == "activation.invite_accepted" for item in events.json())


def test_eight_stage_acceptance_is_evidence_driven_and_never_enables_execution(db):
    service = ProductionFoundationService(db)
    actor = owner()
    acceptance = service.acceptance_program(actor=actor)
    assert acceptance["total_stages"] == 8
    assert [stage["key"] for stage in acceptance["stages"]] == list(service.ACCEPTANCE_STAGES)
    assert acceptance["production_execution_allowed"] is False
    assert acceptance["pilot_approved"] is False
    assert acceptance["status"] == "blocked"

    service.record_acceptance_evidence(
        actor=actor,
        stage_key="release_quality",
        evidence={
            "artifact_ref": "ci://run/quality-123",
            "reviewer": "release-owner",
            "verified_at": "2026-06-20T10:00:00Z",
            "cross_browser_verified": True,
            "failure_paths_verified": True,
            "accessibility_verified": True,
            "visual_regression_verified": True,
        },
    )
    updated = service.acceptance_program(actor=actor)
    release = next(stage for stage in updated["stages"] if stage["key"] == "release_quality")
    assert release["status"] == "verified"
    assert updated["status"] == "blocked"
    assert updated["production_execution_allowed"] is False


def test_external_evidence_packet_exports_blockers_without_unlocking_execution(db):
    service = ProductionFoundationService(db)
    packet = service.external_evidence_packet(actor=owner())
    assert packet["packet_type"] == "production_external_evidence_packet"
    assert packet["artifact_id"]
    assert packet["contains_secrets"] is False
    assert packet["production_execution_allowed"] is False
    assert packet["pilot_approved"] is False
    assert packet["external_evidence_required"] is True
    assert packet["missing_evidence"]
    assert "不会自动实盘" in packet["safe_boundaries"]

    artifact = db.get(ExportArtifact, packet["artifact_id"])
    assert artifact is not None
    assert artifact.export_type == "production_external_evidence_packet"
    assert artifact.summary_json["contains_secrets"] is False
    assert artifact.summary_json["production_execution_allowed"] is False


def test_acceptance_evidence_rejects_missing_proof_and_secrets(db):
    service = ProductionFoundationService(db)
    with pytest.raises(ProductionFoundationError, match="requires"):
        service.record_acceptance_evidence(actor=owner(), stage_key="release_quality", evidence={"artifact_ref": "ci://run/1"})
    with pytest.raises(ProductionFoundationError, match="must not contain secrets"):
        service.record_acceptance_evidence(
            actor=owner(),
            stage_key="release_quality",
            evidence={"artifact_ref": "ci://run/1", "reviewer": "owner", "verified_at": "now", "api_key": "forbidden"},
        )


def test_openai_wire_schema_closes_nested_objects_and_preserves_domain_dictionaries():
    from app.ai.providers import _closed_openai_schema, _openai_report_schema, _decode_openai_report_output
    schema=_openai_report_schema()
    assert set(schema['required'])==set(schema['properties'])
    assert schema['additionalProperties'] is False
    nested={'type':'object','properties':{'plan':{'type':'object','properties':{'label':{'type':'string'}}}}}
    closed=_closed_openai_schema(nested)
    assert closed['properties']['plan']['additionalProperties'] is False
    assert closed['properties']['plan']['required']==['label']
    assert 'additionalProperties' not in nested
    report={'report_id':'wire-test','report_type':'single_asset_research','agent_name':'wire','data_snapshot_id':'snapshot','input_facts':json.dumps({'nested':{'values':[1,True,None,'中文']}}),'summary':'Source claim [N1]','bullish_case':'Missing data','bearish_case':'Missing data','key_risks':['Risk'],'suggested_action':'Review evidence','confidence':0.1,'evidence':json.dumps({'news_citation_ids':['N1'],'other':{'source':'snapshot'}}),'limitations':'Review only'}
    result=json.loads(_decode_openai_report_output(json.dumps(report)))
    assert result['input_facts']['nested']['values']==[1,True,None,'中文']
    assert result['evidence']['news_citation_ids']==['N1']
    canonical=json.loads(_decode_openai_report_output(json.dumps(report), {'price':1}))
    assert canonical['input_facts']=={'price':1}
    report['evidence']='[]'
    with pytest.raises(ValueError):_decode_openai_report_output(json.dumps(report))
