# V4 Gap Audit — Phase 1, Phase 2, Phase 23

Date: 2026-06-15

This audit records the first safe implementation pass after aligning the project to the v4 master prompt.

## Current Result

| Area | Status | Implemented In This Pass | Remaining Gap |
| --- | --- | --- | --- |
| Phase 1 Domain Models | Improved | Added `DataCatalogEntry`, `InvestmentLedgerEntry`, `ReconciliationRun`, and `ReconciliationBreak` models and migrations; existing Asset, Account, Position, Quote, Candle, Snapshot, Quality, PortfolioSnapshot models remain the local core. | Full tax/cash/corporate-action normalized ledger and external-broker reconciliation remain later work. |
| Phase 2 Data Adapters | Improved | Added `/imports/csv` for manual holdings, crypto holdings, wallet balances, and trade-history CSV ingestion; added demo CSV files. Added `/data-sources/connections/read-only-setup` and `/data-sources/connections/{connection_id}/read-only-preflight` for metadata-only IBKR/Futu/CEX/Wallet onboarding checks. | Authenticated read-only API calls, fundamentals, corporate-action, and news adapters remain later phases. |
| Phase 23 Data Catalog | Improved | Added `/data-catalog/entries`, `/data-catalog/overview`, `/data-catalog/trust-report`, lineage/contract metadata, quality status, and read-only catalog writes from quote, candle, account, and CSV imports. Added `/data-sources/freshness`. | Raw payload hash, dataset versioning, reconciliation promotion rules, and strict downstream gate enforcement remain later work. |
| Daily Workflow | First safe slice | Added `/daily-use/action-queue` and UI actions for reminders, watchlist maintenance, exports, backups, and data-refresh attention. | Calendar integrations, recurring scheduling UX, and richer thesis-review automation remain later work. |
| Investment Ledger | Improved | Added `/ledger/sync`, `/ledger/entries`, `/ledger/preflight`, `/ledger/reconcile`, `/ledger/reconciliation/latest`, `/ledger/statement-imports`, and `/ledger/reconcile/extended`, plus Settings visualization for ledger entries, statement imports, reconciliation breaks, and extended checks. Ledger sync/reconcile now expose `data_trust_status` from the data trust layer. | Authenticated broker statement download, account-level reconciliation policies, reconciliation-based dataset promotion, and automated repair remain later work. |
| Deep Workflow Queue | Improved | Added `/workflows/deep-review-queue` for thesis monitor, missing thesis links, gate blockers/warnings, approved paper drafts, post-trade reviews, and playbook proposal follow-up. Added `/workflows/deep-review-tasks` assignment/completion metadata. | Calendar scheduling, notification routing, and bulk workflow actions remain later work. |
| Stage 5-11 Readiness | First safe slice | Added `/workflows/stage-5-11-readiness` to aggregate Strategy Playbook, Investment Thesis, Thesis Monitor, Decision Gates, Risk Engine, Behavior Engine, and Workflow State checks for order intents/drafts. Added Workflow panel visibility and focused tests. | Enforced workflow transitions, richer gate replay, behavior response capture, and scheduled thesis checkpoint automation remain later work. |
| Order Closure Report | First safe slice | Added `/workflows/order-closure-report` to aggregate each order draft across thesis/rationale, gates, risk, approval, paper execution, post-trade review, and safety boundary. | Frontend drilldown, workflow-task integration, and live-execution reconciliation handling remain later gated work. |
| Ops Readiness | Improved | Added `/ops/stability-report` for database, Redis, data freshness, backup, restore drill, secret-reference, operational-event, CI, monitoring, production targets, deployment, and safety checks. Added `/ops/restore-drill`, `/ops/production-targets`, and `.github/workflows/ci.yml`. | Managed deployment automation, real monitoring provider wiring, and executed restore drills in isolated infrastructure remain later work. |
| Stage 1-10 Route Parity Safe Lab | First safe slice | Added `/strategy-rules`, `/backtest-runs`, `/controlled-auto/*`, `/modules`, and `/broker-connections` compatibility routes. Added persisted StrategyRule and BacktestRun models plus migration `20260616_0017`. | Strategy-rule integration into gates, real module registry discovery, and any controlled/live execution remain later gated work. |
| Stage 4 Frontend Real Workflow | Improved | Data Sources now surfaces Research Data Trust and read-only account preflight. Settings now surfaces Ledger Preflight, ledger data trust, source availability, latest reconciliation, and safety checks. | Wire trust status deeper into order-draft and approval panels, add richer operator drilldowns, and add mobile-specific polish. |
| Stage 6 Strategy/Backtest/Signal Lab | Improved | Backtest start now performs fail-closed local data preflight and runs a deterministic MA-cross simulation when enough stored candles exist. Results include simulated trades, equity curve, metrics, data contract, and safety counters. | Richer strategy DSL, multi-asset simulation, benchmark comparison, slippage/liquidity models, and promotion workflow remain later work. |
| Stage 7 External Beta Productionization | First safe slice | Added `/beta/external-launch-report` to aggregate beta readiness, ops stability, daily-review data trust, ledger preflight, and release controls into a go/no-go report. | Real deployment provider verification, external monitoring integration, invite workflow, and rollback execution drills remain later work. |
| Stage 8 Controlled Live Sandbox | First safe slice | Added `/live-execution/sandbox-run` to exercise prepare checks, requested order calculation, broker submission planning, and rollback plan generation without creating executions or mutating drafts. | Real broker sandbox adapters, account allowlists, broker order-state reconciliation, and controlled external dry-run certification remain later work. |
| Stage 9 Advanced Sidecar/AI Modules | First safe slice | Added `/modules/sidecar-policy/evaluate` and module registry entry `ai_sidecar_policy` to evaluate proposed AI/sidecar modules against local control-plane boundaries. | Actual sidecar process registry, typed adapter contracts, callback ingestion, and provider-specific certifications remain later work. |
| Stage 10 Small Approval Live Pilot | First safe slice | Added `/live-execution/small-pilot-readiness` to check small-notional limits, human approval, live readiness, sandbox boundary, and rollback plan without executing. | Real broker sandbox certification, explicit account allowlists, signed approval packets, and controlled live pilot enablement remain later gated work. |

## Safety Boundary

- CSV import creates read-only accounts/assets/positions and snapshots.
- Imported assets remain `tradable=false`, `manual_enabled=false`, and `auto_enabled=false`.
- Data catalog entries do not create execution authority.
- CSV data defaults to `usable_for_trading=false`.
- Quote/candle catalog entries may be marked usable for trading decisions only when quality is complete; they still have `execution_available=false`.
- Read-only account snapshots remain review-only and are cataloged as not trading-usable until reconciliation exists.
- Read-only adapter onboarding stores only credential references and non-sensitive config.
- Daily action queue and ops preflight never execute trades, deployments, wallet signing, or secret rotation.
- External beta launch report is read-only and never deploys, invites users, rotates secrets, restores data, creates orders, approves trades, or executes trades.
- Ledger sync and reconciliation never modify broker/exchange state.
- Statement import accepts local CSV text only, stores read-only ledger/catalog records, and never connects to a broker/exchange/bank/wallet.
- Extended reconciliation reports cash, tax-lot, and corporate-action breaks only; it never repairs ledgers or positions automatically.
- Deep workflow queue never approves, executes, or applies playbook changes.
- Review task assignment records follow-up ownership only; it does not transition workflow state or approve trades.
- Stage 5-11 readiness is read-only aggregation and always reports `execution_available=false`.
- Order closure report is read-only aggregation and always reports `execution_available=false`; the current safe slice treats non-paper executions as blocking anomalies.
- Strategy rules are metadata only and do not create order intents, drafts, executions, or broker calls.
- Backtest run start returns `blocked` when local historical-data contracts are missing or insufficient; otherwise it runs deterministic read-only simulation.
- Backtest simulation is read-only: it stores simulated trades only in `BacktestRun.results_json` and never creates order intents, order drafts, paper executions, live executions, or broker calls.
- Live execution sandbox-run is read-only: it never creates `Execution`, never mutates `OrderDraft.execution_status`, and never submits broker orders.
- Sidecar policy evaluation is read-only and never starts sidecars, stores secrets, creates orders, executes trades, mutates core state, or calls brokers.
- Small live pilot readiness is preflight-only: it never creates `Execution`, mutates draft execution status, creates positions, or submits broker orders.
- Controlled-auto evaluation is readiness-only; controlled-auto execute always returns `blocked` and never creates an order intent.
- Broker connection compatibility endpoints store only secret references and inherit live execution fail-closed behavior.
- Restore drill only records a manual plan and audit event; it does not restore data or run commands.
- Production targets are metadata-only records; they do not configure external monitoring, deploy services, rotate secrets, or send alerts.

## New API Surface

- `POST /imports/csv`
- `GET /data-catalog/entries`
- `GET /data-catalog/entries/{entry_id}`
- `GET /data-catalog/overview`
- `POST /data-sources/connections/read-only-setup`
- `POST /data-sources/connections/{connection_id}/read-only-certification`
- `GET /data-sources/freshness`
- `GET /daily-use/action-queue`
- `GET /data-catalog/provenance-report`
- `GET /ledger/entries`
- `GET /ledger/reconciliation-policy`
- `GET /ledger/statement-imports`
- `POST /ledger/statement-imports`
- `POST /ledger/sync`
- `POST /ledger/reconcile`
- `POST /ledger/reconcile/extended`
- `GET /ledger/reconciliation/latest`
- `GET /workflows/deep-review-queue`
- `GET /workflows/deep-review-tasks`
- `POST /workflows/deep-review-tasks`
- `POST /workflows/deep-review-tasks/{task_id}/complete`
- `GET /workflows/stage-5-11-readiness`
- `GET /workflows/order-closure-report`
- `GET /workflows/review-quality-report`
- `GET /beta/external-launch-report`
- `GET /beta/release-control-report`
- `GET /ops/stability-report`
- `POST /ops/restore-drill`
- `GET /ops/production-targets`
- `POST /ops/production-targets`
- `GET /strategy-rules`
- `POST /strategy-rules`
- `PATCH /strategy-rules/{rule_id}`
- `DELETE /strategy-rules/{rule_id}`
- `GET /backtest-runs`
- `POST /backtest-runs`
- `GET /backtest-runs/{run_id}`
- `POST /backtest-runs/{run_id}/start`
- `POST /backtest-runs/{run_id}/promotion-preflight`
- `POST /controlled-auto/evaluate/{kind}`
- `POST /controlled-auto/execute/{kind}`
- `GET /modules`
- `GET /modules/{module_type}/health`
- `GET /modules/{module_type}/gate-compliance`
- `POST /modules/sidecar-policy/evaluate`
- `POST /modules/sidecar-contract/report`
- `GET /broker-connections`
- `POST /broker-connections`
- `DELETE /broker-connections/{connection_id}`
- `POST /live-execution/sandbox-run`
- `POST /live-execution/sandbox-certification`
- `POST /live-execution/small-pilot-readiness`
- `POST /live-execution/small-pilot-approval-packet`

## Demo Files

- `backend/data/demo_csv/holdings.csv`
- `backend/data/demo_csv/trades.csv`

## Verification

Focused backend verification:

```bash
cd backend
.venv/bin/pytest tests/test_csv_import_catalog.py tests/test_data_sources.py -q
.venv/bin/pytest tests/test_readonly_setup_daily_ops.py tests/test_data_sources.py tests/test_daily_use.py tests/test_beta_readiness.py -q
```

Focused results during implementation: `17 passed` for the first CSV/catalog slice, `27 passed` for the 4/5/6 slice, `7 passed` for the 7/8/9 slice, and `6 passed` for the 10/11/12 slice. After the 10/11/12 slice, full backend suite passed with `158 passed`; Alembic smoke, frontend typecheck, regression script, API smoke, and browser desktop/mobile verification passed. The Stage 0-4 follow-up added Data Catalog entry detail inspection and filtered Daily Action Queue verification with `7 passed` focused backend tests plus frontend typecheck. The Stage 5-11 follow-up added readiness aggregation with `2 passed` focused backend tests plus frontend typecheck. The Stage 1-10 route parity safe lab added backend compatibility routes with `5 passed` focused backend tests, then full regression passed with backend `165 passed`, Alembic smoke through `20260616_0017`, frontend typecheck, and demo smoke. The 2026-06-18 Stage 1-10 completion pass added certification/provenance/ledger-policy/frontend/review-quality/backtest-promotion/beta-release/sandbox-certification/sidecar-contract/small-pilot-packet slices; full backend suite passed with `194 passed`, and frontend `npm run typecheck` passed.

The 2026-06-19 Product Completion Plan 1-10 pass added certified sync plan, contract enforcement report, reconciliation workbench, frontend product packet client functions, review action plan, backtest research packet, beta invitation packet, product stability packet, broker reconciliation plan, and small pilot go/no-go. New focused tests passed with `10 passed`; related backend tests passed with `61 passed`; frontend `npm run typecheck` passed. All live-related additions remain preflight/report/packet only.
