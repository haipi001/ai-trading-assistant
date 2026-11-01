# Stage 3 Ledger Trust Preflight

This stage connects the data trust layer to ledger and reconciliation workflows.

## Scope

- Added `GET /ledger/preflight`.
- Ledger sync and reconciliation responses now include `data_trust_status` and `data_trust_report`.
- Reconciliation run summaries record the current ledger data-trust status.
- Existing sync/reconcile happy paths remain read-only and compatible with paper execution and local position workflows.

## Preflight Checks

| Check | Purpose |
| --- | --- |
| `data_trust` | Reads `/data-catalog/trust-report?decision_scope=ledger`. |
| `ledger_sources` | Counts local positions, paper executions, and ledger entries available for sync. |
| `latest_reconciliation` | Reports whether a prior reconciliation exists and whether it blocked. |
| `safety_boundary` | Confirms ledger workflows cannot trade, sign, swap, or withdraw. |

## Status Semantics

- `block`: no trusted/review-only ledger dataset and no local sync source exists.
- `warn`: data is review-only, or reconciliation has not yet run.
- `ok`: data trust and latest reconciliation are clean.

## Remaining Work

- Make frontend ledger actions show this preflight before sync/reconcile buttons.
- Add reconciliation promotion rules that can explicitly mark certain read-only account datasets as ledger-ready.
- Add account-level policies for broker statement, CSV, and read-only account conflict resolution.
