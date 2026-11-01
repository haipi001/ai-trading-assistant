# Product Stage Audit And Roadmap - 2026-06-19

## Scope Reviewed

- Workspace communication records under `/Users/lizekai/Documents/交易系统/沟通记录`.
- Memory-bank indexes and latest AI Trading OS records under `/Users/lizekai/Documents/仓库/Codex/记忆库`.
- Core product docs: `PROJECT_BRIEF.md`, `ROADMAP.md`, `README.md`, `docs/ARCHITECTURE.md`, V4 gap/readiness/fundraising docs.
- Backend FastAPI app, SQLAlchemy models, Alembic migrations, services, adapters, schemas, and tests.
- Frontend Next.js workspace shell, module panels, typed backend client, i18n messages, and smoke/typecheck configuration.

## Executive Stage Judgment

AI Trading OS is currently in a strong local engineering alpha / founder-demo alpha stage.

It is no longer a concept-only project. The repo has a working backend, frontend terminal, migrations, broad test coverage, demo seed path, safe paper execution, data catalog, ledger/reconciliation surfaces, self-logic models, decision gates, behavior/risk checks, Web3 read-only monitoring, readiness dashboards, and live-execution preflight packets.

It is not yet a complete product or private beta product. The most important missing proof is real authenticated read-only account data, production-grade auth/secrets/ops, a narrow ICP daily workflow, real beta users, AI eval quality with a real provider, and a polished onboarding/demo path.

It is also not a live trading system. Real broker execution, CEX trading, wallet signing, DEX swaps, withdrawals, and autonomous live execution remain intentionally absent or blocked.

## Product Narrative From Communication Records

The communication history converges on five stable decisions:

1. The product should be an AI-native personal financial terminal, not a stock-picking chatbot.
2. It should support both manual and automated workflows, and both stock-market and Web3 assets, but automation must be permissioned and fail-closed.
3. The differentiator is investment memory: thesis capture, self-logic, behavior intervention, gate checks, journal, and monthly review.
4. The interface should be a terminal workspace with dense financial context, AI command bar, risk/action panels, and module workspaces, not a full-screen chat interface.
5. Bloomberg and FinceptTerminal are product-shape references, but the wedge is different: personal multi-asset investors who need decision discipline, not an institutional Bloomberg clone.

## Current Implemented Capabilities

### Backend

- FastAPI app with 30+ registered API modules and about 240 route handlers.
- SQLAlchemy model surface covering assets, accounts, positions, quotes, candles, data sources, data snapshots, data quality, data catalog, ledger, reconciliation, daily-use records, beta/user/secret references, live-execution configs, portfolio snapshots, research reports, signals, risk checks, self-logic, strategy rules, backtests, workflows, Web3 risk, orders, approvals, paper executions, tax lots, corporate actions, journal/review, playbook proposals, and audit logs.
- 17 Alembic migration files through `20260616_0017`.
- 38 backend test files with 214 test functions passing in the current regression run.
- Deterministic demo seed and smoke flow.

### Product Logic

- Required trade path exists as architecture and partial implementation:
  InvestmentConstitution -> StrategyPlaybook -> InvestmentThesis -> gates -> risk/behavior -> OrderIntent -> OrderDraft -> approval -> paper execution -> journal -> review.
- Decision gates and risk engine block unsafe progression.
- Behavior engine creates interventions and thesis conflicts.
- Automation policy defaults to read-only and blocks future-only adaptive automation.
- Live-execution service writes blocked records and audit trail but does not submit broker orders.

### Data

- CSV imports for holdings, crypto holdings, wallet balances, and trades.
- Public read-only market data adapters: mock, Stooq, Yahoo Finance, custom HTTP read-only.
- Metadata-only IBKR/Futu/CEX/wallet read-only setup/preflight/certification.
- Data catalog overview, provenance, trust, contract-enforcement, freshness, and detail views.
- Ledger sync, statement import, reconciliation, extended cash/tax-lot/corporate-action checks.

### AI And Research

- Mock AI provider, report schema validation, AI report evaluator, prompt files.
- Multi-agent research committee with deterministic structured-output validation.
- OpenAI provider remains a placeholder and makes no external calls.
- Research outputs are review-only and cannot execute trades.

### Frontend

- Next.js terminal workspace with sidebar modules: overview, portfolio, holdings, theses, strategy/playbook, AI research, signals, risk, decision gates, order drafts/execution, journal, reviews, Web3, data sources, constitution, automation, fundraising, complete product, settings.
- Typed backend client exposes many backend packets and workflows.
- Readiness dashboards make product gaps visible, including complete-product and fundraising-readiness workspaces.
- UI has the intended dark terminal style and module-first information architecture.

## Verification

Current run:

```bash
cd /Users/lizekai/Documents/交易系统/ai-trading-os
./scripts/regression_check.sh
```

Result:

- Backend: `214 passed in 21.24s`.
- Alembic migration smoke: passed through `20260616_0017`.
- Frontend typecheck: passed.
- Demo smoke: skipped because backend was not running at `http://127.0.0.1:8000`.
- E2E smoke: not run because `RUN_E2E=1` was not set.

## Distance To Complete Product

| Dimension | Current Stage | Estimated Progress |
| --- | --- | ---: |
| Local engineering demo | Stable local alpha | 80% |
| Safety architecture | Strong safe-by-default foundation | 80% |
| Self-logic workflow | Broadly modeled, partially interactive | 70% |
| Terminal UI coverage | Broad module coverage, needs polish and coherence | 65% |
| Paper execution/review loop | Functional safe slice | 65% |
| Data trust/ledger | Good local/read-only surfaces, real sync missing | 55% |
| Real data integration | Public/read-only + placeholders | 40% |
| Production security/ops | Mostly readiness metadata | 30% |
| AI quality with real LLMs | Mock/eval foundation only | 30% |
| Beta/traction/commercialization | Readiness surfaces only | 15% |
| True live execution | Intentionally not implemented | 10% |

Overall complete-product progress: roughly 50-60% for a credible local alpha, 35-45% for private beta, and 20-30% for production/commercial readiness.

## Main Product Gaps

1. No real authenticated read-only broker/CEX/wallet adapter yet.
2. No production auth/session/RBAC/secret-manager stack.
3. ICP and killer daily workflow are still too broad.
4. Many latest "developed" items are readiness packets, not finished operational capabilities.
5. Real onboarding and first-run experience are not yet the product center.
6. Ledger repair/reconciliation is visible but not yet a trusted automatic workflow.
7. Research/event feeds and evidence packets are mostly modeled, not real source-backed.
8. Portfolio risk depth is still early: exposure, factor/theme/sector, scenario stress, and drawdown budget need product-grade screens and calculations.
9. Notifications/calendar/escalation are mostly planned.
10. AI provider, prompt registry, eval dashboard, and governance are not production-grade.
11. Beta invite, waitlist, analytics, pricing, support, and admin are not real systems yet.
12. E2E/mobile/visual/load/recovery testing are not complete.
13. Live sandbox is preflight/report only; no actual sandbox broker adapter.

## Important Code-Level Improvement Notes

- `frontend/app/components/layout/WorkspaceShell.tsx` should include `fundraising_readiness` and `complete_product` in `MODULE_IDS`; otherwise those URLs can render the page while the shell resolves the active module as overview.
- `Settings.automation_level` now defaults to `A0_READ_ONLY`; legacy L0-L3 inputs are accepted only as schema aliases and normalized before service logic.
- Several route surfaces are readiness/report packets with `execution_available=false`; keep UI copy explicit so users do not mistake them for completed external integrations.
- Direct `POST /orders/drafts` exists and is guarded by latest risk check, but the preferred path is order intent -> decision gates -> risk -> draft. Future UX should hide direct draft creation except admin/debug contexts.
- Public adapters and placeholders should expose source limitation clearly in the UI: delayed/public/sample-only/authenticated-read-only/not-trading-usable.

## Product Improvement Directions

### 1. Narrow The Product Wedge

Choose one beachhead ICP for the next milestone. Recommended first ICP:

Self-directed cross-market investor holding US stocks/ETFs plus crypto assets, who already makes thesis-driven decisions but loses discipline because data, rationale, alerts, and reviews are scattered.

Daily product promise:

"Every morning, the terminal tells me what changed, whether my thesis still holds, what risks need attention, and what action is allowed or blocked by my own rules."

### 2. Turn Readiness Into Real Workflow

The readiness dashboards are useful internally, but the product experience should start with:

- connect/import data
- inspect trust status
- create or repair thesis
- review today's actions
- block unsafe draft
- close review loop

### 3. Build Trust Before Execution

The next value step is not live trading. It is trusted read-only memory:

- one real read-only account sync
- statement import normalization
- ledger reconciliation
- dataset promotion
- evidence-backed AI summaries

### 4. Make AI A Controlled Research Layer

Bring in real LLM only behind strict controls:

- prompt registry
- source citations
- evidence packet
- unsupported-claim rejection
- stale-data rejection
- order-leakage red team
- model disable switch

### 5. Polish The Terminal UX

Move from "many panels" to "one coherent daily terminal":

- first-run onboarding
- empty states
- global action queue
- drilldowns from holding -> thesis -> gate -> order -> review
- mobile review/check flows
- one-click demo reset and guided investor demo

## Product Development Roadmap

### Phase 1 - Founder Daily-Use Alpha

Goal: make the local product useful every day for the founder.

Deliver:

- Fix module routing mismatch.
- One first-run onboarding path.
- Daily open/close workflow.
- Today's action queue as the main entry.
- Holding -> thesis -> gate -> review drilldown.
- Clear empty/error states.
- Guided demo reset.

Exit criteria:

- A user can open the terminal and know the next 3 actions without reading docs.
- Demo path runs in under 7 minutes.
- Regression + E2E smoke pass.

### Phase 2 - Real Read-Only Data Proof

Goal: prove the terminal can ingest real account data safely.

Deliver:

- One authenticated read-only adapter: choose IBKR, Futu, or one CEX first.
- Secret-reference-only auth.
- Positions, balances, transactions, data freshness, and sync audit.
- No trading scopes, no withdrawal scopes, no signing.
- Real account snapshot -> data catalog -> ledger preflight.

Exit criteria:

- One real account sync works without trading authority.
- UI can explain what is trusted, stale, blocked, or review-only.

### Phase 3 - Trusted Ledger And Data Promotion

Goal: make portfolio memory reliable enough for user decisions.

Deliver:

- Statement import normalization for fills, fees, cash, dividends, transfers, FX, and corporate actions.
- Reconciliation exception workflow.
- Dataset versioning and snapshot replay.
- Promotion rules from review-only to ledger-ready.
- Manual repair workflow with audit trail.

Exit criteria:

- Product can answer "why do you trust this position/cost/cash number?"
- Bad data fails closed before gates/order drafts.

### Phase 4 - Research Evidence And Thesis Delta

Goal: make AI useful because it reads grounded evidence, not because it sounds fluent.

Deliver:

- Real LLM provider behind disabled-by-default safe adapter.
- News/filings/macro/on-chain event feeds.
- Catalyst calendar.
- Evidence packets attached to research and thesis changes.
- AI eval suite and prompt registry.

Exit criteria:

- AI report can be reproduced from evidence and rejected when unsupported.
- Thesis monitor can say support/weaken/invalidate/data insufficient with citations.

### Phase 5 - Portfolio Risk Terminal

Goal: make the terminal valuable even without trading.

Deliver:

- Allocation, sector/theme/factor exposure.
- Concentration, liquidity, counterparty, stablecoin, CEX, wallet, and DeFi exposure.
- Scenario stress and drawdown budget.
- Risk budget drift and next actions.

Exit criteria:

- User can understand portfolio risk and thesis risk in one workspace.

### Phase 6 - Private Beta Foundation

Goal: safely host external users and real read-only data.

Deliver:

- Auth, sessions, RBAC.
- Secret manager.
- Local/staging/prod separation.
- Monitoring, logs, error reporting, backups, restore drills.
- Audit retention, export/delete/privacy controls.
- Beta invite flow and admin console.

Exit criteria:

- 10-30 beta users can be onboarded without local-only assumptions.

### Phase 7 - Traction And Commercial Loop

Goal: prove users return and may pay.

Deliver:

- Waitlist/landing page.
- Activation, retention, review-completion, thesis-coverage, and sync-success analytics.
- Pricing experiments.
- Support inbox and feedback tagging.
- Investor demo video, deck, one-pager, and data room.

Exit criteria:

- 10-30 beta users or 3-5 qualified pilot prospects.
- At least one repeated weekly usage loop.

### Phase 8 - Broker Sandbox Execution Proof

Goal: prove future live execution path without enabling real production trading.

Deliver:

- Broker sandbox adapter.
- Account allowlist.
- Idempotency keys.
- Order-state reconciliation.
- Cancel/replace path.
- Signed approval packet.
- Kill switch and rollback drill.

Exit criteria:

- Sandbox order lifecycle is auditable end to end.
- Production live trading remains disabled.

### Phase 9 - Controlled Pilot

Goal: only after the above gates, test tiny-notional controlled live pilot if legally and operationally cleared.

Deliver:

- Legal/compliance memo.
- Small-notional policy.
- Human approval packet.
- Kill switch exercise.
- Incident response runbook.
- Post-pilot reconciliation and review.

Exit criteria:

- Controlled live action is optional, gated, reversible, and not part of the core product promise.

## Recommended Immediate Next 10 Tasks

2026-06-19 code pass status:

- `WorkspaceShell.tsx` module ID mismatch for `fundraising_readiness` and `complete_product` is fixed.
- Automation naming is now centered on the `A0_READ_ONLY` family across defaults, Docker, frontend copy, service logic, tests, and docs. Legacy L0-L3 request values are retained only as normalized schema aliases.
- Today Action Queue is promoted to the first overview entry and the pending-actions card routes into the same queue behavior.
- `binance_spot_readonly` adds a real authenticated read-only account adapter using env-referenced credentials, timestamped HMAC signing, and audited account snapshot sync; execution, order routing, withdrawals, and signing remain unavailable.
- Fundraising and complete-product readiness payloads now mark readiness/report/packet surfaces as preflight capabilities with `capability_kind=preflight_capability` and `production_capability=false`.
- The nine-phase plan is exposed through `/product-roadmap/summary`, `/product-roadmap/phases`, and `/product-roadmap/phases/{phase_no}`, and is visible in the Complete Product panel.

1. Build first-run onboarding and daily open/close workflow.
2. Run `binance_spot_readonly` against a real read-only key in a private environment and record the evidence packet.
3. Add provider credential-reference UX with explicit forbidden scopes.
4. Build ledger exception repair UI.
5. Define raw/reviewed/trusted data-promotion states and gate usage by state.
6. Add one-click guided demo reset and demo script.
7. Add Playwright E2E for the core daily-use demo path.
8. Start ICP memo and private beta interview/LOI packet.
9. Add waitlist and first activation/retention analytics.
10. Draft sandbox adapter contract while keeping production execution locked.

## Bottom Line

The product has a real foundation and a distinctive direction. Its strongest asset is not execution automation; it is safe investment memory and self-logic enforcement.

The next stage should convert the strong local alpha into a daily-use read-only terminal with one real data integration, one narrow user segment, and one polished repeated workflow. Live execution should stay behind later sandbox and compliance gates.
