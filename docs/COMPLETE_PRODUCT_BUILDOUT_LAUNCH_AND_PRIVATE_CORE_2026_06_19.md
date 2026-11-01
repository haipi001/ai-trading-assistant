# Complete Product Buildout, Launch Prep, And Private Core - 2026-06-19

This pass extends the complete-product readiness workbench into a concrete buildout plan. It still does not enable real broker orders, CEX trading, wallet signing, withdrawals, DEX swaps, or autonomous live execution.

## Product Buildout Order

| # | Project | Release gate |
|---|---------|--------------|
| 1 | Real onboarding, open/close workflow, and today queue | Founder daily-use alpha |
| 2 | First real authenticated read-only broker or CEX adapter | Private beta data proof |
| 3 | Ledger repair and reconciliation workflow | Trusted portfolio memory |
| 4 | Dataset versioning, snapshot replay, and data promotion | Audit replay ready |
| 5 | Research event feeds, catalyst calendar, and evidence packets | Thesis delta ready |
| 6 | Portfolio allocation, exposure, and stress-risk terminal | Portfolio risk review ready |
| 7 | Notifications, calendar, and escalation | Retention loop ready |
| 8 | Production auth, RBAC, sessions, and privacy controls | Private beta security gate |
| 9 | Billing, plan limits, support, beta admin, and release ops | Paid beta ready |
| 10 | Security engineering, AI safety, and AI governance | Security governance gate |
| 11 | E2E, visual, load, recovery, and release testing | Release candidate gate |
| 12 | Broker sandbox execution stack | Sandbox-only execution proof |

## Launch Preparation

Before private beta:

- Isolate local, staging, production, and sandbox environments.
- Use a managed secret store and secret-reference-only provider credentials.
- Finish production auth, RBAC, session management, and route permission tests.
- Define privacy policy, retention, export, deletion, and audit-export workflows.
- Add external monitoring, logs, tracing, SLOs, cost monitoring, and job failure alerts.
- Execute backup, restore, migration rollback, and incident response drills in staging.
- Run dependency scanning, secret scanning, SAST/DAST, prompt-injection evals, and AI regression evals.
- Prepare support inbox, bug reports, release notes, feedback triage, and beta user operations.

Before public launch:

- Complete qualified legal review of product boundary, terms, privacy, and non-advisory disclaimers.
- Finalize data room: deck, one-pager, demo video, architecture, security plan, legal memo, financial model, and hiring plan.
- Add blue-green or canary release, rollback owner approval, and public release checklist.

## Private Core Boundary

Recommended strategy: open interfaces, private core.

Keep private:

- Decision memory, thesis graph, and behavior-risk learning.
- Gate policy engine, risk scoring, override analysis, and safety orchestration.
- Dataset promotion, entitlement, replay scoring, and provider reliability logic.
- Research delta detection, evidence ranking, and proprietary memo generation.
- Portfolio risk models, scenario stress, liquidity, counterparty, and risk-budget logic.
- Prompt registry, eval sets, model routing, AI provenance, and model disable controls.
- Billing, entitlement, usage metering, beta/admin analytics, and support operations.
- Sandbox-to-live execution safety orchestration, kill switch, rollback, and broker reconciliation internals.

Can be open-sourced after review:

- UI shell without proprietary scoring rules.
- Typed adapter SDK and mock adapters.
- Sample-data fixtures and demo workflows.
- Documentation, schemas, and non-sensitive runbooks.
- MCP/tool protocol interfaces without privileged implementations.
- Sandbox examples that cannot submit production orders.

Never publish secrets, provider keys, customer data, audit logs, production configs, or live execution bypass details.

## Safety-Limited Development Scope

Allowed under the current safety boundary:

- Authenticated read-only sync with secret-reference-only credentials.
- Statement import, manual ledger repair, dataset replay, data promotion, research evidence packets, portfolio risk analytics.
- Opt-in notifications, auth/RBAC, billing sandbox, admin console, security scans, AI governance, E2E, load, and recovery tests.
- Broker sandbox order lifecycle only when production credentials are rejected and account allowlists are enforced.

Forbidden until explicit release gates pass:

- Real broker order submission.
- CEX spot or derivatives trading.
- Wallet signing, transfer, withdrawal, deposit initiation, DEX swap, or bridge.
- Autonomous live execution.
- Secret values stored in the database.
- AI tool access to execution without human approval and audit.

## API Surface

- `GET /complete-product/readiness/buildout/summary`
- `GET /complete-product/readiness/buildout/projects`
- `GET /complete-product/readiness/launch-preparation`
- `GET /complete-product/readiness/private-core`
- `GET /complete-product/readiness/safety-limited-capabilities`

## Verification

```bash
cd backend
.venv/bin/pytest tests/test_complete_product_readiness.py -q
```

```bash
cd frontend
npm run typecheck
```
