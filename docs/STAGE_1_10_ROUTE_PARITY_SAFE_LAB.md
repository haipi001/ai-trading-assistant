# Stage 1-10 Route Parity Safe Lab

Date: 2026-06-16

This slice starts the requested step-by-step development plan by closing backend route gaps that the frontend already expected, without expanding execution authority.

## Implemented

- Added persisted `StrategyRule` metadata for `/strategy-rules`.
- Added persisted `BacktestRun` records for `/backtest-runs`.
- Added `/controlled-auto/evaluate/{kind}` and `/controlled-auto/execute/{kind}` for DCA, rebalance, stop-loss, and take-profit readiness checks.
- Added `/modules`, `/modules/{module_type}/health`, and `/modules/{module_type}/gate-compliance`.
- Added `/broker-connections` compatibility endpoints that map to existing `LiveExecutionConfig` references.
- Added Alembic migration `20260616_0017`.
- Added focused route parity safety tests.

## Safety Boundary

- Strategy rules are metadata only and do not create order intents, drafts, executions, or broker calls.
- Backtest runs can be created, but `start` returns `blocked` until a verified deterministic engine and data contract exist.
- Controlled-auto evaluate always returns `passed=false`.
- Controlled-auto execute always returns `status=blocked` and `order_intent_id=not-created`.
- Broker connections store `api_key_ref` references only and reject inline secret-looking values.
- Module compliance reports fail-closed execution posture.
- No live trading, wallet signing, DEX swap, withdrawals, or broker submission is introduced.

## New API Surface

- `GET /strategy-rules`
- `POST /strategy-rules`
- `PATCH /strategy-rules/{rule_id}`
- `DELETE /strategy-rules/{rule_id}`
- `GET /backtest-runs`
- `POST /backtest-runs`
- `GET /backtest-runs/{run_id}`
- `POST /backtest-runs/{run_id}/start`
- `POST /controlled-auto/evaluate/dca`
- `POST /controlled-auto/execute/dca`
- `POST /controlled-auto/evaluate/rebalance`
- `POST /controlled-auto/execute/rebalance`
- `POST /controlled-auto/evaluate/stop-loss`
- `POST /controlled-auto/execute/stop-loss`
- `POST /controlled-auto/evaluate/take-profit`
- `POST /controlled-auto/execute/take-profit`
- `GET /modules`
- `GET /modules/{module_type}/health`
- `GET /modules/{module_type}/gate-compliance`
- `GET /broker-connections`
- `POST /broker-connections`
- `DELETE /broker-connections/{connection_id}`

## Verification

Focused backend verification:

```bash
cd backend
./.venv/bin/pytest tests/test_route_parity_safe_lab.py
```

Observed result during implementation: `5 passed`.

Full regression after implementation:

```bash
./scripts/regression_check.sh
```

Observed result: backend `165 passed`, Alembic migration smoke passed through `20260616_0017`, frontend typecheck passed, and demo smoke passed.

## Remaining Work

- Replace placeholder blocked backtest start with deterministic, read-only simulation after historical data contracts are verified.
- Connect strategy rules into thesis/gate/readiness explanations without allowing direct order creation.
- Add richer module registry details for installed sidecars and advanced labs.
- Keep live execution and controlled auto disabled until approval, risk budget, kill switch, reconciliation, and observability criteria are proven.
