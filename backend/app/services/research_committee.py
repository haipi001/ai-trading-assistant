import json
from datetime import datetime
from datetime import timezone
from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError
from pydantic import field_validator
from sqlalchemy.orm import Session

from app.agents import BearResearcher
from app.agents import BullResearcher
from app.agents import CryptoOnchainAnalyst
from app.agents import FundamentalAnalyst
from app.agents import NewsAnalyst
from app.agents import PortfolioManager
from app.agents import ResearchAgent
from app.agents import RiskManager
from app.agents import TechnicalAnalyst
from app.ai.reports import ResearchReportOutput
from app.models import AgentRun
from app.models import AuditLog
from app.models import ResearchReport
from app.services.data_catalog import DataCatalogService


class InvalidAgentOutputError(ValueError):
    pass


class AgentOutput(BaseModel):
    agent_name: str
    role: str
    data_snapshot_id: str
    input_facts: dict[str, Any] = Field(default_factory=dict)
    findings: list[str]
    risks: list[str]
    confidence: float = Field(ge=0, le=1)
    limitations: str

    @field_validator("findings", "risks")
    @classmethod
    def require_items(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("field must contain at least one item")
        return value


class ResearchCommitteeResult(BaseModel):
    report: ResearchReport
    agent_runs: list[AgentRun]
    order_intent_id: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class ResearchCommitteeService:
    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        *,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        automation_level: str = "A0_READ_ONLY",
    ) -> ResearchCommitteeResult:
        DataCatalogService(self.db).require_trusted_snapshot(
            data_snapshot_id,
            decision_scope="research_committee",
        )
        agent_runs: list[AgentRun] = []
        analyst_outputs: list[dict[str, Any]] = []

        for agent in self._analysts():
            output, agent_run = self._run_agent(agent, data_snapshot_id=data_snapshot_id, input_facts=input_facts)
            analyst_outputs.append(output.model_dump())
            agent_runs.append(agent_run)

        debate_facts = {**input_facts, "analyst_outputs": analyst_outputs}
        debate_outputs: list[dict[str, Any]] = []
        for agent in [BullResearcher(), BearResearcher(), RiskManager(), PortfolioManager()]:
            output, agent_run = self._run_agent(agent, data_snapshot_id=data_snapshot_id, input_facts=debate_facts)
            debate_outputs.append(output.model_dump())
            agent_runs.append(agent_run)

        report = self._create_final_report(
            data_snapshot_id=data_snapshot_id,
            input_facts=input_facts,
            analyst_outputs=analyst_outputs,
            debate_outputs=debate_outputs,
            agent_runs=agent_runs,
            automation_level=automation_level,
        )
        self.db.commit()
        self.db.refresh(report)
        return ResearchCommitteeResult(report=report, agent_runs=agent_runs, order_intent_id=None)

    def _analysts(self) -> list[ResearchAgent]:
        return [
            FundamentalAnalyst(),
            TechnicalAnalyst(),
            NewsAnalyst(),
            CryptoOnchainAnalyst(),
        ]

    def _run_agent(
        self,
        agent: ResearchAgent,
        *,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
    ) -> tuple[AgentOutput, AgentRun]:
        agent_run = AgentRun(
            agent_name=agent.agent_name,
            run_type="multi_agent_research",
            status="running",
            input_snapshot_id=data_snapshot_id,
            output_json={},
        )
        self.db.add(agent_run)
        self.db.flush()

        try:
            raw_output = agent.run(data_snapshot_id=data_snapshot_id, input_facts=input_facts)
            output = self._validate_agent_output(raw_output, agent.agent_name, data_snapshot_id, input_facts)
        except InvalidAgentOutputError as exc:
            agent_run.status = "failed"
            agent_run.error_message = str(exc)
            agent_run.completed_at = now()
            self._write_audit_log(
                action="agent_run.invalid_output_rejected",
                entity_type="AgentRun",
                entity_id=agent_run.id,
                payload_json={"agent_name": agent.agent_name, "data_snapshot_id": data_snapshot_id, "error": str(exc)},
            )
            self.db.commit()
            raise

        agent_run.status = "completed"
        agent_run.output_json = output.model_dump()
        agent_run.completed_at = now()
        return output, agent_run

    def _validate_agent_output(
        self,
        raw_output: str | dict[str, Any],
        agent_name: str,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
    ) -> AgentOutput:
        if isinstance(raw_output, str):
            try:
                payload = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise InvalidAgentOutputError(f"{agent_name} returned invalid JSON") from exc
        else:
            payload = raw_output

        try:
            output = AgentOutput.model_validate(payload)
        except ValidationError as exc:
            raise InvalidAgentOutputError(f"{agent_name} output failed schema validation: {exc}") from exc

        if output.agent_name != agent_name:
            raise InvalidAgentOutputError(f"{agent_name} changed agent_name")
        if output.data_snapshot_id != data_snapshot_id:
            raise InvalidAgentOutputError(f"{agent_name} changed data_snapshot_id")
        if output.input_facts != input_facts:
            raise InvalidAgentOutputError(f"{agent_name} changed input_facts")

        return output

    def _create_final_report(
        self,
        *,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        analyst_outputs: list[dict[str, Any]],
        debate_outputs: list[dict[str, Any]],
        agent_runs: list[AgentRun],
        automation_level: str,
    ) -> ResearchReport:
        report_type = "single_asset_research" if input_facts.get("asset_id") else "portfolio_daily_review"
        risk_items = self._risks_from_outputs(debate_outputs)
        final_input_facts = {
            **input_facts,
            "agent_outputs": analyst_outputs + debate_outputs,
            "automation_level": automation_level,
        }
        final_payload = ResearchReportOutput(
            report_id=f"committee-{data_snapshot_id}",
            report_type=report_type,
            agent_name="ResearchCommittee",
            data_snapshot_id=data_snapshot_id,
            input_facts=final_input_facts,
            summary="Multi-agent research committee completed using structured input facts only.",
            bullish_case=self._findings_for("BullResearcher", debate_outputs),
            bearish_case=self._findings_for("BearResearcher", debate_outputs),
            key_risks=risk_items,
            suggested_action="review_only",
            confidence=self._average_confidence(analyst_outputs + debate_outputs),
            evidence={
                "agent_run_ids": [agent_run.id for agent_run in agent_runs],
                "agent_names": [agent_run.agent_name for agent_run in agent_runs],
                "order_intent_created": False,
            },
            limitations="No external data, execution adapter, broker, exchange, or wallet call was made.",
        )

        report = ResearchReport(
            report_type=final_payload.report_type,
            agent_name=final_payload.agent_name,
            data_snapshot_id=final_payload.data_snapshot_id,
            asset_id=input_facts.get("asset_id"),
            input_facts=final_payload.input_facts,
            summary=final_payload.summary,
            bullish_case=final_payload.bullish_case,
            bearish_case=final_payload.bearish_case,
            key_risks={"items": final_payload.key_risks},
            suggested_action=final_payload.suggested_action,
            confidence=final_payload.confidence,
            evidence=final_payload.evidence,
            limitations=final_payload.limitations,
        )
        self.db.add(report)
        self.db.flush()
        self._write_audit_log(
            action="research_committee.completed",
            entity_type="ResearchReport",
            entity_id=report.id,
            payload_json={
                "data_snapshot_id": data_snapshot_id,
                "agent_run_ids": [agent_run.id for agent_run in agent_runs],
                "automation_level": automation_level,
                "order_intent_created": False,
            },
        )
        return report

    def _findings_for(self, agent_name: str, outputs: list[dict[str, Any]]) -> str:
        for output in outputs:
            if output["agent_name"] == agent_name:
                return " ".join(output["findings"])
        return "Data unavailable for this committee role."

    def _risks_from_outputs(self, outputs: list[dict[str, Any]]) -> list[str]:
        risks: list[str] = []
        for output in outputs:
            risks.extend(output["risks"])
        return risks or ["Data unavailable for risk review."]

    def _average_confidence(self, outputs: list[dict[str, Any]]) -> float:
        if not outputs:
            return 0
        return round(sum(float(output["confidence"]) for output in outputs) / len(outputs), 4)

    def _write_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload_json: dict[str, Any],
    ) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="phase5-research-committee",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


def now() -> datetime:
    return datetime.now(timezone.utc)
