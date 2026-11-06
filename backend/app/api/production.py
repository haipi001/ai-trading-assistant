from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request, Response
from fastapi import Header, Query
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.core.auth import AuthenticatedUser
from app.core.auth import get_current_user
from app.core.auth import require_permission
from app.core.config import get_settings
from app.core.local_secrets import LocalSecretError
from app.core.local_secrets import delete_user_secret
from app.core.local_secrets import list_user_secret_names
from app.core.local_secrets import set_user_secret
from app.db.session import get_db
from app.services.broker_sandbox import BrokerSandboxProofError
from app.services.broker_sandbox import BrokerSandboxProofService
from app.services.beta_support import BetaSupportError
from app.services.beta_support import BetaSupportService
from app.services.beta_analytics import BetaAnalyticsError
from app.services.beta_analytics import BetaAnalyticsService
from app.services.human_control import HumanControlError
from app.services.human_control import HumanControlService
from app.services.product_completion import ProductCompletionError
from app.services.product_completion import ProductCompletionService
from app.services.production_foundation import ManagedAuthService
from app.services.production_foundation import ProductionFoundationError
from app.services.production_foundation import ProductionFoundationService
from app.services.red_team import RedTeamError
from app.services.red_team import RedTeamSafetyService
from app.services.research_evals import ResearchEvalDatasetService
from app.services.research_evals import ResearchEvalError
from app.services.ops_readiness import OpsReadinessService
from app.services.privacy_center import PrivacyCenterError
from app.services.privacy_center import PrivacyCenterService


router = APIRouter(prefix="/production", tags=["production-foundation"])


def production_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-AI-Trading-User"),
    x_role: str | None = Header(default=None, alias="X-AI-Trading-Role"),
    x_beta_token: str | None = Header(default=None, alias="X-Beta-Access-Token"),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    settings = get_settings()
    try:
        if settings.managed_auth_required:
            if not authorization or not authorization.startswith("Bearer "):
                raise ProductionFoundationError("managed session bearer token is required")
            return ManagedAuthService(db).authenticate(authorization.removeprefix("Bearer ").strip())
        return get_current_user(x_user_id=x_user_id, x_role=x_role, x_beta_token=x_beta_token)
    except (ProductionFoundationError, HTTPException) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/auth/login")
def managed_login(payload: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return ManagedAuthService(db).login(str(payload.get("access_token") or ""))
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/auth/logout")
def managed_logout(payload: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return ManagedAuthService(db).revoke(str(payload.get("session_token") or ""))
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/secrets/verify")
def verify_secret(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        if "secrets:write" not in actor.permissions:
            raise ProductionFoundationError("missing permission: secrets:write")
        return ProductionFoundationService(db).verify_secret_reference(user_id=actor.user_id, reference=str(payload.get("reference") or ""), purpose=str(payload.get("purpose") or "general"))
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/readiness")
def production_readiness(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).readiness(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/privacy")
def privacy_status(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return PrivacyCenterService(db).status(actor=actor)
    except PrivacyCenterError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/privacy/export", status_code=201)
def privacy_export(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return PrivacyCenterService(db).export(actor=actor)
    except PrivacyCenterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/privacy/deletion-request", status_code=201)
def privacy_deletion_request(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return PrivacyCenterService(db).request_deletion(actor=actor, confirmation=str(payload.get("confirmation") or ""))
    except PrivacyCenterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/privacy/deletion-request/cancel")
def privacy_deletion_cancel(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return PrivacyCenterService(db).cancel_deletion(actor=actor)
    except PrivacyCenterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/privacy/deletion-request/execute")
def privacy_deletion_execute(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return PrivacyCenterService(db).execute_deletion(
            actor=actor,
            confirmation=str(payload.get("confirmation") or ""),
            nonce=str(payload.get("verification_nonce") or ""),
        )
    except PrivacyCenterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/support/tickets", status_code=201)
def create_support_ticket(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaSupportService(db).create(actor=actor, payload=payload)
    except BetaSupportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/support/tickets")
def list_support_tickets(status: str | None = None, limit: int = 50, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> list[dict]:
    try:
        return BetaSupportService(db).list(actor=actor, status=status, limit=limit)
    except BetaSupportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/support/tickets/{ticket_id}")
def get_support_ticket(ticket_id: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaSupportService(db).get(actor=actor, ticket_id=ticket_id)
    except BetaSupportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/support/tickets/{ticket_id}/replies")
def reply_support_ticket(ticket_id: str, payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaSupportService(db).reply(actor=actor, ticket_id=ticket_id, message=str(payload.get("message") or ""))
    except BetaSupportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/support/tickets/{ticket_id}")
def transition_support_ticket(ticket_id: str, payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaSupportService(db).transition(actor=actor, ticket_id=ticket_id, payload=payload)
    except BetaSupportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/support/operator-queue")
def support_operator_queue(limit: int = 100, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> list[dict]:
    try:
        return BetaSupportService(db).operator_queue(actor=actor, limit=limit)
    except BetaSupportError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/support/operator-metrics")
def support_operator_metrics(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaSupportService(db).operator_metrics(actor=actor)
    except BetaSupportError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/beta-profile")
def beta_profile(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaAnalyticsService(db).profile(actor=actor)
    except BetaAnalyticsError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/beta-profile")
def save_beta_profile(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaAnalyticsService(db).save_profile(actor=actor, payload=payload)
    except BetaAnalyticsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/beta-analytics")
def beta_analytics(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BetaAnalyticsService(db).metrics(actor=actor)
    except BetaAnalyticsError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/acceptance")
def production_acceptance(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).acceptance_program(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/acceptance/external-evidence-packet", status_code=201)
def create_external_evidence_packet(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).external_evidence_packet(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/human-control/initialize")
def initialize_human_controls(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).initialize(actor=actor)
    except HumanControlError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/product-completion/initialize")
def initialize_product_completion(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).initialize(actor=actor)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/product-completion/status")
def product_completion_status(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).status(actor=actor)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/product-completion/scheduler/tick")
def run_product_scheduler_tick(payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).scheduler_tick(actor=actor, action=(payload or {}).get("action"))
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/product-completion/ledger/cash")
def record_multi_currency_cash(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).record_cash_ledger_entry(actor=actor, payload=payload)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/product-completion/ledger/corporate-actions")
def normalize_product_corporate_action(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).normalize_corporate_action(actor=actor, payload=payload)
    except (ProductCompletionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/product-completion/data/version/{snapshot_id}")
def version_data_snapshot(snapshot_id: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).version_snapshot(actor=actor, snapshot_id=snapshot_id)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/product-completion/data/replay/{snapshot_id}")
def replay_data_snapshot(snapshot_id: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).replay_snapshot(actor=actor, snapshot_id=snapshot_id)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/product-completion/risk/report")
def product_risk_report(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).portfolio_risk_report(actor=actor)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/product-completion/usage/{metric}")
def record_product_usage(metric: str, payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).record_usage(actor=actor, metric=metric, quantity=int((payload or {}).get("quantity") or 1))
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/product-completion/checkout/test")
def create_product_test_checkout(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).create_test_checkout(actor=actor, plan=str(payload.get("plan") or "private_beta"))
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/product-completion/support-tickets", status_code=201)
def create_product_support_ticket(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).create_support_ticket(actor=actor, payload=payload)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/product-completion/incident-drills/{scenario}")
def run_product_incident_drill(scenario: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductCompletionService(db).incident_drill(actor=actor, scenario=scenario)
    except ProductCompletionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/human-control/status")
def human_control_status(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).status(actor=actor)
    except HumanControlError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/human-control/projects/{project_key}")
def configure_human_control_project(project_key: str, payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).configure(actor=actor, project_key=project_key, payload=payload)
    except HumanControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/human-control/llm/preflight")
def llm_preflight_dry_run(payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).llm_preflight_dry_run(actor=actor, prompt=str((payload or {}).get("prompt") or ""))
    except HumanControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/human-control/llm/credentials", status_code=201)
def import_llm_credentials(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).set_llm_credentials(actor=actor, payload=payload)
    except HumanControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/human-control/llm/chat/status")
def research_chat_status(response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return HumanControlService(db).research_chat_status(actor=actor)
    except HumanControlError:
        raise HTTPException(403, detail={"code": "ai_permission_required"}) from None


@router.get("/human-control/llm/chat/news-context/{snapshot_id}")
def research_news_snapshot(snapshot_id: str, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return HumanControlService(db).research_news_snapshot(actor=actor, snapshot_id=snapshot_id)
    except HumanControlError:
        raise HTTPException(404, detail={"code":"news_context_not_found"}) from None


@router.get("/human-control/llm/chat/market-context/{snapshot_id}")
def research_market_snapshot(snapshot_id: str, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return HumanControlService(db).research_market_snapshot(actor=actor,snapshot_id=snapshot_id)
    except HumanControlError:
        raise HTTPException(404,detail={"code":"market_context_not_found"}) from None


@router.get("/human-control/llm/chat/onchain-contexts")
def research_onchain_history(wallet_id: str = Query(min_length=1,max_length=128), chain_id: str = Query(pattern=r"^[1-9][0-9]{0,19}$"), contract_address: str = Query(default="",pattern=r"^(0x[0-9a-fA-F]{40})?$"), actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    if not wallet_id or len(wallet_id)>128 or len(chain_id)>20 or len(contract_address)>42:
        raise HTTPException(422,detail={"code":"ai_onchain_invalid"})
    return HumanControlService(db).research_onchain_history(actor=actor,wallet_id=wallet_id,chain_id=chain_id,contract_address=contract_address)


@router.get("/human-control/llm/chat/onchain-context/{snapshot_id}")
def research_onchain_snapshot(snapshot_id: str, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return HumanControlService(db).research_onchain_snapshot(actor=actor,snapshot_id=snapshot_id)
    except HumanControlError:
        raise HTTPException(404,detail={"code":"onchain_context_not_found"}) from None


@router.post("/human-control/llm/chat")
async def research_chat(request: Request, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    import json
    from starlette.concurrency import run_in_threadpool
    response.headers["Cache-Control"] = "no-store"
    try:
        raw = await request.body()
        if len(raw) > 200000:
            raise ValueError()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) - {"question", "page", "symbol", "history", "response_style", "include_news", "market_context", "onchain_context"}:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, detail={"code": "ai_question_invalid"}) from None
    try:
        return await run_in_threadpool(HumanControlService(db).research_chat, actor=actor, payload=payload)
    except HumanControlError as exc:
        code = "ai_permission_required" if "permission" in str(exc) else "ai_question_invalid"
        raise HTTPException(403 if code == "ai_permission_required" else 422, detail={"code": code}) from None


@router.post("/human-control/llm/test-call")
def llm_user_key_test_call(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).llm_test_call(actor=actor)
    except HumanControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/local-secrets")
def list_local_secrets(actor: AuthenticatedUser = Depends(production_user)) -> dict:
    if "readiness:read" not in actor.permissions:
        raise HTTPException(status_code=403, detail="missing permission: readiness:read")
    return {"secrets": list_user_secret_names(), "values_returned": False}


@router.post("/local-secrets", status_code=201)
def set_local_secret(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    if "readiness:write" not in actor.permissions:
        raise HTTPException(status_code=403, detail="missing permission: readiness:write")
    try:
        reference = set_user_secret(str(payload.get("name") or ""), str(payload.get("value") or ""))
    except LocalSecretError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    name = reference.removeprefix("env://")
    write_audit_log(db, action="local_secret.stored", entity_type="LocalSecret", entity_id=name, payload_json={"name": name, "contains_secret": False}, actor_id=actor.user_id)
    db.commit()
    return {"name": name, "reference": reference, "value_returned": False}


@router.delete("/local-secrets/{name}")
def delete_local_secret(name: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    if "readiness:write" not in actor.permissions:
        raise HTTPException(status_code=403, detail="missing permission: readiness:write")
    existed = delete_user_secret(name)
    write_audit_log(db, action="local_secret.deleted", entity_type="LocalSecret", entity_id=name.upper(), payload_json={"name": name.upper(), "existed": existed, "contains_secret": False}, actor_id=actor.user_id)
    db.commit()
    return {"name": name.upper(), "deleted": existed}


@router.post("/human-control/data/simulate")
def simulate_readonly_data(payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).run_simulated_data_sync(actor=actor, latency_ms=int((payload or {}).get("latency_ms") or 120))
    except HumanControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/human-control/data/stability")
def simulated_data_stability(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).data_stability(actor=actor)
    except HumanControlError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/human-control/projects/{project_key}/drills/{scenario}")
def run_human_control_drill(project_key: str, scenario: str, payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return HumanControlService(db).run_drill(actor=actor, project_key=project_key, scenario=scenario, notes=str((payload or {}).get("notes") or ""))
    except HumanControlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/acceptance/evidence/{stage_key}")
def record_acceptance_evidence(stage_key: str, payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).record_acceptance_evidence(actor=actor, stage_key=stage_key, evidence=payload)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/invitations", status_code=201)
def create_invitation(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).record_invitation(actor=actor, invitee_id=str(payload.get("invitee_id") or ""), role=str(payload.get("role") or "viewer"))
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/invitations/me")
def invitation_status(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    return ProductionFoundationService(db).invitation_status(actor=actor)


@router.get("/invitations")
def list_invitations(status: str | None = None, limit: int = 100, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).list_invitations(actor=actor, status=status, limit=limit)
    except ProductionFoundationError as exc:
        denied = "permission" in str(exc) or "operator role" in str(exc)
        raise HTTPException(status_code=403 if denied else 422, detail=str(exc)) from exc


@router.post("/invitations/accept")
def accept_invitation(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).accept_invitation(actor=actor, code=str(payload.get("invite_code") or ""))
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/invitations/{invitee_id}/revoke")
def revoke_invitation(invitee_id: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).revoke_invitation(actor=actor, invitee_id=invitee_id)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/activation/events", status_code=201)
def record_activation(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).record_activation(actor=actor, event_name=str(payload.get("event_name") or ""), metadata=payload.get("metadata") or {})
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/activation/funnel")
def activation_funnel(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).activation_funnel(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/pricing")
def set_pricing(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).set_pricing(actor=actor, config=payload)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/data-room", status_code=201)
def create_data_room(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        artifact = ProductionFoundationService(db).create_data_room(actor=actor)
        return {"id": artifact.id, "status": artifact.status, "summary": artifact.summary_json}
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/data-room/{artifact_id}/download")
def download_data_room(artifact_id: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).get_data_room(actor=actor, artifact_id=artifact_id)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/commercial-loop/rehearsal-packet")
def create_commercial_loop_rehearsal_packet(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).commercial_loop_rehearsal_packet(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/slo")
def slo_report(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).slo_report(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/retention")
def retention_status(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).retention_status(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/retention")
def configure_retention(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).configure_retention(actor=actor, payload=payload)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/retention/apply")
def apply_retention(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).apply_retention(actor=actor, confirmation=str(payload.get("confirmation") or ""))
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/restore-drill", status_code=201)
def restore_drill(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    if "backups:write" not in actor.permissions:
        raise HTTPException(status_code=403, detail="missing permission: backups:write")
    return OpsReadinessService(db).restore_drill(user_id=actor.user_id)


@router.post("/research/eval-cases", status_code=201)
def add_research_eval_case(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ResearchEvalDatasetService(db).add_case(actor=actor, payload=payload)
    except ResearchEvalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/research/eval-dataset/seed", status_code=201)
def seed_research_eval_dataset(payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ResearchEvalDatasetService(db).seed_reference_dataset(actor=actor, dataset_version=str((payload or {}).get("dataset_version") or "reference-v1"))
    except ResearchEvalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/research/eval-cases/{case_id}/run")
def run_research_eval_case(case_id: str, payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        provider_name = str((payload or {}).get("provider_name") or "openai")
        return ResearchEvalDatasetService(db).run_case(actor=actor, case_id=case_id, provider_name=provider_name)
    except (ResearchEvalError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/research/eval-summary")
def research_eval_summary(dataset_version: str | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ResearchEvalDatasetService(db).summary(actor=actor, dataset_version=dataset_version)
    except ResearchEvalError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/research/eval-results/{result_id}/label")
def label_research_eval_result(result_id: str, payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ResearchEvalDatasetService(db).label_result(actor=actor, result_id=result_id, labels=payload)
    except ResearchEvalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/research/eval-cases")
def list_research_eval_cases(dataset_version: str | None = None, limit: int = 200, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> list[dict]:
    try:
        return ResearchEvalDatasetService(db).list_cases(actor=actor, dataset_version=dataset_version, limit=limit)
    except ResearchEvalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/research/eval-batches/run")
def run_research_eval_batch(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ResearchEvalDatasetService(db).run_batch(
            actor=actor,
            provider_name=str(payload.get("provider") or ""),
            dataset_version=str(payload.get("dataset_version") or "reference-v1"),
            limit=int(payload.get("limit") or 10),
        )
    except ResearchEvalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/research/red-team/seed", status_code=201)
def seed_red_team_cases(payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return RedTeamSafetyService(db).seed_cases(actor=actor, dataset_version=str((payload or {}).get("dataset_version") or "red-team-v1"))
    except RedTeamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/research/red-team/run")
def run_red_team_cases(payload: dict | None = None, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return RedTeamSafetyService(db).run_all(actor=actor, dataset_version=str((payload or {}).get("dataset_version") or "red-team-v1"))
    except RedTeamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/pilot/evidence/{gate}")
def record_pilot_evidence(gate: str, payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).record_pilot_evidence(actor=actor, gate=gate, evidence=payload)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/pilot/readiness")
def pilot_readiness(actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ProductionFoundationService(db).pilot_readiness(actor=actor)
    except ProductionFoundationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/broker-sandbox/orders", status_code=201, dependencies=[Depends(require_permission("trade:submit"))])
def submit_sandbox_order(payload: dict, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BrokerSandboxProofService(db).submit(actor=actor, order_draft_id=str(payload.get("order_draft_id") or ""), idempotency_key=str(payload.get("idempotency_key") or ""))
    except (BrokerSandboxProofError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/broker-sandbox/reconcile/{idempotency_key}")
def reconcile_sandbox_order(idempotency_key: str, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)) -> dict:
    try:
        return BrokerSandboxProofService(db).reconcile(actor=actor, idempotency_key=idempotency_key)
    except (BrokerSandboxProofError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
