# Baseline Health

This document locks the current v4 Phase 0 health baseline for local self-use and future product hardening work.

Phase 0 proves the scaffold remains runnable after Phase -1 product/rules alignment. It does not introduce new schemas, APIs, adapters, or execution paths.

## Baseline Command

Run the full local baseline from the repository root:

```bash
./scripts/regression_check.sh
```

The script verifies:

- backend pytest suite
- Alembic upgrade from an empty temporary SQLite database to `head`
- frontend TypeScript typecheck
- demo smoke when a backend server is reachable at `BACKEND_URL`
- optional frontend e2e smoke when `RUN_E2E=1`

Useful switches:

```bash
RUN_MIGRATION_SMOKE=0 ./scripts/regression_check.sh
RUN_E2E=1 ./scripts/regression_check.sh
BACKEND_URL=http://127.0.0.1:8000 ./scripts/regression_check.sh
```

## Demo Seed Baseline

The demo seed is covered by both:

- `backend/tests/test_demo_seed.py`
- `scripts/demo_smoke.py` when the backend is running

The expected official flow remains:

1. data import
2. holdings
3. thesis
4. gates
5. order draft
6. approval
7. paper fill
8. journal
9. monthly review

## Migration Baseline

`scripts/regression_check.sh` now runs Alembic against a temporary local SQLite file. This catches broken revision chains, missing model imports, and obvious DDL regressions without touching local PostgreSQL data.

For a real deployment database, still run:

```bash
cd backend
alembic upgrade head
```

## Frontend Hydration Watchlist

Known Stage 0 watch item:

- `H-001`: several client-rendered panels still format server-provided timestamps with browser locale helpers such as `toLocaleString()`. This can produce hydration warnings if server and browser locale/time zone output differs. The top command bar data-update timestamp was moved behind client hydration in the 10/11/12 slice; broader timestamp cleanup remains a watch item.

Current mitigation:

- Keep the issue visible in this baseline document.
- Treat new hydration warnings in browser verification as regressions.
- Prefer explicit locale and `timeZone` options, or client-only formatting, when touching timestamp UI in later phases.

This Stage 0 pass does not redesign all timestamp formatting because that is a broad UI sweep and not required for the baseline lock.

## Safety Boundary

The baseline check must not:

- enable live trading
- call a real broker, exchange, or wallet
- store raw credentials
- bypass gates, risk, approval, audit, journal, or review
- build wallet signing, DEX swaps, bridge transactions, token approvals, or withdrawal-enabled CEX flows
