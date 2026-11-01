# Phase 00 — Scaffold

## Objective

Keep the local v4 scaffold healthy before adding new implementation phases.

This repository already contains a working FastAPI backend, Alembic migrations, pytest suite, Next.js frontend, Docker Compose scaffold, local demo seed, and regression script. Phase 0 is the guardrail that proves those foundations still run before later slices add CSV import, data catalog work, adapters, or new trading workflow features.

## Deliverables

- Repo structure, docs, and task cards
- Safety-first conventions documented
- Backend app scaffold with health endpoint
- Alembic migration chain
- Frontend app scaffold and terminal workspace shell
- Local demo seed and smoke script
- Regression script covering backend tests, migration smoke, frontend typecheck, and optional e2e
- Baseline health document

## Baseline Command

Run from the repository root:

```bash
./scripts/regression_check.sh
```

The baseline is defined in `docs/BASELINE_HEALTH.md`.

## Acceptance

- Backend tests pass.
- Alembic upgrades a temporary empty SQLite database to `head`.
- Frontend TypeScript typecheck passes.
- Demo smoke passes when a backend server is running.
- Optional frontend e2e passes when `RUN_E2E=1` and both local servers are running.
- Live trading remains disabled by default.
- No real broker, exchange, wallet, private key, seed phrase, signing, DEX swap, or live order execution is introduced.

## Out Of Scope

- CSV import implementation.
- New data catalog tables.
- Authenticated IBKR, Futu, CEX, or wallet adapters.
- Live execution.
- Controlled auto execution.
