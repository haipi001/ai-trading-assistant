# Phase 01 — Domain Models

## Deliverables

- Core domain types: Instrument, Quote/Bar, Portfolio, Position, TradeIntent, Order, Fill
- Serialization format decisions and versioning

## Implementation Status

- Added SQLAlchemy models and Alembic migration for the Phase 1 core objects.
- Added basic CRUD endpoints for assets, accounts, positions, portfolio snapshots, order intents, order drafts, and audit logs.
- Added the first v4 data-catalog domain model, `DataCatalogEntry`, with lineage metadata, contract metadata, quality status, row count, and `usable_for_trading` gating metadata.
- Order-related endpoints create passive data records only; no broker, exchange, paper execution, or live execution logic exists in Phase 1.

## Remaining Gap

- Full transaction history and investment-ledger models are still pending. The CSV trade import currently records read-only snapshots, not normalized ledger transactions.
