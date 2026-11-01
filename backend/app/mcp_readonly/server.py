"""Read-only MCP server for the AI Trading OS (Phase 29).

Exposes the terminal's review-only capabilities as MCP tools over stdio so an
external agent (Claude Desktop, Claude Code, any MCP client) can *look at*
the book — portfolio state, theses and their evidence deltas, risk reports,
signal quality, data trust, plan pipeline status, backtest results.

Hard safety boundary, by construction rather than by policy text:
- No tool here creates, modifies, approves, executes, promotes, signs, or
  transfers anything. The only write anywhere below is the audit record the
  thesis-delta service keeps of its own generation.
- Decision gates cannot be bypassed through this server because nothing that
  crosses a gate (order intents, drafts, approvals, executions) is callable.
- Every tool result carries execution_available=False.

Run: `python -m app.mcp_readonly.server` (stdio transport).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.session import get_session_factory

# Tool names must never suggest (or provide) trade execution. The safety test
# asserts every registered tool name is free of these verbs/nouns.
FORBIDDEN_TOOL_NAME_TERMS = (
    "create",
    "approve",
    "execute",
    "order",
    "trade",
    "buy",
    "sell",
    "promote",
    "sign",
    "transfer",
    "withdraw",
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - dependency is optional (pyproject extra "mcp")
    raise ImportError("The MCP server requires the 'mcp' extra: pip install -e '.[mcp]'") from exc

mcp = FastMCP(
    "ai-trading-os-readonly",
    instructions=(
        "Read-only research tools for a personal trading terminal. These tools can "
        "inspect portfolio state, theses, risk, signals, data trust, plan pipeline "
        "status, and backtest results. They can never place, draft, approve, or "
        "execute trades; treat every result as review-only evidence for a human."
    ),
)

# Module attribute so tests can swap in a throwaway database session factory.
_session_factory = None


def _open_session():
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    return _session_factory()


def _readonly(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "execution_available": False, "review_only": True}


@mcp.tool()
def portfolio_snapshot() -> dict[str, Any]:
    """Current portfolio summary: total equity, cash, and allocation buckets.
    Review-only; contains no credentials or account identifiers."""
    from app.services.portfolio import PortfolioSummaryService

    with _open_session() as session:
        return _readonly(PortfolioSummaryService(session).build_current())


@mcp.tool()
def list_theses(limit: int = 20, status: str | None = None) -> dict[str, Any]:
    """List investment theses (newest first): asset, entry reason, status,
    confidence, max-loss tolerance, invalidation conditions."""
    from app.models import Asset
    from app.models import InvestmentThesis

    limit = max(1, min(int(limit), 100))
    with _open_session() as session:
        query = select(InvestmentThesis).order_by(InvestmentThesis.created_at.desc()).limit(limit)
        if status:
            query = select(InvestmentThesis).where(InvestmentThesis.status == status).order_by(InvestmentThesis.created_at.desc()).limit(limit)
        rows = list(session.scalars(query).all())
        symbols = {asset.id: asset.symbol for asset in session.scalars(select(Asset)).all()}
        return _readonly(
            {
                "count": len(rows),
                "theses": [
                    {
                        "id": thesis.id,
                        "symbol": symbols.get(thesis.asset_id),
                        "status": thesis.status,
                        "entry_reason": thesis.entry_reason,
                        "key_drivers": thesis.key_drivers_json,
                        "invalidation_conditions": thesis.invalidation_conditions_json,
                        "confidence": float(thesis.confidence),
                        "max_loss_tolerance_pct": float(thesis.max_loss_tolerance_pct),
                        "expected_horizon": thesis.expected_horizon,
                        "updated_at": thesis.updated_at.isoformat(),
                    }
                    for thesis in rows
                ],
            }
        )


@mcp.tool()
def thesis_delta(thesis_id: str) -> dict[str, Any]:
    """What changed since this thesis was last reviewed: price move vs the
    stated max-loss tolerance, new SEC filings, news, macro deltas, catalysts.
    Built from locally stored evidence only; missing feeds are reported
    honestly. The human still records the checkpoint verdict."""
    from app.services.research_feeds import ResearchFeedService

    with _open_session() as session:
        return _readonly(ResearchFeedService(session).thesis_delta(thesis_id))


@mcp.tool()
def portfolio_risk_latest(user_id: str = "default-user") -> dict[str, Any]:
    """Latest time-series risk analysis: realized volatility, VaR, drawdown
    vs budget, correlations, liquidity, and stress scenarios. Returns a
    not-run marker when no analysis exists yet (fail-closed, nothing invented)."""
    from app.services.portfolio_time_series_risk import PortfolioTimeSeriesRiskService

    with _open_session() as session:
        result = PortfolioTimeSeriesRiskService(session).latest(user_id=user_id)
        if result is None:
            return _readonly({"status": "not_run", "detail": "No portfolio risk analysis has been run yet."})
        return _readonly(result)


@mcp.tool()
def signal_quality_report(horizon_candles: int = 5, limit: int = 500) -> dict[str, Any]:
    """Signal quality vs a zero-skill baseline: hit rates and forward returns
    realized from stored candles. Signals cannot bypass decision gates
    regardless of how good this report looks."""
    from app.services.signals import SignalEngineService

    with _open_session() as session:
        return _readonly(SignalEngineService(session).evaluate_signal_quality(horizon_candles=horizon_candles, limit=limit))


@mcp.tool()
def data_trust_report(decision_scope: str = "research") -> dict[str, Any]:
    """Whether locally stored data is fresh and trustworthy enough for the
    given decision scope (research / daily_review / ...). Fail-closed."""
    from app.schemas import DataTrustReportRead
    from app.services.data_catalog import DataCatalogService

    with _open_session() as session:
        report = DataCatalogService(session).trust_report(decision_scope=decision_scope)
        # The raw report embeds ORM rows; serialize through the same schema the
        # HTTP API uses so the MCP payload is plain JSON.
        return _readonly(DataTrustReportRead.model_validate(report).model_dump(mode="json"))


@mcp.tool()
def plan_pipeline_status(limit: int = 20) -> dict[str, Any]:
    """Status of the plan pipeline (read-only): each draft's risk, behavior,
    approval, and execution status. This tool can only observe the pipeline;
    it cannot move anything through it."""
    from app.models import OrderDraft

    limit = max(1, min(int(limit), 100))
    with _open_session() as session:
        rows = list(session.scalars(select(OrderDraft).order_by(OrderDraft.created_at.desc()).limit(limit)).all())
        return _readonly(
            {
                "count": len(rows),
                "drafts": [
                    {
                        "id": draft.id,
                        "risk_status": draft.risk_status,
                        "behavior_status": draft.behavior_status,
                        "approval_status": draft.approval_status,
                        "execution_status": draft.execution_status,
                        "created_at": draft.created_at.isoformat(),
                    }
                    for draft in rows
                ],
            }
        )


@mcp.tool()
def list_backtest_results(limit: int = 10) -> dict[str, Any]:
    """Recent backtest runs with their metrics and benchmark comparison.
    Research-only simulations; results never unlock execution."""
    from app.services.backtests import BacktestRunsService

    limit = max(1, min(int(limit), 50))
    with _open_session() as session:
        runs = BacktestRunsService(session).list_runs(limit=limit)
        return _readonly(
            {
                "count": len(runs),
                "runs": [
                    {
                        "id": run.id,
                        "name": run.name,
                        "status": run.status,
                        "date_from": run.date_from.isoformat(),
                        "date_to": run.date_to.isoformat(),
                        "metrics": (run.results_json or {}).get("metrics"),
                        "benchmark": (run.results_json or {}).get("benchmark"),
                        "mode": (run.results_json or {}).get("mode", "single_asset"),
                        "engine_status": (run.results_json or {}).get("engine_status"),
                    }
                    for run in runs
                ],
            }
        )


def main() -> None:  # pragma: no cover - interactive entry point
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
