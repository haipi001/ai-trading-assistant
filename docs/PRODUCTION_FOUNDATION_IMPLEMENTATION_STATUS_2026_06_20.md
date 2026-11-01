# Production Foundation Implementation Status

Date: 2026-06-20

## Product stage

The repository now contains a production integration layer, but the product is still a private-beta candidate with external verification blockers. Code availability and external evidence are tracked separately.

## Implemented in code

1. Binance Spot read-only private verification runner, redacted proof references, snapshot/quality/audit packet checks, private file permissions, and fail-closed exit status.
2. OpenAI Responses API provider with exact provider/model allowlist, secret-reference resolution, strict JSON schema output, existing Pydantic evaluator enforcement, and no execution tools.
3. Versioned research eval cases, persisted eval history, dataset summaries, and thesis/snapshot evidence checks.
4. Managed OIDC userinfo login, short-lived signed sessions, server-side revocation metadata, route-wide production auth middleware, RBAC, and query-scope user isolation.
5. Secret reference resolver for environment, AWS Secrets Manager, GCP Secret Manager, and Vault, plus verification/rotation metadata without secret persistence.
6. SLO report, operational event search, backup manifest integration, and a real isolated SQLite backup/restore/integrity/count drill.
7. Invitations, one-time invite code, activation funnel events, pricing administration with billing disabled, and permissioned/redacted data-room artifacts.
8. HTTPS sandbox/paper/testnet-only broker adapter, approved-draft requirement, idempotency, external/local order linkage, audit, and broker-to-ledger reconciliation evidence without auto-repair.
9. Controlled Pilot evidence requirements for legal, limits, monitoring, rollback, kill switch, allowlist, and operations. Passing all evidence only unlocks a separate human review.
10. Chromium desktop/mobile, Firefox, and WebKit tests for daily workflow, risk links, overflow, failure states, accessibility names/focus, and visual regression.
11. Separate managed staging/production Compose overlays with mandatory external PostgreSQL/Redis/OIDC/secret references, immutable images, non-root read-only containers, dropped capabilities, production Next.js standalone serving, and hard-disabled execution.
12. A dry-run-by-default managed release tool for Compose validation, migration, readiness verification and application-image rollback without automatic database downgrade.
13. A non-destructive managed PostgreSQL logical restore tool that restores into a random isolated database, compares migration/schema/count manifests, destroys temporary data, and emits credential-free evidence.

## Verified locally

- Backend: 233 tests passed.
- Frontend TypeScript: passed.
- Python compile check: passed.
- Chromium desktop/mobile: core E2E and quality/visual subsets passed.
- Firefox: 6 cross-browser tests passed.
- WebKit: 6 cross-browser tests passed.
- SQLite isolated restore drill: passed with private evidence excluded from Git.

## External blockers

- No Binance read-only credential reference, private permission screenshot, withdrawal-disabled proof, real account snapshot, or quality report exists in the current environment.
- No OpenAI secret reference or external-call enablement exists; no real model call or longitudinal eval run was executed.
- No OIDC tenant/client or session signing secret reference exists; managed auth was tested with deterministic local fixtures only.
- No AWS/GCP/Vault tenant credentials exist; resolver contracts and tests are present, but no cloud secret was fetched.
- No production monitoring/error-reporting target exists.
- The managed PostgreSQL restore tool exists, but no real managed database drill has been executed in this environment; only local SQLite restore evidence exists.
- Managed staging/production release contracts exist, but no external environment deployment or application rollback has been executed and verified.
- No real broker sandbox URL/token exists; the adapter and reconciliation contract were tested without external submission.
- Legal and operational pilot evidence requires signed human artifacts outside the repository.

## Safety decision

Automatic live trading, wallet signing, withdrawals, DEX swaps, automatic approval, gate bypass, and production broker credentials remain prohibited. `production_execution_allowed` remains false even when every Controlled Pilot evidence gate is present.
