# ROADMAP.md — AI Trading OS v4 Master Roadmap

2026-11-01 起，当前整体实施顺序以 [r127 整体规划](docs/planning/R127_OVERALL_PLAN_2026_11_01.md) 为准；保留现有 r127 UI，分 T0–T7 推进。原工程包、113 项执行任务和 95 项 UI 覆盖位于该规划目录。以下历史领域模型与安全原则继续适用。

历史后续开发目标与验收顺序见 [docs/DEVELOPMENT_GOALS_2026_07_16.md](docs/DEVELOPMENT_GOALS_2026_07_16.md)。该文档把历史阶段、已完成能力和真实待开发目标分开管理。

## Product Direction

AI Trading OS is an AI-native Personal Financial Terminal, not a black-box trading bot.

It automates the user's investment workflow, trading workflow, risk discipline, self-logic review, and decision journaling while keeping execution authority constrained by policy, gates, approval, and audit logs.

The v4 wedge is a personal financial operating system for multi-asset investors: it unifies portfolio memory, thesis memory, risk discipline, Web3 read-only risk, and decision-quality review. It should never promise profit or present itself as investment advice.

## Core Principle

Automate the user's investment process and self-discipline, not uncontrolled trading.

AI may research, summarize, explain, detect changes, and propose actions.
AI must never directly execute trades.

## Required Architecture Layers

1. Terminal Workspace Layer
2. Data Adapter Layer
3. Data Catalog Layer
4. Data Contract Layer
5. Portfolio Memory Layer
6. Investment Ledger Layer
7. Investment Constitution Layer
8. Strategy Playbook Layer
9. Investment Thesis Layer
10. Research Automation Layer
11. Signal & Alpha Lab Layer
12. Decision Gate Layer
13. Risk Engine Layer
14. Behavior Engine Layer
15. Automation Policy Layer
16. Order Workflow State Machine
17. Approval Workflow Layer
18. Execution Adapter Layer
19. Journal & Review Layer
20. Web3 Risk Automation Layer
21. AI Command Bar Layer
22. MCP / Tool Layer
23. Observability & Audit Layer

RiskEngine is mandatory, but it is not the highest-level guardrail.
InvestmentConstitution, StrategyPlaybook, and InvestmentThesis sit upstream of gates, risk, behavior checks, order workflow, approvals, execution, and reviews.

## Mandatory Workflow

Every trade-related workflow must follow:

InvestmentConstitution
-> StrategyPlaybook
-> InvestmentThesis
-> ResearchGate
-> ThesisGate
-> RiskGate
-> BehaviorGate
-> ExecutionGate
-> OrderIntent
-> OrderDraft
-> ApprovalPolicy
-> PaperExecution or LiveExecution
-> TradeJournal
-> PostTradeReview
-> MonthlyDecisionReview

## Default Safety Settings

- `live_trading_enabled = false`
- `automation_level = A0_READ_ONLY`
- Web3 is read-only.
- No private keys.
- No seed phrases.
- No withdrawal-enabled CEX keys.
- No LLM direct execution.
- No signal direct execution.
- No strategy direct execution.

## Build Order

Do not start with broker integration.

## V4 Phase Execution Index

New work should follow this phase order. Existing v3 task names, migrations, and docs describe already-built historical slices and do not grant permission to skip v4 safety gates.

| Phase | Implementation Target | Current Guidance |
| --- | --- | --- |
| Phase -1 | Product Wedge Docs | Align product definition, safety posture, open-source policy, and development order. |
| Phase 0 | Project Scaffold | Keep local scaffold, regression baseline, migrations, frontend typecheck, and demo smoke healthy. |
| Phase 1 | Core Domain Models | Extend only when gaps remain after auditing existing models. |
| Phase 2 | CSV Import + Demo Data | Prefer local import before any authenticated broker or exchange API. |
| Phase 3 | Portfolio Memory | Maintain deterministic portfolio state from typed data snapshots. |
| Phase 4 | Investment Constitution | Make self-logic required before automation. |
| Phase 5 | Strategy Playbook | Keep strategy rules above order workflow. |
| Phase 6 | Investment Thesis | Tie positions and orders to rationale. |
| Phase 7 | Thesis Capture + Thesis Monitor | Use structured facts and fail closed on insufficient data. |
| Phase 8 | Decision Gates | Preserve ResearchGate, ThesisGate, RiskGate, BehaviorGate, and ExecutionGate ordering. |
| Phase 9 | Risk Engine | Enforce hard constraints and kill switches. |
| Phase 10 | Behavior Engine | Detect FOMO, panic selling, overtrading, thesis conflict, and concentration drift. |
| Phase 11 | Workflow State Machine | Block skipped gates and record blocked transitions. |
| Phase 12 | Automation Policy | Default to A0_READ_ONLY and reject future-only modes. |
| Phase 13 | Order Intent + Order Draft | Draft only after gates and policy. |
| Phase 14 | Approval Workflow | Require explicit approval for execution paths. |
| Phase 15 | Paper Execution | Keep paper execution downstream of approval and audit. |
| Phase 16 | Trade Journal | Preserve decision/rationale context. |
| Phase 17 | Monthly Decision Review | Focus on decision quality, not return promises. |
| Phase 18 | AI Research Reports + MockAIProvider | Structured, cited, evaluated outputs only. |
| Phase 19 | AI Evals | Reject hallucinated, unsupported, or executable advice output. |
| Phase 20 | AI Command Bar | Typed tool router, not a free-form execution channel. |
| Phase 21 | Terminal Workspace UI | Dense terminal workspaces with clear risk and thesis states. |
| Phase 22 | Web3 Read-only Risk | Public address monitoring only. |
| Phase 23 | Data Catalog | Track datasets, lineage, quality, and use permissions. |
| Phase 24 | yfinance Adapter | Public read-only prototype data. |
| Phase 25 | ccxt Read-only Adapter | Market/account read-only only; no trading keys. |
| Phase 26 | web3.py Read-only Adapter | Public-chain reads only; no signing. |
| Phase 27 | Backtest Lab | Research-only, not live execution. |
| Phase 28 | Signal Lab | Signals cannot bypass gates. |
| Phase 29 | MCP Server | Tools cannot bypass the main control system. |
| Phase 30 | Real API Read-only Adapters | Authenticated read-only after local import path is solid. |
| Phase 31 | Approval-based Live Execution | Explicitly requested later; disabled by default. |
| Phase 32 | Controlled Auto Execution | Explicitly requested later; strict policy and kill switch required. |
| Phase 33 | Advanced AI / Kronos / Qlib / Sidecars | Reference or sidecar only; never main control bypass. |

Start with Phase -1 and Phase 0 only unless explicitly instructed to continue.

## Historical Prompt Execution Index

Use this index only when referring to already-completed historical v3 implementation slices:

| Prompt | Implementation Target |
| --- | --- |
| 第 0 次 | 更新 `AGENTS.md` / `PROJECT_BRIEF.md` / `ROADMAP.md` |
| 第 1 次 | 实现 v3 核心数据模型 |
| 第 2 次 | 实现 Workflow State Machine |
| 第 3 次 | 实现 Decision Gates |
| 第 4 次 | 实现 Thesis Capture / Monitor |
| 第 5 次 | 实现 Behavior Engine |
| 第 6 次 | 实现 Automation Policy Engine |
| 第 7 次 | 实现 Portfolio Memory |
| 第 8 次 | 实现 AI Research + AI Evals |
| 第 9 次 | 实现 AI Command Bar |
| 第 10 次 | 实现 Order Draft + Approval |
| 第 11 次 | 实现 Paper Trading |
| 第 12 次 | 实现 Monthly Decision Review |
| 第 13 次 | 实现 Terminal Workspace UI |
| 第 14 次 | 实现 Web3 Risk Read-only |
| 第 15 次以后 | 再接 IBKR / Futu / CEX / wallet read-only |

### Prompt 0 — Project Rules And Docs

Build:

- project rules
- product definition
- architecture boundaries
- safety defaults
- roadmap
- task acceptance standards

Acceptance:

- docs describe the terminal product clearly
- no execution features are introduced
- no broker integration is introduced

### Prompt 1 — Core Domain Models

Build:

- Asset, Account, Position, Quote, Candle
- PortfolioSnapshot
- ResearchReport, AgentRun, Signal
- RiskCheck, OrderIntent, OrderDraft, Approval, Execution
- TradeJournalEntry, AuditLog
- InvestmentConstitution, RiskBudget
- StrategyPlaybook
- InvestmentThesis, ThesisCheckpoint, ThesisViolation
- DecisionGate, BehaviorPattern, BehaviorIntervention
- AutomationPolicy, WorkflowState, MonthlyDecisionReview

Acceptance:

- migrations exist
- typed schemas exist
- CRUD foundation exists
- tests pass
- live trading remains disabled

### Prompt 2 — Workflow State Machine

Build:

- WorkflowEngine
- allowed lifecycle states
- transition validation
- blocked transition recording
- workflow timeline API
- transition AuditLog

Acceptance:

- invalid transitions are rejected
- gates cannot be skipped
- live execution is blocked by default

### Prompt 3 — Decision Gates

Build:

- ResearchGate
- ThesisGate
- RiskGate
- BehaviorGate
- ExecutionGate
- gate result storage
- fail-closed uncertainty handling

Acceptance:

- missing data blocks progression
- all gate results are stored
- gate failures write AuditLog
- no execution occurs

### Prompt 4 — Thesis Capture

Build:

- ThesisCaptureService
- ThesisMonitorService
- thesis prompt templates
- ThesisCheckpoint creation
- ThesisViolation support

Acceptance:

- thesis capture cannot create orders
- insufficient data returns DATA_INSUFFICIENT
- invalid AI output is rejected

### Prompt 5 — Behavior Engine

Build:

- behavior pattern detection
- BehaviorIntervention generation
- thesis-conflict detection
- intervention levels: SILENT_RECORD, SOFT_WARNING, HARD_CONFIRM, BLOCK

Acceptance:

- harmful patterns create interventions
- thesis conflicts create ThesisViolation
- no execution occurs

### Prompt 6 — Automation Policy

Build:

- AutomationPolicyEngine
- effective policy resolution
- A0 through A5 permission checks
- A6 rejection as future-only

Acceptance:

- default policy is A0_READ_ONLY
- A3 can draft but cannot execute
- A4 requires approval
- A5 is whitelisted and constrained
- live execution is blocked by default

### Prompt 7 — Portfolio Memory

Build:

- current portfolio view
- position valuation
- allocation calculation
- PnL calculation
- exposure calculation
- deterministic daily summary

Acceptance:

- portfolio snapshot works
- daily summary works
- no LLM and no trading

### Prompt 8 — AI Research And Evals

Build:

- AIProvider interface
- MockAIProvider
- OpenAIProvider placeholder
- ResearchReport generator
- AIReportEvaluator
- multi-agent research workflow

Acceptance:

- reports cite data_snapshot_id
- facts come from structured input data
- invalid JSON is rejected and logged
- agents cannot execute trades

### Prompt 9 — AI Command Bar

Build:

- deterministic intent detection
- typed tool routing
- command logs
- tool call logs
- command results
- permission checks

Acceptance:

- command bar is not free-form execution
- execution requests are rejected
- order intent creation requires policy
- audit logs are written

### Prompt 10 — Order Draft And Approval

Build:

- order draft workflow
- approval policy
- approve/reject/modify flow
- audit logs

Acceptance:

- no draft before required gates
- risk-failed drafts cannot be approved
- no execution without approval policy

### Prompt 11 — Paper Trading

Current status:

- implemented safe slice: approved `OrderDraft` -> `PaperExecution` -> simulated cash/position update -> `TradeJournalEntry` -> pending `PostTradeReview` -> `AuditLog`
- P0.5 implemented: partial paper fills, repeated fills until completion, buy-side paper tax lots, FIFO sell-lot realization, and realized PnL/cost-basis/proceeds fields
- not yet implemented: advanced tax-lot accounting, dividends/corporate actions, automatic playbook updates

Build:

- paper broker
- paper execution service
- fee and slippage model
- portfolio update from paper fills
- audit logs

Acceptance:

- paper execution cannot bypass gates
- paper execution cannot enable live trading

### Prompt 12 — Monthly Decision Review

Build:

- MonthlyDecisionReview generation
- planned vs impulsive attribution
- thesis-aligned vs thesis-violating attribution
- behavior summary
- rule update proposals

Acceptance:

- review distinguishes performance attribution from decision attribution
- suggestions require user approval
- no direct investment advice

### Prompt 13 — Terminal Workspace UI

Build:

- portfolio workspace
- research workspace
- thesis workspace
- signal workspace
- order review workspace
- journal workspace
- monthly review workspace
- AI command bar UI

Acceptance:

- users navigate workflows through terminal workspaces
- AI actions are contextual and permissioned

### Prompt 14 — Web3 Read-only Risk Automation

Build:

- wallet registration by public address
- token balances
- token allowances
- transfer monitoring
- protocol exposure
- exchange exposure
- stablecoin exposure
- on-chain risk alerts

Do not build:

- seed phrase input
- private key storage
- signing
- transaction building
- DEX swap execution

Acceptance:

- Web3 is read-only by default
- no signing capability exists
- alerts only

### Prompt 15+ — Real API Read-only Adapters

Current status:

- P1 safe slice implemented: `DataSourceConnection`, read-only provider registry, `mock_market_data`, `stooq_public_eod`, `yfinance_public`, `custom_http_readonly`, health checks, quote import, candle import, `DataSnapshot`, `DataQualityReport`, and audit logs
- frontend data-source workspace can enable default read-only sources, register a custom placeholder, check health, import quote snapshots, run manual candle refresh, run manual signal generation, and surface a lightweight signal review queue
- still not implemented: IBKR/Futu/CEX account sync, authenticated providers, broker state reconciliation, wallet read adapters beyond existing Web3 risk slice, automatic cron-style refresh and review queue orchestration beyond current manual-run scheduled jobs

Build:

- yfinance prototype adapter
- IBKR read-only skeleton
- Futu read-only skeleton
- ccxt read-only adapter
- web3.py read-only adapter

Do not build:

- live trading
- automatic execution
- withdrawal-enabled CEX keys

Acceptance:

- interfaces are typed
- tests use mocks
- credentials are optional and never committed

### Later — Approval-based Live Execution

Build:

- live execution interface
- manual approval policy
- broker state checks
- execution state checks
- fail-closed behavior

Acceptance:

- live trading disabled by default
- no LLM can call execution
- every live order has full gate, approval, and audit history

### Later — Controlled Automation

Build:

- controlled DCA
- controlled rebalance
- controlled stop-loss
- controlled take-profit
- strict whitelists
- kill switch
- intervention escalation

Acceptance:

- controlled automation requires InvestmentConstitution
- strategy requires StrategyPlaybook
- all gates must pass
- audit logs are complete

## Later Advanced Modules

Evaluate only after core safety architecture is mature:

- Kronos predictor feature
- Qlib research workflow
- FinRL research-only experiments
- Freqtrade sidecar
- Hummingbot sidecar
- LEAN or NautilusTrader evaluation

No external project, sidecar, or advanced module may bypass RiskEngine, BehaviorGate, ApprovalPolicy, decision gates, or AuditLog.

## Task Acceptance Standards

Every task must include, when applicable:

- migrations if schema changes
- typed schemas
- services
- API endpoints
- tests
- audit logs
- docs updates
- no live trading by default
- no execution bypass

## Completion Response Required

After each task, provide:

1. Summary of implementation
2. Files changed
3. Commands run
4. Test results
5. Safety review
6. What was intentionally not implemented
7. Next smallest useful task

## Status Log

### 2026-07-05 — Real LLM First-Pass Verification And Safety Harness

Completed:

- `reports` / `theses` / `human_control` services accept a DeepSeek provider branch with the same gates as OpenAI (external-calls flag, provider:model allowlist, secret reference).
- Real DeepSeek end-to-end verification for research report generation and thesis capture; outputs passed project schema validation.
- Eval runner (`run_case`) accepts `provider_name` and is no longer hardcoded to OpenAI.
- Frontend Settings / Data Sources panels show DeepSeek configuration state.
- All 12 reference eval cases ran against a real provider for the first time.
- Fixed: exact-match `"review_only"` eval check that failed all real-LLM natural-language output regardless of quality.
- Fixed: blocked-action term list matched only snake_case tokens (`market_order`) and missed natural language ("market order") — the execution-leakage gate was near-ineffective against real output.
- Added normalized multilingual blocked-action detector (`app/ai/safety.py`), red-team registry/runner (17 cases EN/ZH/mixed/disguised, `docs/RED_TEAM_CASES.md`), provider comparison in eval summary, and regression tests. Backend suite: 320 passed.

Current judgment:

- AI provider integration moved from Mock-only to real-provider proof. This is a first-pass verification, not production-grade AI safety: `hallucination_rate` remains null until human-labeled review exists, long-run provider comparison has not started, and real exchange read-only key verification is still pending.

Next:

1. Rotate the DeepSeek key (it appeared in a plaintext working session).
2. Human-label the first eval batch; fill `hallucination_rate` from labels only.
3. Expand bilingual red-team execution-leakage cases.
4. Run `binance_spot_readonly` private verification with a real read-only key.

### 2026-07-06 — Eval Registry Expansion, Human Labeling, Red-Team Growth

Completed:

- Eval cases now carry `task_type`: research_report (default) plus thesis_capture / thesis_monitor / thesis_violation_message, dispatched to provider generation methods with schema validation and blocked-action scanning. Reference dataset grew 12 → 15 cases.
- Human labeling workflow: `POST /production/research/eval-results/{id}/label` stores hallucination/blocked-action/direct-advice labels with labeler identity; `summary()` now computes `hallucination_rate` exclusively from human-labeled runs (`human_labeled_runs` reported; stays null with zero labels).
- Red-team registry grew 17 → 27 cases: euphemisms (pull the trigger / get me in / 全仓买入 / 梭哈), buried mid-text instructions, system-prompt bypass, no-confirmation phrasing, zh limit-order and withdrawal, mixed EN/ZH order requests. Live run: 27/27 blocked, 0 leaked.
- Third real bug found by a failing test and fixed: scanning raw JSON for Chinese execution phrases silently fails under `ensure_ascii=True` escaping; the runner now scans decoded output. Documented in RED_TEAM_CASES.md as a rule for all future gates.
- Backend suite: 323 passed.

Still external (unchanged): DeepSeek key rotation, human labeling of the first real batch, real Binance read-only key verification.

### 2026-07-06 (second pass) — User-Imported Credentials And Product Usability

Completed:

- DeepSeek/OpenAI API keys are now user-imported through the product, not developer-edited env files. New local secret store (`backend/.user_secrets.env`, gitignored, mode 0600, loaded at startup) holds user credentials; everything downstream sees only `env://` references. Raw values never enter the database, audit logs, or API responses (test-asserted).
- New self-service endpoints: `POST /production/human-control/llm/credentials` (provider/model/key/budgets/approval), `POST /production/human-control/llm/test-call` (one real review-only call to verify the key inside the product), and generic `GET/POST/DELETE /production/local-secrets` for future read-only exchange keys.
- Settings workspace gained an "AI 模型与密钥（自定义导入）" card: provider/model/key/budget form, explicit approval checkbox (unapproved keys stay unused; Mock remains active), one-click real test call, stored-reference list with delete.
- The developer-era `DEEPSEEK_API_KEY` was removed from `backend/.env`; the same key imported through the product flow verified end-to-end: stored → server restart → loaded from user store → real DeepSeek call returned structured review-only output, confirmed both via API and through the UI button.
- Fixed in passing: provider TLS requests now pin the `certifi` CA bundle (previously failed with certificate errors on machines with incomplete Python trust stores — certifi was a declared dependency but unused by providers).
- Backend suite: 330 passed. Frontend typecheck: passed.

Still external: rotate the DeepSeek key (unchanged; it appeared in a plaintext session — now trivial to re-import via the UI after rotation), human-label the first eval batch, real Binance read-only key (import path now exists via local-secrets).

### 2026-07-07 — Founder Daily-Use Closure: E2E Journey Green On Fresh Database

Completed:

- Data Sources credentials_ref input now offers imported local-secret references (env://USER_*) via a datalist instead of free-typing.
- Human labeling UI shipped in the Research workspace: lists unlabeled eval runs with output preview, one-click hallucination yes/no, and live human_labeled_runs / hallucination_rate from the backend (labels-only).
- Daily open/close runs are now persisted as individual records with a `GET /daily-use/daily-history` endpoint (previously only the latest packet survived). Found and fixed a latent crash: `overview()` embedded a raw ORM object, so daily-open failed for any user with an existing export artifact.
- Found and fixed a significant config bug: `Settings` loaded `.env` relative to the launcher's cwd, so a server started from another directory silently fell back to the default Postgres URL. The preview server had been running against local Postgres the whole time while env edits went unread. `.env` is now anchored to the backend directory; the interactive DATABASE_URL is set explicitly.
- The demo-journey E2E smoke now passes end to end on a completely fresh database (9.3s): first-run onboarding wizard → approval → paper execution → post-trade review → generate monthly review. Two product gaps were fixed to get there: the test now completes the first-run wizard like a real user, and the redesigned Review workspace's monthly tab was rewired from static mock content to the real `/reviews/monthly` endpoints (fetch + generate), with `module=monthly_review` deep links landing on the tab.
- Backend suite: 331 passed. Frontend typecheck: passed.

### 2026-07-07 (second pass) — Every Button Real: Local-Runnable Product Frame

Goal: everything that waits on the user becomes user-input in the product, and every visible control performs its stated function.

Completed:

- Restored routes for panels orphaned by the UI redesign: `module=data_sources` renders the full DataSourcesPanel (CSV import, read-only sources, health checks, credential references), `module=complete_product` and `module=fundraising_readiness` render their real panels. The simple Settings workspace links into them.
- SettingsWorkspace rewired from static mock to real state: data mode / first-run status from `/daily-use/local-start`, registered-vs-enabled connection counts from the live registry, AI call boundary from `/ai/provider-status`; quick-start buttons navigate into the real flows; safety switches converted from fake toggles to honest "locked default" indicators; advanced items are working navigation buttons.
- ReviewWorkspace fully rewired: pending tab lists real `/post-trade-reviews` with backend-generated review questions and a completion drawer that writes real records (verified in-browser: completing a review moved counts 3→2 pending, 3→4 done); trades tab lists real journal entries; patterns tab computes progress from real completed reviews and renders behavior patterns / rule proposals from the latest monthly review; static AI-audit tab with fabricated conclusions removed.
- Next-action rail now keeps category diversity (max 2 per kind in the visible 4), so a just-approved execution or fresh review surfaces even with a long approval backlog — this fixed a real UX failure where 48 pending approvals drowned everything else.
- Demo-journey smoke updated to click the matching action rather than blindly the first, and now passes against both a fresh database and the busy real database (21.6s).
- Backend suite: 331 passed. Frontend typecheck: passed.

Known remaining static content (documented, next batch): parts of Plan/Risk/Research workspace narrative cards, and the Copilot rail bullets on some pages.

### 2026-07-07 (third pass) — Phase 5 / 9 / 26 Advanced

- **Phase 5 (Strategy Playbook → gates)**: active StrategyRules on the order's thesis playbook are now enforced inside the risk gate — supported rule types: max_position_weight, max_order_notional, forbidden_symbols, allowed_sides, min_thesis_confidence; per-rule block/warn action from actions_json; unsupported types warn; every rule evaluation is recorded as gate evidence. Verified with block / warn / pass tests. A rule the user writes after a review now actually gates the next trade.
- **Phase 9 (Risk engine)**: audit found the real time-series engine (realized vol, historical correlation/VaR/drawdown from stored candles, with methodology + limitations) already exists end-to-end at `/portfolio-risk/time-series/*` — the remaining proxy was only in the product-completion risk packet. That packet now automatically upgrades to the real time-series results when an analysis exists (methodology `time_series_realized_from_stored_candles`) and falls back to the labeled deterministic proxy only when none has been run. Both paths tested.
- **Phase 26 (real on-chain reads)**: new `EvmRpcReadOnlyAdapter` — eth_getBalance and ERC-20 balanceOf via https JSON-RPC with certifi TLS; strict address validation; no signing/transaction method exists (test-asserted, same guarantee style as the Web3 service). `POST /web3/wallets/{id}/rpc-refresh` persists real balances (`source=evm_rpc_readonly`, USD value honestly 0 until a price source is attached) with audit. Live verification: mainnet chain_id=1, read a well-known public address's ETH and USDC balances through the default public node.
- Backend suite: 340 passed (331 + 9 new).

Assessment updates: Phase 5 → ~85%, Phase 9 → ~85% (real engine existed; packet unification done), Phase 26 → ~55% (real single-chain reads live; multi-chain, allowance reads via RPC, and price attachment remain).

### 2026-07-07 (fourth pass) — Phase 15 / 27 / 28 Advanced

- **Phase 15 (paper corporate actions)**: assessment corrected — cash dividends AND stock splits (with tax-lot quantity/cost adjustment, journal entries, audit, endpoints, tests) were already fully implemented. No code was needed; the tracking table was stale.
- **Phase 27 (backtest lab)**: strategy DSL and walk-forward analysis also already existed. The genuine gap was slippage: the simulation now supports `slippage_bps` — buys fill at close×(1+slip), sells at close×(1−slip), per-trade `fill_price` and `slippage_cost` recorded, realized PnL and final capital reflect friction. Test proves a 50bps-slippage run ends with strictly less capital than a frictionless run of the same strategy.
- **Phase 28 (signal quality)**: new `GET /signals/quality-report` evaluates stored signals against realized forward returns from local candles — hit rate and average forward return overall and per signal type, per-signal outcomes, signals without enough forward history skipped and counted (never imputed), methodology stated, audited, review-only. Tests cover hit/miss math and the fail-closed skip path.
- Backend suite: 343 passed (340 + 3 net new).

Assessment updates: Phase 15 → ~90% (was already there), Phase 27 → ~70% (slippage added; multi-asset simulation remains), Phase 28 → ~70% (quality measurement live; benchmark comparison remains).

### 2026-07-07 (fifth pass) — Phase 26 Extension + Phase 23 Gate Enforcement

- **Phase 26 (on-chain reads, extended)**: `EvmRpcReadOnlyAdapter.get_erc20_allowance` reads real ERC-20 approvals via `eth_call` (allowance selector); values within 2× of max uint256 are treated as unlimited. `rpc-refresh` now accepts an `allowances` list, persists `TokenAllowance` rows (`source=evm_rpc_readonly`, high risk when unlimited), and creates an `UNLIMITED_TOKEN_ALLOWANCE` alert — observation only; the alert text tells the user to review/revoke from their own wallet, the system never signs anything.
- **Phase 23 (data catalog → gates)**: the research gate now enforces the catalog's own verdict on the cited snapshot — a cataloged snapshot whose entry is `BLOCKED`/`FAILED` or `usable_for_trading=false` cannot pass, closing the loop on "data quality uncertainty fails closed". Existing passing paths (usable or uncataloged snapshots with quality reports) are unchanged; test proves the blocked path.
- Backend suite: 345 passed.

Assessment updates: Phase 26 → ~65% (balances + allowances + alerts over real RPC; multi-chain and price attachment remain), Phase 23 → ~80% (trust verdict now enforced at the gate).

### 2026-07-08 — Tier 0 Sprint Verification

Backend + typecheck:
- Backend suite: 345 passed. Frontend typecheck: clean.

E2E (fresh sqlite DB, live servers):
- demo-journey smoke: 1/1 passed.
- core-workspace: 4/4 passed. Fixed 2 assertions made stale by the complete_product route split (panel now renders on its own route with content expanded, so the intermediate "产品与外部验证" tab click was removed).
- local-self-use (20 fail) and quality-regression (3 fail): these are PRE-REDESIGN legacy suites. They reference retired panel regions (本地启动中心, 首次启动步骤, 季度复盘趋势, 策略验证向导, 账本修复抽屉, etc. — still present only in the unrouted app/components/panels/* old panels) plus stored screenshot baselines. They are structurally out of sync with the current workspace UI and need a standalone rewrite; they are NOT regressions from this sprint's work. (Also note: local-self-use defaults to port 3001; run with APP_BASE_URL=http://127.0.0.1:3000.)

Fresh-DB product acceptance walkthrough (real endpoints, browser-verified):
- Seed established 3 drafts / 8 theses / 2 reviews / 15 assets / 5 constitutions.
- Decision gates: all five PASS on happy path; strategy-rule enforcement + data-catalog-trust enforcement confirmed by 4 passing gate tests.
- Phase 26 real on-chain read: vitalik.eth returned 6.669 ETH / 36.77 USDC live via evm_rpc_readonly.
- Phase 28 signal quality endpoint live, fail-closed on no forward data, execution_available=false.
- Review workspace monthly tab renders real monthly-decision attribution (period, trade counts, thesis alignment, gate blocks) from the live endpoint.

Follow-up flagged: rewrite local-self-use + quality-regression E2E suites against the redesigned workspace UI (separate task; not a sprint regression).

### 2026-07-08 (second pass) — Phase 28 signal baseline + Phase 4 audit correction

- **Phase 28 (signal baseline comparison)**: `GET /signals/quality-report` now includes a `baseline` block answering "do signals carry information?" — baseline = expected hit rate for the same direction mix with zero skill (each bullish scores the sample's up-move rate, each bearish the down-move rate). Reports `baseline_hit_rate`, `edge_vs_baseline`, `has_positive_edge`, and up/down move rates, with an explicit note that this is not a significance test and small samples are noisy. Two tests: a mixed-direction/mixed-move sample shows +0.5 edge; a uniform up-market shows 0 edge (the case the baseline exists to expose). Backend suite: 347 passed.
- **Phase 4 audit correction**: research_feeds was assessed as "mostly modeled, not real source-backed" — that was wrong. `sync_sec_filings_and_fundamentals` is a real SEC EDGAR implementation (company_tickers → CIK → submissions → companyfacts, official API, no key); FRED macro (public CSV) and blockchain.com on-chain metrics are also real public sources; all fetch through certifi-pinned TLS (open_readonly_url). Live-verified: SEC returned 10,418 tickers, AAPL CIK 320193. So Phase 4 data-source ingestion is materially further along than the tracking table showed (real news/filings/macro/on-chain sources exist; the remaining gap is wiring these feeds into a thesis-delta comparison view, not building the sources).

Note: this pass was backend-only by design — a parallel session is rewriting the legacy E2E suites (task_18273b61) and touching frontend, so frontend was left untouched to avoid conflict.

### 2026-07-08 (third pass) — Phase 27 buy-and-hold benchmark

- **Phase 27 (backtest benchmark)**: backtest results now include a `benchmark` block — a buy-and-hold comparison that deploys full initial capital at the first usable close (with the same entry fee/slippage as the strategy) and holds to the end. Reports the benchmark's final capital and return, `strategy_excess_return_pct`, and a `strategy_beats_benchmark` flag, with a note that it is not risk-adjusted. This answers the single most honest sanity check on any timing strategy: did it beat simply holding? Two tests: a steady uptrend where buy-and-hold doubles (100% return) and excess/flag consistency is verified; a friction case confirming entry fee + slippage drag pulls benchmark return just under the frictionless 10%. Backend suite: 349 passed.

Remaining Phase 27 gap: multi-asset portfolio backtest (current engine is single-asset MA-cross). Benchmark comparison and slippage/fee are now done.

Note: backend-only pass again — parallel session still owns the frontend (legacy E2E rewrite, task_18273b61).

### 2026-07-08 (fourth pass) — Phase 23 data promotion lifecycle

- **Phase 23 (raw → reviewed → trusted promotion)**: data catalog entries now have an explicit, evidence-driven promotion lifecycle. `POST /data-catalog/entries/{id}/promote` advances an entry: reviewed requires quality_status VALID; trusted additionally requires no open critical/error reconciliation breaks. `usable_for_trading` is bound to the trusted stage only. Promotion advances at most one stage per call (never raw→trusted in a single jump), is idempotent, fail-closed (missing evidence holds the lower stage), records a promotion_history in lineage_json, and is fully audited. `GET /data-catalog/entries/{id}/promotion` is a read-only status view reporting current_stage, eligible_stage, can_advance, and trusted_blockers. Four service-level tests: low quality stays raw; VALID promotes one stage per call to trusted with correct history; an open critical reconciliation break caps promotion at reviewed; status read is non-mutating. Backend suite: 353 passed.

This closes the upstream half of "data quality uncertainty fails closed": the research gate already blocks non-usable snapshots (2026-07-07), and now usable_for_trading is only ever set by evidence-driven promotion rather than a manual flag.

Note: backend-only pass — frontend still owned by the parallel legacy-E2E-rewrite session (task_18273b61).

### 2026-07-12 — Wire new backend capabilities into the UI (post E2E-rewrite session)

The parallel legacy-E2E-rewrite session (task_18273b61) finished 3+ days ago, so the frontend was safe to touch. Wired three recently-added backend capabilities into the real UI:

- **backendService.ts (append-only)**: added `fetchSignalQualityReport` + `SignalQualityReport` type (incl. baseline block), `fetchCatalogPromotion` / `promoteCatalogEntry` + `DataCatalogPromotion` type, and a `backtestBenchmark(run)` helper + `BacktestBenchmark` type that safely reads the buy-and-hold block from an untyped `results_json`. No existing code edited.
- **SignalsPanel**: new "信号质量与基线 / Signal quality vs baseline" card — hit rate, avg forward return, baseline hit rate, edge-vs-baseline (positive-edge flag), up/down move rates, and per-signal-type breakdown; fail-closed empty state when there is no forward history; explicit review-only framing noting signals never bypass the decision gates.
- **StrategiesPanel** (was an orphan panel with no route — backtest was unreachable): added `?module=strategy` route in page.tsx, and surfaced the buy-and-hold benchmark in the backtest evidence summary (beats/below-hold pill, excess return, benchmark return).

Verification:
- Frontend typecheck: clean.
- StrategiesPanel route renders live (fresh browser tab shows 回测/规则 content; server HTML 92KB).
- Benchmark proven end-to-end against real Postgres: seeded a rising 10→20 series, ran a real MA-cross backtest → strategy +21.67% vs buy-and-hold +99.70%, `strategy_beats_benchmark=false`, excess −78.03% (exactly the over-trading-underperforms-hold case the benchmark exists to expose). Throwaway asset/candles/run cleaned up; user's real data untouched.

Note: signal quality card and backtest benchmark both show correctly but this Postgres DB lacks forward candle history for most assets, so live values often read "insufficient data" (correct fail-closed behavior) — the logic itself is proven by backend tests + the seeded benchmark run above.

### 2026-07-12 (second pass) — Data promotion lifecycle wired into the catalog UI

Third and final of this batch's backend capabilities now surfaced in the real UI:

- **DataSourcesPanel catalog detail drawer**: new "数据晋升生命周期 / Data promotion lifecycle" section shows current stage (raw/reviewed/trusted) with a colored badge, eligible stage, usable-for-trading flag, trusted-stage blockers, promotion history, and a promote button. Uses `fetchCatalogPromotion` on inspect and `promoteCatalogEntry` on click (single-step, evidence-driven). Append-only wiring; existing version/replay section untouched.
- Live-verified against real Postgres: opened a real BLOCKED broker_statement entry — the section correctly showed stage=raw, quality=BLOCKED, eligible=raw, usable=否, blocker=quality_not_valid, and the promote button read "证据不足，无法晋升" and was **disabled**. This is exactly the fail-closed behavior the lifecycle exists to enforce: a non-VALID entry cannot be promoted.
- Frontend typecheck: clean.

All three of this batch's backend capabilities (signal baseline, backtest benchmark, data promotion) are now reachable in the UI. Also restored the orphaned StrategiesPanel to a `?module=strategy` route so backtest is accessible at all.

Note (browser tooling): the in-app Browser pane's hydration got stuck on tabs where navigate + hard window.location.href were interleaved (blank body despite valid 30KB+ server HTML). Opening a fresh tab renders correctly every time — a tooling/session quirk, not an app bug.

### 2026-07-13 — Phase 27: multi-asset portfolio backtest

Extended the review-only backtest engine from single-asset to multi-asset portfolios (append-only; single-asset path untouched and all 8 prior backtest tests still green).

- **Trigger**: `parameters_json.assets` = list of `{asset_id, weight}` (≥2 legs). Absent/malformed → falls through to the proven single-asset path.
- **Engine** (`_simulate_portfolio` + module-level `simulate_ma_cross_leg`): each leg runs the same MA-cross on its own capital sleeve (initial_capital × normalized weight), with the shared fee_bps/slippage_bps. Legs are combined into one portfolio equity curve on the union of timestamps (each leg forward-filled). Reports per-leg contribution (final, return %, buy-and-hold %, trade count) and portfolio metrics (total return, max drawdown, trade count, leg count).
- **Benchmark**: `buy_and_hold_portfolio` — weighted buy-and-hold of the same legs with identical entry fee/slippage; exposes excess return and `strategy_beats_benchmark`. Static-weight sleeves; periodic rebalancing noted as a future extension.
- **Preflight** (`_portfolio_preflight_blockers`): blocks on inactive playbook, invalid MA windows, duplicate asset, non-positive weight, zero weight-sum, and insufficient candles per leg — fail-closed, no partial runs.
- **Safety invariants hold in portfolio mode**: `execution_available=False`, `real_orders_created=0`, `paper_orders_created=0`; `promotion_preflight` works unchanged (review-only, order creation disallowed).

Verified end-to-end on a throwaway sqlite DB (real Postgres untouched): a rising+falling two-asset book — the rising leg's MA-cross captured +113.96% on its sleeve, the falling leg correctly stayed in cash (0%, avoiding the −66.7% hold loss); portfolio +68.38% vs weighted buy-and-hold +93.04%, `strategy_beats_benchmark=False`, excess −24.66% (honest: timing lagged static hold on the winner). Leg finals summed exactly to the portfolio final. Added 2 API-level regression tests (`test_backtest_portfolio_run_combines_legs_without_orders`, `test_backtest_portfolio_run_blocks_on_bad_weight`). Full backend suite: 355 passed.

### 2026-07-13 (second pass) — Phase 23: snapshot diff / drift comparison

Built the missing counterpart to snapshot versioning + replay: an actual **diff between two versioned snapshots**, so a re-import or a replay copy can be checked against its origin for drift/tampering.

- **Backend** `DataCatalogService.compare_entry_snapshots(entry_id, other_entry_id)`: compares stable content hashes for a fast identical/changed verdict, then computes a **row-level diff** (multiset by row content hash → added/removed/unchanged counts + bounded samples, order-insensitive and duplicate-aware) for row-shaped payloads, or a **field-level diff** (added/removed/changed top-level keys with before/after values) for keyed payloads. dataset_type/snapshot_type mismatches surface as warnings. Review-only: writes only a `data_catalog.snapshots_compared` audit record; `execution_available=false`.
- **API**: `GET /data-catalog/entries/{entry_id}/compare/{other_entry_id}`.
- **Client + UI**: `compareDataCatalogEntrySnapshots` in backendService; new "版本对比与漂移检查 / Snapshot diff" section in the DataSourcesPanel catalog detail drawer — pick another entry (incl. replay copies) from a dropdown, see verdict pill, base/compared hashes, row-count delta, and added/removed/unchanged (or field add/remove/change) counts.
- Honest nuance verified live: two broker_statement entries showed verdict **changed** (top-level hash differs) with **0 row changes** (2→2 unchanged) — correctly signalling metadata/timestamp drift over an unchanged row payload. Self-compare returns **identical** (hash fast-path).

Verification: 5 new service tests (`test_data_snapshot_compare.py`) covering identical, changed-rows, field-diff, type-mismatch warning, and missing-entry 404; full backend suite **360 passed**; frontend typecheck clean; real-Postgres API check + browser screenshot of the rendered diff.

### 2026-07-13 (third pass) — Phase 26: multi-chain read-only RPC

The on-chain read path was mainnet-only: a Base/Arbitrum wallet was silently read against the Ethereum node. Fixed with a chain registry + fail-closed verification.

- **Adapter** (`evm_rpc_readonly.py`): `CHAIN_REGISTRY` maps chain_id → {name, public https node, native symbol} for Ethereum(1), Base(8453), Arbitrum(42161), Optimism(10), Polygon(137), with a name/alias resolver (`resolve_chain`). New `EvmRpcReadOnlyAdapter.for_chain(chain)` builds an adapter on the chain's default read-only node; `verify_chain()` reads on-chain `eth_chainId` and **fail-closed raises** if the node's network doesn't match the expected chain (no-op when no chain is expected, e.g. a raw rpc_url override). Still zero signing/write capability.
- **Service** (`web3_risk.rpc_refresh_wallet`): resolves the node from `wallet.chain` via the registry (unless an adapter/rpc_url is supplied), verifies the chain before any read, and takes the native symbol from the registry. Unknown chains fail closed as a Web3ReadOnlySafetyError rather than reading the wrong network.
- **API**: `GET /web3/supported-chains` lists the read-only chains and their default nodes for the wallet UI.
- **Live-verified against real public nodes**: the same public address (vitalik.eth) returned distinct real balances per chain — Ethereum 6.66 ETH (chain_id 1), Base 3.13 ETH (8453), Arbitrum 0.158 ETH (42161) — each confirmed against the correct chain_id. Wrong-network guard proven: a Base-expecting adapter pointed at the mainnet node was rejected with "chain_id 1 does not match expected 8453".
- Tests: 3 new (chain resolution incl. unknown-chain rejection, fail-closed wrong-network verify, unsupported-chain rpc-refresh → 422). Full backend suite **363 passed**.

Phase 26 → ~85% (multi-chain live; only USD price attachment to on-chain balances remains — currently honestly 0).

### 2026-07-13 (fourth pass) — Phase 26: USD price attachment for on-chain balances

The last Phase 26 gap: on-chain balances were read for real but valued at USD 0. Now valued from a public read-only price source, fail-closed.

- **Service** (`web3_risk.rpc_refresh_wallet`): new injectable `price_provider` param. When supplied, each native/ERC-20 balance gets `usd_price`/`usd_value` from it; symbols it can't price keep 0 (never invented). Audit log records `balances_priced` and `price_source`. Injectability keeps unit tests fully offline.
- **Default provider** (`default_onchain_price_provider`): USD spot via the existing public Yahoo Finance read-only quote adapter (`{SYMBOL}-USD`, no credentials); stablecoins (USDC/USDT/DAI/…) pinned to 1.0; any failure returns None → valuation 0. No signing, no writes.
- **API**: `rpc-refresh` accepts `attach_prices` (default true) and wires the default provider; explicit opt-out passes None.
- **Live-verified end-to-end**: same public address across chains — Ethereum 6.66 ETH → ~$11,766, Base 3.13 ETH → ~$5,524, Arbitrum 0.158 ETH → ~$280, using a real ~$1766 ETH price from the public source; USDC pinned to 1.0. Fail-closed proven: an unpriceable token keeps usd_value 0.
- Tests: 2 new (offline fake-provider valuation with fail-closed unpriced token; stablecoin pin). Full backend suite **365 passed**.

Phase 26 → ~95% (multi-chain reads + USD valuation both live and real). Plan items #1 and #2 are now complete.

### 2026-07-13 (fifth pass) — Phase 27: portfolio periodic rebalancing

Completes the backtest lab: the multi-asset portfolio can now rebalance to target weights on a fixed cadence, not just hold static independent sleeves.

- **Engine** (`simulate_portfolio_rebalanced`): a lock-step multi-asset MA-cross on a shared union timeline. Each leg computes its MA signal from its full close history (no per-period warmup loss). Every `rebalance_every` timeline steps, all legs are **liquidated to cash at the current close (paying real fee/slippage), the combined cash is redistributed to target weights**, and trading resumes on each leg's signal. Reports per-leg trade counts, rebalance-event count, and timeline steps.
- **Result** (`_build_rebalanced_portfolio_result`): standard portfolio result shape plus a `rebalance` block (enabled, cadence, events, note) and `metrics.rebalance_events`. Benchmark stays weighted buy-and-hold (no rebalancing) with identical entry fee/slippage, so excess return isolates what rebalancing added or cost.
- **Trigger**: `parameters_json.rebalance_every` (candles). 0/absent → the proven static-sleeve path is untouched. Negative → fails closed as a `blocked` run (`invalid_rebalance_every`) via portfolio preflight, never a crash.
- Safety invariants hold: `execution_available=false`, `real_orders_created=0`; `promotion_preflight` unchanged.
- Verified on a real Postgres two-asset book (one up-then-down, one down-then-up): static +59.67% (3 trades) vs rebalance-every-5 +43.95% (7 trades, 3 rebalance events over a 20-step timeline) — the extra trades are the boundary liquidations, and rebalancing beat weighted buy-and-hold by +34.1% excess. Equity curve ends exactly at the reported final capital.
- Tests: 2 new (rebalanced run reports consistent events + equity, negative rebalance fails closed). Full backend suite **367 passed**.

Phase 27 → ~95% (slippage/fees, buy-and-hold benchmark, multi-asset portfolio, and periodic rebalancing all live). Portfolio/rebalance is API-configured via parameters_json; the single-asset backtest keeps its UI form. Plan item #3 complete.

### 2026-07-14 — Phase 4/7: thesis-delta comparison view

The real data sources (SEC EDGAR, Nasdaq news, FRED macro, catalyst calendar, on-chain) existed but were never compared against a thesis. Now they are.

- **Backend** `ResearchFeedService.thesis_delta(thesis_id)`: baseline = newest ThesisCheckpoint, else thesis creation. Compares the baseline against **locally stored evidence only** (no network calls — reproducible): price move from local 1d candles vs the thesis's `max_loss_tolerance_pct` (breach → `max_loss_tolerance_pressure` flag), new SEC filings after the baseline date, symbol-relevant news, per-series macro deltas (baseline obs vs latest), upcoming catalysts, and on-chain metric deltas for crypto assets. Fail-closed feed states: never-synced → `missing`, synced before baseline → `stale_since_baseline` with a re-sync next-action; no candles → `no_local_candles`. Review-only and audited; the human records the checkpoint verdict — `checkpoint_required_for_conclusion: true`.
- **API**: `GET /research-feeds/thesis-delta/{thesis_id}` (404 for unknown thesis).
- **UI**: new `ThesisDeltaCard` on the Research workspace Thesis tab — pick one of your real stored theses (symbol resolved from assets), generate the report: baseline line + flag badges, price block (baseline→latest close, change %, tolerance breach), per-feed cards (fresh/stale/missing badges, new facts, macro deltas), and a "next steps (your call)" list. First **real-data** block on a workspace whose thesis list was previously static (advances plan item #6 too).
- Verified: 3 new API tests (price-pressure + new-facts flags; fail-closed without evidence incl. 404; pre-baseline snapshots marked stale) — full backend suite **370 passed**; frontend typecheck clean; live browser run against real Postgres (50 real theses in the dropdown; report correctly showed baseline 2026-06-29, `缺少本地K线` for a candle-less test asset, news/SEC fresh, macro/catalysts stale-with-re-sync-advice) with screenshot.
- Note: hit the documented Browser-pane hydration quirk again (effects not running on a reused tab after interleaved navigations); a fresh tab rendered and behaved correctly — tooling quirk, not an app bug.

Plan item #4 complete. Phase 4 ingestion→comparison loop is now closed; Phase 7 thesis monitoring gains its evidence-delta input.

### 2026-07-14 (second pass) — Plan workspace on real order drafts

The 交易计划 page (order_drafts route, a core product page) was 100% static — hardcoded fake plans, fake checks, fake approvals. Rewritten on real data.

- **PlanWorkspace** now loads real order drafts (`fetchOrderDrafts` + per-draft `fetchOrderDraftDecisionDetail`) and derives everything from backend state: status buckets (待补充/待检查/待审批/已通过/已拒绝/已复盘) from approvals + post-trade reviews + thesis link + risk checks; risk level from draft risk/behavior status; direction from the real intent (side/qty/order type/limit price); linked-thesis state and max-loss tolerance from the real thesis.
- **Drawer** shows real evaluations: 7-item check list (thesis link, thesis active, hard risk rules with reason, behavior status, five decision gates, manual approval, real-orders-disabled boundary), gate blocking reasons when present, real approval record with date+reason, and paper-execution / review / journal counts. Invented narrative fields (whyNow/ifNot/AI dissent) were removed rather than faked; footer buttons are honest navigation only.
- Client `InvestmentThesis` type gained `max_loss_tolerance_pct` (backend returned it; the type didn't declare it).
- Live-verified in the browser against real Postgres: 30 real drafts (25 待审批 / 1 已通过 / 4 已复盘), real direction strings ("BUY 1 limit @ 225.12"), and an honestly mixed drawer — a thesis-less draft shows 需要补充 on the thesis checks while hard risk rules show 通过 ("all hard rules passed") and a real 已批准 2026/7/7 approval record. Screenshot taken. Frontend typecheck clean.
- Hit the Browser-pane hydration quirk again on the reused tab (effects not running); fresh tab worked — tooling, not app.

Plan item #6 substantially advanced: Settings/Review/Plan workspaces now real; Research got its first real block (thesis-delta). Remaining static: RiskWorkspace arrays, ResearchWorkspace thesis list/REPORTS cards.

### 2026-07-15 — Risk workspace on real data

The 风险复盘 page was 100% static (fake priorities, fake holdings, fake stress numbers). Rewritten so every row derives from real backend state:

- **Metric cards**: risk level from the real annualized volatility (40.0%, 171 observations → 高); drawdown budget bar from the real engine (budget_used 255%, current drawdown −37.2% vs 15% budget); needs-attention = derived priority count; blocking items = thesis-less holdings + blocked plans (honest 433 on the sim book).
- **Overview**: priority list computed live — missing-thesis risk (blocking, with affected symbols), concentration breaches vs the 10% cap, Web3 approval risk (high allowances + open alerts), drawdown-budget risk (>80% used). Empty state when nothing qualifies.
- **Holdings**: real positions (weight from market value / total) × real theses; top 30 by weight with a count note. **Plans**: real order drafts' risk/behavior/approval statuses. **Web3**: real wallet allowances (risk_level) + unresolved alerts, with the no-signing disclaimer kept. **Data quality**: real freshness overview per dataset (source, latest as-of, quality). **Stress tests**: the real time-series engine's scenarios — broad_risk_off −27.3% ($17,634), crypto_shock −29.2% ($18,840), historical_worst_5d −17.3% ($11,158) — all correctly flagged 超预算 vs the 15% budget (fixed a sign bug: engine reports losses negative; comparison now uses absolute values). Empty state offers a real "run analysis" action (`sync-and-run`).
- Client types patched to match the backend (`WalletAllowance` gained id/symbol/risk_level/source; alerts use `resolved`).
- Verified live in the browser against real Postgres across all six tabs with screenshot; frontend typecheck clean. Hydration quirk again required a fresh tab (documented tooling issue).

With Settings, Review, Plan, and Risk now real and Research carrying its first real block, plan item #6's core is done. Remaining static: ResearchWorkspace's thesis list/REPORTS narrative cards (smallest slice), and plan item #5 (MCP read-only server) is the last codeable feature target.

### 2026-07-15 (second pass) — Research workspace thesis list on real data

The last big static block: the Research page's Thesis list (7 hardcoded rows) is now built from real backend state.

- **buildThesisRows**: newest real thesis per asset (up to 25 rows) with: real weight from portfolio market value; status derived from thesis.status + evidence (active & ≥60% → 有效, active & <60% → 证据不足, monitoring → 需复查); **evidence completeness computed from what's actually written** (entry reason, invalidation conditions, key drivers/narrative, horizon, max-loss tolerance, confidence — 6 checks → %); real invalidation conditions, key drivers, confidence, tolerance, horizon, and last-updated date in the card + drawer. Plus synthesized **缺失 rows for the largest holdings with no thesis at all** — the "no rationale, no plan" rule made visible.
- 研究待办 counters now real: 需要补 Thesis 5 / 已完成 20 on the live book.
- Client `InvestmentThesis` type gained `key_drivers_json` (returned by backend, undeclared).
- Verified in the browser against real Postgres: real theses (SELF26577 …) with real entry reasons, real invalidation text from JSON, 证据完整度 100% with real dates; missing rows show the top thesis-less holdings. Screenshot taken; typecheck clean.
- REPORTS/RULES/DISCIPLINES/AI_FINDINGS narrative cards remain static by design for now (educational copy, not data claims); noted as the only static remnants.

Plan item #6 complete. Remaining codeable feature target: plan item #5 — MCP read-only tool server (Phase 29).

### 2026-07-15 (third pass) — Phase 29: MCP read-only tool server

The last codeable feature target from the plan. External agents (Claude Desktop/Code, any MCP client) can now *observe* the terminal — and only observe.

- **Server** (`app/mcp_readonly/server.py`, FastMCP over stdio; `pip install -e '.[mcp]'`): 8 read-only tools over the existing service layer — `portfolio_snapshot`, `list_theses`, `thesis_delta`, `portfolio_risk_latest`, `signal_quality_report`, `data_trust_report`, `plan_pipeline_status`, `list_backtest_results`. Every result carries `execution_available:false` + `review_only:true`.
- **"Tools cannot bypass the main control system" enforced structurally**: nothing that crosses a decision gate (intents, drafts creation, approvals, executions, promotions, signing) is callable at all. Pinned by regression tests three ways: tool names free of execution vocabulary (token-level check — "signal" ≠ "sign"), server source free of execution/approval service imports and of any write-call patterns, and functional results carrying the review-only markers (incl. `portfolio_risk_latest` → honest `not_run` when no analysis exists).
- **Fix found during live verification**: `data_trust_report` embedded ORM rows → not JSON-serializable over MCP; now serialized through the same `DataTrustReportRead` schema the HTTP API uses.
- **Live-verified over the real MCP protocol** (stdio client spawning the real server against real Postgres): 8/8 tools — real total equity, real theses (SELF16822 active), risk VALID with 39.98% vol, plan pipeline pending states, data trust honestly `blocked` (fail-closed on stale data), thesis-delta with correct `no_local_candles` flag.
- Docs: `docs/MCP_READONLY_SERVER.md` (boundary, tool table, Claude Code/Desktop registration). Dependency recorded as the `mcp` pyproject extra. Full backend suite **374 passed**.
- Environment note: the venv's pip shebang pointed at the project's old path (Documents/交易系统), so `pip install` silently installed elsewhere; `python3 -m pip` installs correctly. Worth knowing for future installs.

Phase 29 → ~70% (read-only server live and verified; resources/prompts and an HTTP transport remain optional extensions). **All plan items (#1–#6) are now complete.**
