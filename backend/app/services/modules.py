from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditLog
from app.models.core import utc_now


class ModuleRegistryError(ValueError):
    pass


class ModuleNotFoundError(ModuleRegistryError):
    pass


@dataclass(frozen=True)
class RegisteredModule:
    module_type: str
    name: str
    available: bool
    gate_compliant: bool
    details: str
    compliance_message: str


MODULES = [
    RegisteredModule(
        module_type="ai_sidecar_policy",
        name="AI Sidecar Policy",
        available=True,
        gate_compliant=True,
        details="Evaluates proposed AI/sidecar modules against local control-plane boundaries before integration.",
        compliance_message="Sidecars are policy-checked and cannot bypass gates, approvals, risk, behavior, or audit.",
    ),
    RegisteredModule(
        module_type="strategy_rules",
        name="Strategy Rules",
        available=True,
        gate_compliant=True,
        details="Rules are persisted as strategy metadata only; they do not create orders.",
        compliance_message="Registered as a metadata module with no execution capability.",
    ),
    RegisteredModule(
        module_type="backtest_lab",
        name="Backtest Lab",
        available=True,
        gate_compliant=True,
        details="Backtest runs can be recorded; engine execution is blocked until verified data contracts exist.",
        compliance_message="Fail-closed experiment shell; no paper or live orders are generated.",
    ),
    RegisteredModule(
        module_type="controlled_auto",
        name="Controlled Auto",
        available=False,
        gate_compliant=True,
        details="Controlled auto requests return readiness evaluations only and cannot execute.",
        compliance_message="Execution is blocked by design and requires future gate, risk, and approval proof.",
    ),
    RegisteredModule(
        module_type="broker_connections",
        name="Broker Connections",
        available=False,
        gate_compliant=True,
        details="Compatibility alias stores secret references only; broker health checks fail closed.",
        compliance_message="Registered without real broker submission capability.",
    ),
    RegisteredModule(
        module_type="read_only_data",
        name="Read-only Data",
        available=True,
        gate_compliant=True,
        details="Read-only adapters and import pipelines are allowed to feed data quality layers.",
        compliance_message="Data ingestion remains separate from order execution.",
    ),
]


def contract_check(key: str, label: str, status: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "evidence": evidence,
    }


class ModulesService:
    def __init__(self, db: Session | None = None):
        self.db = db
        self.settings = get_settings()

    def list_modules(self) -> list[dict]:
        return [{"module_type": module.module_type, "name": module.name} for module in MODULES]

    def health(self, module_type: str) -> dict:
        module = self._get_module(module_type)
        return {
            "module_type": module.module_type,
            "name": module.name,
            "available": module.available,
            "registered": True,
            "last_check": utc_now(),
            "details": module.details,
        }

    def gate_compliance(self, module_type: str) -> dict:
        module = self._get_module(module_type)
        return {
            "module_type": module.module_type,
            "registered": True,
            "gate_compliant": module.gate_compliant,
            "message": module.compliance_message,
        }

    def evaluate_sidecar_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        name = str(payload.get("name") or "").strip()
        sidecar_type = str(payload.get("sidecar_type") or "unknown").strip()
        if not name:
            blockers.append("sidecar_name_required")
        if not sidecar_type:
            blockers.append("sidecar_type_required")
        if payload.get("control_pattern") != "local_self_logic_to_sidecar_callback":
            blockers.append("invalid_control_pattern")
        if payload.get("creates_orders"):
            blockers.append("sidecar_must_not_create_orders")
        if payload.get("executes_trades") and not payload.get("post_approval_only"):
            blockers.append("execution_sidecar_requires_local_approval")
        if payload.get("stores_secrets"):
            blockers.append("sidecar_must_not_store_local_secrets")
        if payload.get("mutates_core_state"):
            blockers.append("sidecar_must_not_mutate_core_state")

        source_of_truth_for = {str(item).lower() for item in payload.get("source_of_truth_for") or []}
        prohibited_sources = {
            "self_logic",
            "approval",
            "approvals",
            "safety",
            "safety_policy",
            "risk",
            "decision_gates",
            "audit",
            "ledger",
        }
        for source in sorted(source_of_truth_for & prohibited_sources):
            blockers.append(f"sidecar_cannot_be_source_of_truth_for:{source}")

        capabilities = {str(item).lower() for item in payload.get("capabilities") or []}
        if "execution" in capabilities or payload.get("executes_trades"):
            warnings.append("execution_sidecar_requires_future_certification_and_local_approval")
        if payload.get("requires_external_calls") and not self.settings.external_llm_calls_enabled:
            warnings.append("external_calls_disabled_in_current_environment")
        if not capabilities:
            warnings.append("no_capabilities_declared")

        if blockers:
            status = "blocked"
        elif warnings:
            status = "review_required"
        else:
            status = "approved"
        response = {
            "name": name,
            "sidecar_type": sidecar_type,
            "status": status,
            "allowed": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "required_controls": [
                "typed_request_response_contract",
                "minimum_data_scope",
                "local_gates_before_sidecar",
                "local_approval_before_execution_sidecar",
                "local_audit_log_for_request_and_callback",
                "mock_or_disabled_mode_available",
                "fail_closed_on_uncertain_state",
            ],
            "execution_available": False,
            "real_broker_call_allowed": False,
            "audit_required": True,
        }
        if self.db is not None:
            self.db.add(
                AuditLog(
                    actor_type="system",
                    actor_id="modules-service",
                    action="sidecar_policy.evaluated",
                    entity_type="SidecarPolicy",
                    entity_id=name or "unnamed-sidecar",
                    payload_json=response | {"request": payload},
                )
            )
            self.db.commit()
        return response

    def sidecar_contract_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        policy = self.evaluate_sidecar_policy(payload)
        checks = [
            contract_check("policy", "Policy evaluation", "block" if policy["blockers"] else "warn" if policy["warnings"] else "ok", {"status": policy["status"]}),
            contract_check("typed_contract", "Typed request/response contract", "ok" if payload.get("request_schema") and payload.get("response_schema") else "warn", {"has_request_schema": bool(payload.get("request_schema")), "has_response_schema": bool(payload.get("response_schema"))}),
            contract_check("audit", "Audit callback", "ok" if payload.get("audit_callback") else "warn", {"audit_callback": payload.get("audit_callback")}),
            contract_check("control_plane", "Control plane boundary", "ok" if not policy["blockers"] else "block", {"required_controls": policy["required_controls"]}),
        ]
        if any(check["status"] == "block" for check in checks):
            status = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            status = "review_required"
        else:
            status = "contract_ready"
        response = {
            "name": policy["name"],
            "sidecar_type": policy["sidecar_type"],
            "status": status,
            "policy_status": policy["status"],
            "allowed_for_integration_review": status in {"contract_ready", "review_required"} and policy["allowed"],
            "blockers": policy["blockers"],
            "warnings": policy["warnings"],
            "required_controls": policy["required_controls"],
            "checks": checks,
            "execution_available": False,
            "real_broker_call_allowed": False,
            "mutates_core_state_allowed": False,
            "source_of_truth_allowed": False,
        }
        if self.db is not None:
            self.db.add(
                AuditLog(
                    actor_type="system",
                    actor_id="modules-service",
                    action="sidecar_contract.reported",
                    entity_type="SidecarContract",
                    entity_id=policy["name"] or "unnamed-sidecar",
                    payload_json=response | {"request": payload},
                )
            )
            self.db.commit()
        return response

    def _get_module(self, module_type: str) -> RegisteredModule:
        for module in MODULES:
            if module.module_type == module_type:
                return module
        raise ModuleNotFoundError("module not found")
