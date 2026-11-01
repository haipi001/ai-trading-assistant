# Phase 05 — Multi-Agent Research

## Deliverables

- Read-only TradingAgents-style research committee
- `FundamentalAnalyst`, `TechnicalAnalyst`, `NewsAnalyst`, `CryptoOnchainAnalyst`
- `BullResearcher`, `BearResearcher`, `RiskManager`, `PortfolioManager`
- `POST /agents/run-research`
- `AgentRun` records for each agent
- Final validated `ResearchReport`

## Safety Constraints

- Agents cannot execute trades.
- Agents cannot call broker, exchange, wallet, or execution adapters.
- Invalid agent JSON is rejected and logged.
- `OrderIntent` creation remains disabled in this phase, even when request automation level is `A3_ORDER_DRAFT`.
- Final reports cite `data_snapshot_id` and use only structured request facts plus validated agent outputs.
