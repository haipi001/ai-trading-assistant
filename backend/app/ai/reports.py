from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator

from app.ai.safety import detect_blocked_actions


REPORT_TYPES = {
    "portfolio_daily_review",
    "single_asset_research",
    "technical_signal_explanation",
    "crypto_market_research",
    "rebalance_suggestion",
}

ReportType = Literal[
    "portfolio_daily_review",
    "single_asset_research",
    "technical_signal_explanation",
    "crypto_market_research",
    "rebalance_suggestion",
]

PROMPT_BY_REPORT_TYPE = {
    "portfolio_daily_review": "portfolio_daily_review",
    "single_asset_research": "stock_fundamental_research",
    "technical_signal_explanation": "technical_analysis",
    "crypto_market_research": "crypto_market_research",
    "rebalance_suggestion": "risk_manager_review",
}

# Backward-compatible alias; the real gate is detect_blocked_actions() in
# app/ai/safety.py, which normalizes text and covers EN/ZH natural language.
BLOCKED_ACTION_TERMS = {
    "execute",
    "place_order",
    "place order",
    "market_order",
    "market order",
    "limit_order",
    "limit order",
    "submit_order",
    "submit order",
    "send_order",
    "send order",
}


class ResearchReportOutput(BaseModel):
    model_config = {"extra": "forbid"}

    report_id: str
    report_type: ReportType
    agent_name: str
    data_snapshot_id: str
    input_facts: dict[str, Any] = Field(default_factory=dict)
    summary: str
    bullish_case: str
    bearish_case: str
    key_risks: list[str]
    suggested_action: str
    confidence: float = Field(ge=0, le=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    limitations: str

    @field_validator("summary", "bullish_case", "bearish_case", "suggested_action", "limitations")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("suggested_action")
    @classmethod
    def block_executable_actions(cls, value: str) -> str:
        matches = detect_blocked_actions(value)
        if matches:
            detail = "; ".join(f"{match.category}:{match.normalized_match}" for match in matches[:3])
            raise ValueError(f"report suggested_action cannot contain executable order instructions ({detail})")
        return value
