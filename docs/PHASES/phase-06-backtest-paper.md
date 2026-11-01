# Phase 06 — Signal Engine

## Deliverables

- Technical signal generation: RSI, MA cross, MACD placeholder, Bollinger Band placeholder, volume anomaly, volatility spike
- Capital-flow placeholders: stock capital flow, crypto exchange flow, funding rate
- On-chain placeholders: whale transfer, large wallet accumulation, token unlock, liquidity change
- Deterministic local-candle MA-cross backtest simulation
- Backtest fail-closed preflight for missing asset, inactive playbook, invalid windows, and insufficient candles
- `GET /signals`
- `POST /signals/generate`
- `POST /signals/{id}/create-order-intent`
- `GET /backtest-runs`
- `POST /backtest-runs`
- `POST /backtest-runs/{id}/start`

## Safety Constraints

- Signals are observations, not orders.
- Signal generation never creates `OrderIntent`.
- Signal-to-order-intent conversion requires both explicit user setting and automation level `A3_ORDER_DRAFT` or higher.
- Signal-created order intents are passive records only and do not create drafts or executions.
- Every signal generation and signal-to-order-intent conversion path writes `AuditLog`.
- Backtest simulation writes only `BacktestRun.results_json`; it never creates order intents, order drafts, paper executions, live executions, or broker calls.
