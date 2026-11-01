# Phase 02 — Data Adapters

## Deliverables

- Mock adapters for dev/testing
- Normalization rules and validation

## Implementation Status

- Added typed adapter interfaces for market data, broker data, crypto exchange data, and on-chain read data.
- Added deterministic mock adapters for stocks, crypto exchange balances, and on-chain wallet reads.
- Added a manual CSV import safe slice for holdings, crypto holdings, wallet balances, and trade-history files through `POST /imports/csv`.
- Added demo CSV files under `backend/data/demo_csv/` for local onboarding and regression checks.
- Added mock import/update API endpoints:
  - `POST /mock/import-accounts`
  - `POST /mock/import-positions`
  - `POST /mock/update-quotes`
- CSV, mock, public quote, candle, and account-placeholder ingestion all remain read-only. `place_order` remains blocked with `NotImplementedError`; Phase 2 has no execution path.
