import json
from abc import ABC
from abc import abstractmethod
from typing import Any


class ResearchAgent(ABC):
    agent_name: str
    role: str

    @abstractmethod
    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        raise NotImplementedError

    def output(
        self,
        *,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        findings: list[str],
        risks: list[str] | None = None,
        confidence: float = 0.6,
    ) -> str:
        payload = {
            "agent_name": self.agent_name,
            "role": self.role,
            "data_snapshot_id": data_snapshot_id,
            "input_facts": input_facts,
            "findings": findings,
            "risks": risks or ["Data coverage should be reviewed before making decisions."],
            "confidence": confidence,
            "limitations": "Deterministic mock research agent; uses only structured input facts.",
        }
        return json.dumps(payload)

    def field_status(self, input_facts: dict[str, Any], field_name: str) -> str:
        value = input_facts.get(field_name)
        if value in (None, [], {}):
            return f"{field_name} data unavailable."
        return f"{field_name} provided."


class FundamentalAnalyst(ResearchAgent):
    agent_name = "FundamentalAnalyst"
    role = "fundamental_analysis"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            self.field_status(input_facts, "market_facts"),
            "Fundamental view is limited to structured market facts and prior reports.",
        ]
        return self.output(data_snapshot_id=data_snapshot_id, input_facts=input_facts, findings=findings)


class TechnicalAnalyst(ResearchAgent):
    agent_name = "TechnicalAnalyst"
    role = "technical_analysis"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            self.field_status(input_facts, "signals"),
            "Technical view is based only on supplied signal observations.",
        ]
        return self.output(data_snapshot_id=data_snapshot_id, input_facts=input_facts, findings=findings)


class NewsAnalyst(ResearchAgent):
    agent_name = "NewsAnalyst"
    role = "news_analysis"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            self.field_status(input_facts, "market_facts"),
            "News view is unavailable unless news facts are present inside market_facts.",
        ]
        return self.output(data_snapshot_id=data_snapshot_id, input_facts=input_facts, findings=findings)


class CryptoOnchainAnalyst(ResearchAgent):
    agent_name = "CryptoOnchainAnalyst"
    role = "crypto_onchain_analysis"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            self.field_status(input_facts, "market_facts"),
            "On-chain view is unavailable unless on-chain facts are present inside market_facts.",
        ]
        return self.output(data_snapshot_id=data_snapshot_id, input_facts=input_facts, findings=findings)


class BullResearcher(ResearchAgent):
    agent_name = "BullResearcher"
    role = "bull_case"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            "Bull case can only cite favorable facts already present in analyst outputs.",
            self.field_status(input_facts, "analyst_outputs"),
        ]
        return self.output(data_snapshot_id=data_snapshot_id, input_facts=input_facts, findings=findings)


class BearResearcher(ResearchAgent):
    agent_name = "BearResearcher"
    role = "bear_case"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            "Bear case highlights uncertainty and missing data from analyst outputs.",
            self.field_status(input_facts, "analyst_outputs"),
        ]
        return self.output(
            data_snapshot_id=data_snapshot_id,
            input_facts=input_facts,
            findings=findings,
            risks=["Missing or stale facts may invalidate the research view."],
        )


class RiskManager(ResearchAgent):
    agent_name = "RiskManager"
    role = "risk_review"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            self.field_status(input_facts, "positions"),
            self.field_status(input_facts, "signals"),
            "Risk review does not approve or execute orders.",
        ]
        return self.output(
            data_snapshot_id=data_snapshot_id,
            input_facts=input_facts,
            findings=findings,
            risks=["Review concentration, liquidity, volatility, and missing data before taking action."],
        )


class PortfolioManager(ResearchAgent):
    agent_name = "PortfolioManager"
    role = "portfolio_review"

    def run(self, *, data_snapshot_id: str, input_facts: dict[str, Any]) -> str:
        findings = [
            self.field_status(input_facts, "positions"),
            "Portfolio manager can summarize research but cannot create executable instructions.",
        ]
        return self.output(
            data_snapshot_id=data_snapshot_id,
            input_facts=input_facts,
            findings=findings,
            risks=["Portfolio conclusions are limited by supplied facts and prior agent outputs."],
        )
