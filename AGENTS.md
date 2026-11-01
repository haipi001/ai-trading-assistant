# AGENTS.md — AI Trading OS v4 Development Rules

## Mission

You are building an AI-native Personal Financial Terminal for multi-asset investors.

This product is not merely an AI trading assistant and not a black-box autonomous trading bot.
It automates the user's investment workflow, trading workflow, risk discipline, decision journaling, and self-logic review.

V4 keeps the existing safe v3 foundation and expands the product definition into a personal financial operating system for stocks, ETFs, crypto exchange assets, stablecoins, and on-chain wallet assets. Existing filenames, migration names, and internal schema aliases that contain `v3` are historical implementation labels; new planning and docs should use the v4 phase model.

The system supports:

- stocks
- ETFs
- crypto CEX assets
- Web3 on-chain assets
- portfolio data collection
- market and news monitoring
- research generation
- thesis tracking
- trading idea evaluation
- decision gates
- risk checks
- order draft creation
- human approval workflow
- controlled execution
- trade journaling
- post-trade review
- behavior pattern detection
- playbook and rule updates

The system must not automate uncontrolled speculation.

## Core Principle

Automate the user's investment process and self-discipline, not uncontrolled trading.

AI agents may research, explain, summarize, detect changes, generate reports, generate signals, detect behavioral patterns, and propose actions.

AI agents must never directly execute trades.

Every trade-related flow must pass through:

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

## Non-Negotiable Safety Rules

1. Live trading remains disabled by default.
2. No LLM agent may directly call broker, exchange, wallet, or execution methods.
3. Every order must be connected to either an InvestmentThesis or an explicit user rationale.
4. Every user account must have an InvestmentConstitution before controlled automation is enabled.
5. Every strategy must belong to a StrategyPlaybook before it can create OrderIntent.
6. Every order must pass ResearchGate, ThesisGate, RiskGate, BehaviorGate, and ExecutionGate.
7. If a user action conflicts with prior thesis, create a ThesisViolation record.
8. If a user action matches known harmful behavior patterns, create a BehaviorIntervention record.
9. Interventions must have levels: SILENT_RECORD, SOFT_WARNING, HARD_CONFIRM, BLOCK.
10. If data quality, broker state, risk state, or order state is uncertain, the system must fail closed.
11. Web3 modules must be read-only by default.
12. Never store seed phrases or raw private keys.
13. CEX trading keys must never include withdrawal permission.
14. AI reports must pass AIReportEvaluator before being stored or used downstream.
15. MonthlyDecisionReview is a first-class feature, not an optional analytics add-on.
16. The product must be organized around terminal workspaces, not a single chatbot interface.
17. All real broker, exchange, or wallet integrations must support mock mode and paper mode first.
18. No API keys, broker credentials, wallet private keys, seed phrases, or trading passwords may be committed.
19. All secrets must use environment variables or local secret storage.
20. If real broker integration is incomplete, create typed interfaces and mock adapters.
21. AI-generated reports must cite the data snapshot used.
22. AI-generated facts must come from structured input data.
23. If data is missing, the system must say data is unavailable.
24. Invalid AI JSON output must be rejected and logged.
25. Do not implement high-frequency trading.
26. Do not implement Kubernetes in early phases.
27. Do not implement multi-broker live execution in early phases.
28. Do not implement live automated trading unless a later task explicitly enables it.
29. Default automation policy must be `A0_READ_ONLY`.
30. AI, signal, command-bar, and strategy modules must not bypass RiskEngine, BehaviorGate, or ApprovalPolicy.

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

## Product Definition

Build an AI-native personal financial terminal for multi-asset investors.

It unifies stocks, crypto, and on-chain assets; tracks portfolio memory; captures investment thesis; automates research; applies decision gates; protects trades with risk and behavior checks; and continuously improves the user's self-logic through post-trade review.

It should help the user:

- collect portfolio and market data
- reduce AI hallucination through factual data snapshots
- track current holdings, position weights, and exposure
- generate daily market and portfolio summaries
- assist fundamental, technical, macro, news, and on-chain research
- maintain InvestmentConstitution and StrategyPlaybooks
- capture, monitor, and invalidate InvestmentThesis records
- evaluate trading ideas before they become order intents
- enforce ResearchGate, ThesisGate, RiskGate, BehaviorGate, and ExecutionGate
- detect behavior patterns such as revenge trading, overtrading, thesis drift, and FOMO entries
- generate order drafts only inside approved workflows
- require approval policy before any execution
- maintain trade journals, post-trade reviews, and monthly decision reviews
- update playbooks and self-logic from evidence

## Automation Levels

Implement automation levels:

### A0_READ_ONLY

- read data only
- no order intent

### A1_RESEARCH

- AI reports, watchlists, thesis monitoring, and decision support
- no order intent

### A3_ORDER_DRAFT

- AI or strategy may create OrderIntent and OrderDraft only after required gates
- no execution

### A4_APPROVAL_EXECUTION

- execution only after explicit human approval and all gates pass

### A5_CONTROLLED_AUTO

- predefined strategies may execute inside strict risk, behavior, thesis, and execution limits
- requires InvestmentConstitution and StrategyPlaybook
- not implemented in MVP

### A6_ADAPTIVE_AUTO_FUTURE

- future only
- do not implement

Default mode must be `A0_READ_ONLY`.

## Architecture Rules

Use modular layers in this order:

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

RiskEngine is not the top-level product guard.
InvestmentConstitution, StrategyPlaybook, and InvestmentThesis are upstream self-logic modules that constrain research, signals, gates, risk checks, behavior checks, order drafts, approvals, execution, and review.

Do not mix AI research logic with execution logic.
Do not mix self-logic review with broker execution.
Do not let sidecars, adapters, or external modules bypass gates.

## Required Architecture Boundaries

- AI research produces evaluated reports, observations, and proposed actions only.
- User self-logic modules own constitution, playbooks, theses, violations, interventions, reviews, and rule updates.
- Decision gates decide whether an idea can become an order intent.
- Risk engine decides whether an order intent can become an order draft.
- Order workflow owns drafts, approvals, rejection, modification, and audit records.
- Execution adapters are downstream of ApprovalPolicy and ExecutionGate only.
- Review loop owns trade journal, post-trade review, behavior feedback, and monthly decision review.

## Build Order

Do not start with broker integration.

Use this v4 phase order for new work:

| Phase | Implementation Target |
| --- | --- |
| Phase -1 | Product wedge docs |
| Phase 0 | Project scaffold and baseline health |
| Phase 1 | Core domain models |
| Phase 2 | CSV import and demo data |
| Phase 3 | Portfolio memory |
| Phase 4 | Investment constitution |
| Phase 5 | Strategy playbook |
| Phase 6 | Investment thesis |
| Phase 7 | Thesis capture and monitor |
| Phase 8 | Decision gates |
| Phase 9 | Risk engine |
| Phase 10 | Behavior engine |
| Phase 11 | Workflow state machine |
| Phase 12 | Automation policy |
| Phase 13 | Order intent and order draft |
| Phase 14 | Approval workflow |
| Phase 15 | Paper execution |
| Phase 16 | Trade journal |
| Phase 17 | Monthly decision review |
| Phase 18 | AI research reports and MockAIProvider |
| Phase 19 | AI evals |
| Phase 20 | AI command bar |
| Phase 21 | Terminal workspace UI |
| Phase 22 | Web3 read-only risk |
| Phase 23 | Data catalog |
| Phase 24 | yfinance adapter |
| Phase 25 | ccxt read-only adapter |
| Phase 26 | web3.py read-only adapter |
| Phase 27 | Backtest lab |
| Phase 28 | Signal lab |
| Phase 29 | MCP server |
| Phase 30 | Real API read-only adapters |
| Phase 31 | Approval-based live execution |
| Phase 32 | Controlled auto execution |
| Phase 33 | Advanced AI, Kronos, Qlib, and sidecars |

Start with Phase -1 and Phase 0 only unless the user explicitly instructs continuing into later phases. Later phases must be implemented as small safe slices with tests and docs.

## Acceptance Standards

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

## Backend Preferences

Use:

- Python
- FastAPI
- SQLAlchemy or SQLModel
- Pydantic
- Alembic
- PostgreSQL
- Redis
- pytest
- typed adapter interfaces

## Frontend Preferences

Use:

- Next.js
- TypeScript
- Tailwind or shadcn/ui
- terminal workspace layout
- AI command bar
- charting library where needed
- API client generated or typed from backend schemas if possible

## Core Domain Objects

Implement these domain objects over time:

- UserAccount
- TerminalWorkspace
- InvestmentConstitution
- StrategyPlaybook
- StrategyRule
- InvestmentThesis
- ThesisEvent
- ThesisViolation
- BehaviorPattern
- BehaviorIntervention
- MonthlyDecisionReview
- Asset
- Account
- BrokerConnection
- Position
- Quote
- Candle
- PortfolioSnapshot
- DataSnapshot
- DataQualityReport
- ResearchReport
- AIReportEvaluator
- AgentRun
- Signal
- ResearchGate
- ThesisGate
- RiskGate
- BehaviorGate
- ExecutionGate
- Strategy
- BacktestRun
- RiskCheck
- OrderIntent
- OrderDraft
- Approval
- Execution
- TradeJournalEntry
- PostTradeReview
- AuditLog

## Gate Requirements

Before any OrderIntent becomes an OrderDraft, check:

- InvestmentConstitution exists where required
- StrategyPlaybook exists where required
- InvestmentThesis exists or explicit user rationale exists
- ResearchGate passes
- ThesisGate passes
- RiskGate passes
- BehaviorGate passes
- ExecutionGate passes
- live trading flag
- account mode
- asset tradability
- manual_enabled
- auto_enabled
- asset whitelist
- strategy whitelist
- max order notional
- max position percentage
- max daily loss
- max leverage
- liquidity
- volatility
- kill switch
- data quality
- broker or exchange state
- order state

If any hard rule fails or is uncertain, fail closed, block the order path, and write AuditLog.

## AI Report Requirements

Every AI report must include:

- report_id
- report_type
- agent_name
- data_snapshot_id
- input_facts
- summary
- bullish_case
- bearish_case
- key_risks
- technical_view
- fundamental_view if applicable
- onchain_view if applicable
- suggested_action
- confidence
- evidence
- limitations
- evaluator_status

AI reports must pass AIReportEvaluator before being stored or used downstream.

## Open Source Usage Policy

Do not fork a large trading project as the main codebase.

The main control system must remain self-developed:

- InvestmentConstitution
- StrategyPlaybook
- InvestmentThesis
- DecisionGates
- RiskEngine
- BehaviorEngine
- AutomationPolicy
- OrderWorkflow
- ApprovalWorkflow
- AuditLog
- MonthlyDecisionReview

Use external projects in one of four modes only:

- reference only
- dependency
- sidecar
- small isolated reuse with attribution

Permissive-license code may be reused only when all of the following are true:

- the upstream license explicitly permits reuse
- the copied scope is small and clearly isolated
- copyright and license notices are preserved
- the source is recorded in `THIRD_PARTY_NOTICES.md`
- the reuse is documented in `docs/OPEN_SOURCE_MAP.md`
- the reused module does not become the main control path

AGPL, GPL, or unknown-license code must not be copied into the main codebase unless the project intentionally adopts compatible open-source obligations and the change is documented first.

Do not copy:

- large blocks of code from reference repositories
- UI designs wholesale
- logos, names, or brand assets
- broker credential handling
- exchange order-routing code
- wallet signing or private-key handling
- trading execution paths
- risk-control logic from external trading engines

Use these projects only as architecture references:

- QuantDinger: product-level AI quant OS structure
- TradingAgents: multi-agent research committee
- TradingAgents-CN: Chinese stock research workflow and UI inspiration
- World Monitor: macro/news intelligence dashboard
- LEAN: mature multi-asset trading engine design
- NautilusTrader: event-driven trading system design
- Ghostfolio: portfolio UX and allocation display ideas only
- rotki: crypto accounting, privacy-first modeling, and reporting ideas only
- OpenBB: data-platform and catalog design ideas only

Small isolated reuse may be considered, with attribution and documentation, from permissive projects such as:

- Vibe-Trading: MIT research workspace patterns, skill registry ideas, and MCP/tool routing structure

Allowed early direct dependencies:

- yfinance: prototype stock historical data
- ccxt: crypto CEX market data
- web3.py: EVM wallet read-only monitoring
- backtesting.py: lightweight strategy backtesting
- vectorbt: batch strategy experiments

Later sidecar candidates:

- Freqtrade: crypto bot sidecar
- Hummingbot: market making / arbitrage / DEX sidecar
- OpenBB: data platform sidecar
- rotki: crypto accounting sidecar

Later advanced AI modules:

- Kronos: K-line predictor, feature only
- Qlib: AI quant research workflow
- FinRL: research only, not live trading

Every external project must be reviewed against:

- `docs/LICENSE_POLICY.md`
- `docs/OPEN_SOURCE_MAP.md`
- `docs/SIDECAR_POLICY.md`
- `THIRD_PARTY_NOTICES.md`

No external project, dependency, sidecar, or advanced module may bypass core RiskEngine, BehaviorGate, ApprovalWorkflow, decision gates, or AuditLog.

## Done Means

A task is complete only when:

1. Code compiles, if code changed.
2. Tests pass, if code changed.
3. Types are valid, if typed code changed.
4. Database migrations are included if schema changed.
5. API endpoints are documented if API changed.
6. Mock data path works without real credentials.
7. README or related docs are updated.
8. No live trading is enabled by default.
9. Important actions write AuditLog.
10. New workflow logic respects InvestmentConstitution, StrategyPlaybook, thesis, gates, risk, behavior, approval, journal, and review boundaries.
11. The response includes changed files, test results, and next recommended task.

## Working Style

Before implementing:

- restate the task
- list assumptions
- list files to change
- identify risks

During implementation:

- keep scope small
- do not expand phase boundaries
- prefer simple typed interfaces
- add tests with each feature
- preserve fail-closed safety behavior

After implementation:

- run relevant tests
- summarize changes
- show how to run locally
- mention incomplete items
