# V4 Safe Slices 4, 5, 6

Date: 2026-06-15

This note records the second implementation pass after CSV import and Data Catalog. The scope remains read-only and local-first.

## 4. Real Read-only Adapter Onboarding

Implemented:

- `POST /data-sources/connections/read-only-setup`
- `GET /data-sources/freshness`
- Frontend Data Sources panel for IBKR, Futu, CEX, and Wallet read-only setup.
- Freshness status derived from `DataCatalogEntry`, `DataSnapshot`, and `DataQualityReport`.

Safety boundary:

- Only `credentials_ref` is stored.
- Inline secrets in `config_json` or `credentials_ref` are rejected.
- Config always records `execution_available=false`, `order_routing_available=false`, `withdrawals_allowed=false`, and `signing_available=false`.
- Account sync still requires read-only sample payload or a future authenticated read-only adapter.

## 5. Daily Workflow Depth

Implemented:

- `GET /daily-use/action-queue`
- Daily action queue combines due reminders, high-priority watchlist items, stale/missing/blocked data, and backup recommendations.
- Settings panel can complete or dismiss reminders, deactivate watchlist items, create exports, and create backup manifests.

Safety boundary:

- Daily actions are review tasks only.
- No action can place trades, route orders, sign wallets, or bypass gates.

## 6. Stability, Ops, CI, Secrets, Backups

Implemented:

- `GET /ops/stability-report`
- Preflight checks for database, Redis, data freshness, backup manifest, secret references, operational events, CI wiring, deployment boundary, and execution safety.
- Settings panel renders preflight status and suggested verification commands.

Safety boundary:

- The endpoint only reads state and returns suggested commands.
- It does not deploy, rotate secrets, alter infrastructure, or run shell commands.

## Verification

```bash
cd backend
.venv/bin/pytest tests/test_readonly_setup_daily_ops.py tests/test_data_sources.py tests/test_daily_use.py tests/test_beta_readiness.py -q

cd frontend
npm run typecheck
```

Focused result during implementation: `27 passed`; frontend typecheck passed.
