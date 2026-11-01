import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai import AIProvider
from app.ai import DeepSeekProvider
from app.ai import MockAIProvider
from app.ai import OpenAIProvider
from app.ai.prompts import PromptTemplateLoader
from app.ai.reports import PROMPT_BY_REPORT_TYPE
from app.ai.reports import ResearchReportOutput
from app.models import AgentRun
from app.models import Asset
from app.models import AuditLog
from app.models import ResearchReport
from app.core.auth import AuthenticatedUser
from app.services.human_control import HumanControlService
from app.services.data_catalog import DataCatalogService


class InvalidReportOutputError(ValueError):
    pass


class ReportGenerator:
    def __init__(
        self,
        db: Session,
        *,
        prompt_loader: PromptTemplateLoader | None = None,
        provider: AIProvider | None = None,
        actor: AuthenticatedUser | None = None,
    ):
        self.db = db
        self.prompt_loader = prompt_loader or PromptTemplateLoader()
        self.provider = provider
        self.actor = actor
        self.last_provider_usage: dict[str, Any] | None = None

    def generate(
        self,
        *,
        report_type: str,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        agent_name: str = "mock_research_agent",
        provider_name: str = "mock",
        decision_scope: str = "research_report",
    ) -> ResearchReport:
        DataCatalogService(self.db).require_trusted_snapshot(
            data_snapshot_id,
            decision_scope=decision_scope,
        )
        prompt_template = self.prompt_loader.load(PROMPT_BY_REPORT_TYPE[report_type])
        provider = self.provider or self._provider(provider_name)
        agent_run = AgentRun(
            agent_name=agent_name,
            run_type=report_type,
            status="running",
            input_snapshot_id=data_snapshot_id,
            output_json={},
        )
        self.db.add(agent_run)
        self.db.flush()

        try:
            raw_output = provider.generate_report(
                report_type=report_type,
                agent_name=agent_name,
                data_snapshot_id=data_snapshot_id,
                input_facts=input_facts,
                prompt_template=prompt_template,
            )
            usage = getattr(provider, "last_usage", None)
            self.last_provider_usage = dict(usage) if isinstance(usage, dict) else None
            validated = self._validate(raw_output, report_type, data_snapshot_id, input_facts)
        except (InvalidReportOutputError, NotImplementedError, ValueError) as exc:
            agent_run.status = "failed"
            agent_run.error_message = str(exc)
            self._write_audit_log(
                action="research_report.invalid_output_rejected",
                entity_type="AgentRun",
                entity_id=agent_run.id,
                payload_json={"report_type": report_type, "data_snapshot_id": data_snapshot_id, "error": str(exc)},
            )
            self.db.commit()
            raise

        requested_asset_id = input_facts.get("asset_id")
        asset = self.db.get(Asset, str(requested_asset_id)) if requested_asset_id else None
        report = ResearchReport(
            report_type=validated.report_type,
            agent_name=validated.agent_name,
            data_snapshot_id=validated.data_snapshot_id,
            asset_id=asset.id if asset is not None else None,
            input_facts=validated.input_facts,
            summary=validated.summary,
            bullish_case=validated.bullish_case,
            bearish_case=validated.bearish_case,
            key_risks={"items": validated.key_risks},
            suggested_action=validated.suggested_action,
            confidence=validated.confidence,
            evidence=validated.evidence,
            limitations=validated.limitations,
        )
        self.db.add(report)
        self.db.flush()

        agent_run.status = "completed"
        agent_run.output_json = {"research_report_id": report.id, "report_id": validated.report_id}
        self._write_audit_log(
            action="research_report.generated",
            entity_type="ResearchReport",
            entity_id=report.id,
            payload_json={
                "report_type": report_type,
                "data_snapshot_id": data_snapshot_id,
                "agent_run_id": agent_run.id,
                "provider": provider_name,
            },
        )
        self.db.commit()
        self.db.refresh(report)
        return report

    def _provider(self, provider_name: str) -> AIProvider:
        if provider_name == "mock":
            return MockAIProvider()
        if provider_name == "openai":
            return OpenAIProvider()
        if provider_name == "deepseek":
            return DeepSeekProvider()
        if provider_name == "configured":
            if self.actor is None:
                raise InvalidReportOutputError("configured AI provider requires an authenticated user")
            return HumanControlService(self.db).configured_ai_provider(actor=self.actor)
        raise InvalidReportOutputError(f"unsupported AI provider: {provider_name}")

    def _validate(
        self,
        raw_output: str | dict[str, Any],
        report_type: str,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
    ) -> ResearchReportOutput:
        if isinstance(raw_output, str):
            try:
                payload = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise InvalidReportOutputError("AI provider returned invalid JSON") from exc
        else:
            payload = raw_output

        try:
            validated = ResearchReportOutput.model_validate(payload)
        except ValidationError as exc:
            raise InvalidReportOutputError(f"AI provider output failed schema validation: {exc}") from exc

        if validated.report_type != report_type:
            raise InvalidReportOutputError("AI provider report_type does not match request")
        if validated.data_snapshot_id != data_snapshot_id:
            raise InvalidReportOutputError("AI provider data_snapshot_id does not match request")
        if validated.input_facts != input_facts:
            raise InvalidReportOutputError("AI provider changed input_facts")

        return validated

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
                actor_id="phase4-report-generator",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )
