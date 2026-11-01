# Stage 0-4 Development Plan And Current Slice

Date: 2026-06-16

This document tracks the first implementation pass for the user-requested Stage 0, 1, 2, 3, and 4 plan. The scope remains read-only, audit-first, and fail-closed.

## Stage Map

| Stage | Goal | Current Slice | Acceptance |
| --- | --- | --- | --- |
| 0 Baseline | Keep the repo runnable and regression-safe. | Preserve existing backend regression, frontend typecheck, Alembic smoke, and demo smoke workflow. | `./scripts/regression_check.sh` passes before expanding live or external integrations. |
| 1 Daily Self-use | Make the system useful every day without execution. | Daily action queue now supports `source`, `priority`, and `action_type` filters; queue time handling is normalized outside SQLite datetime quirks. | User can inspect due reminders, high-priority watchlist items, stale data, and backup tasks without any trade execution path. |
| 2 Read-only Data | Ingest and inspect broker/exchange/wallet/CSV data safely. | Existing CSV and read-only account sync flows remain execution-disabled and catalog-writing. | Imports create snapshots, quality reports, catalog entries, and read-only ledger inputs only. |
| 3 Data Trust | Make dataset quality and contract state visible before downstream use. | Added Data Catalog entry detail API and frontend inspection panel with contract status, blockers, recommended actions, linked snapshot, and linked quality report. | Every catalog row can explain whether it is usable, review-only, or blocked; `execution_available=false` remains explicit. |
| 4 Ledger / Reconciliation | Turn imported data into auditable portfolio memory. | Catalog detail links CSV and account datasets to ledger sync/reconciliation actions as manual next steps. | Reconciliation stays manual and read-only; no automatic repair, broker write, wallet signing, or order placement. |

## Implemented In This Slice

- Backend: `GET /data-catalog/entries/{entry_id}` returns entry, linked snapshot, linked quality report, contract status, blockers, recommended actions, related manual action, and `execution_available=false`.
- Backend: `/daily-use/action-queue` accepts optional filters: `source`, `priority`, and `action_type`.
- Backend: Daily queue now avoids accidental high-priority item filtering caused by local variable shadowing.
- Backend: Due reminder selection now normalizes timezone-aware and SQLite-loaded naive datetimes consistently.
- Frontend: Data source panel can inspect a Data Catalog row and show why it is blocked or review-only.
- Frontend: Backend service types now include `DataCatalogEntryDetail` and filtered daily action queue calls.
- Tests: CSV/catalog tests cover the new catalog detail endpoint; daily queue tests cover filtered reminders.

## Safety Boundary

- No live trading was enabled.
- No broker, exchange, wallet, or DEX write action was added.
- No signing, withdrawals, order placement, or automated repair was added.
- Data Catalog detail and Daily Action Queue remain inspection and workflow guidance only.
- Related actions are labels and endpoint references, not automatic execution.

## Next Work

1. Stage 0: keep regression green and add a short baseline-health changelog after each slice.
2. Stage 1: add UI filters for Daily Action Queue and persist user-specific local workflow preferences.
3. Stage 2: add authenticated read-only adapter adapters behind secret references and mock-mode tests.
4. Stage 3: add raw payload hash, dataset version, schema contract version, and strict downstream data-contract checks.
5. Stage 4: expand ledger reconciliation policy by account, asset class, cash, tax lot, and corporate action.

## Verification

Focused verification for this slice:

```bash
cd backend
.venv/bin/pytest tests/test_csv_import_catalog.py tests/test_readonly_setup_daily_ops.py -q

cd ../frontend
npm run typecheck
```

Expected current result: backend focused tests pass and frontend typecheck passes.
