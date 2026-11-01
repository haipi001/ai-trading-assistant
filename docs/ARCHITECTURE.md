# Architecture — AI Trading OS v4

## Product Shape

AI Trading OS is an AI-native personal financial terminal.

The product is organized around terminal workspaces, not a single chatbot interface. AI is a contextual operator inside each workspace, but execution authority remains constrained by constitutions, playbooks, theses, gates, approvals, and audit logs.

V4 expands the architecture from a trading workflow system into a personal financial operating system. The center of gravity is still user self-logic: why the user bought, whether the thesis still holds, and whether the next action violates the user's own rules.

## Core Principle

Automate the user's investment process and self-discipline, not uncontrolled trading.

AI agents may research, summarize, explain, monitor, detect changes, and propose actions.
AI agents must never directly execute trades.

## Required Trade Flow

Every trade-related workflow must pass through:

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

Any uncertainty in data quality, broker state, risk state, or order state must fail closed.

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

## Layered Architecture

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

RiskEngine is mandatory, but it is not the highest-level product guard.
The highest-level guardrail is the user's self-logic stack:

1. InvestmentConstitution defines long-lived principles, constraints, capital rules, and automation boundaries.
2. StrategyPlaybook defines permitted strategy families, setup rules, sizing rules, and invalidation rules.
3. InvestmentThesis binds a specific asset, portfolio decision, or trade idea to facts, assumptions, triggers, and review criteria.

Only after this self-logic stack is satisfied may an idea proceed to gates, risk checks, order workflow, approval, execution, journal, and review.

## Boundary: AI Research

AI research owns:

- structured research reports
- market summaries
- thesis evidence summaries
- signal explanations
- bull and bear cases
- risk narratives
- limitations
- citations to data snapshots

AI research must not:

- call broker, exchange, wallet, or execution methods
- create facts outside structured input data
- store reports that fail AIReportEvaluator
- bypass ResearchGate or ThesisGate
- create executable orders

Outputs:

- ResearchReport
- AgentRun
- evaluated observations
- proposed user-facing actions

## Boundary: User Self-Logic

User self-logic owns:

- InvestmentConstitution
- StrategyPlaybook
- InvestmentThesis
- ThesisCaptureService
- ThesisMonitorService
- ThesisEvent
- ThesisViolation
- BehaviorPattern
- BehaviorIntervention
- BehaviorEngine
- PostTradeReview
- MonthlyDecisionReview
- playbook update proposals

Self-logic modules are responsible for checking whether the user's current action is consistent with prior commitments.

If a user action conflicts with a thesis, create ThesisViolation.
If a user action matches a harmful pattern, create BehaviorIntervention.

Thesis capture records the user's stated rationale as structured data; it must not create orders.
Thesis monitoring compares new structured facts against recorded drivers and invalidation conditions; if facts are insufficient, it returns DATA_INSUFFICIENT and fails closed.

BehaviorEngine detects harmful patterns before order workflow progression. It may create BehaviorPattern, BehaviorIntervention, ThesisViolation, and AuditLog records, but it must not create orders or execute trades.

Intervention levels:

- SILENT_RECORD
- SOFT_WARNING
- HARD_CONFIRM
- BLOCK

## Boundary: Decision Gates

Decision gates sit before order creation.

ResearchGate checks:

- research freshness
- data snapshot quality
- report evaluator status
- missing evidence
- unsupported claims

ThesisGate checks:

- thesis existence or explicit user rationale
- thesis status
- invalidation conditions
- thesis conflict
- thesis drift

BehaviorGate checks:

- overtrading
- revenge trading
- FOMO chasing
- loss-chasing
- size escalation
- repeated rule overrides

ExecutionGate checks:

- broker or exchange state
- account mode
- order state
- market state uncertainty
- execution availability

All gates must fail closed.

## Boundary: Risk Engine

Risk engine owns hard financial constraints:

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

Risk engine writes RiskCheck and AuditLog.

Risk engine does not execute trades.

## Boundary: Order Workflow

Order workflow owns:

- OrderIntent
- OrderDraft
- ApprovalPolicy
- Approval
- rejection
- modification
- state transitions

Order workflow must verify:

- required gates passed
- latest risk check passed
- approval policy exists
- order is not stale
- order is not already terminal

Order workflow does not place orders directly.

## Boundary: Automation Policy

AutomationPolicyEngine owns permission checks for what the system may automate for a given user, account, asset, and strategy.

Default policy is A0_READ_ONLY.

Policy levels:

- A0_READ_ONLY syncs data and creates portfolio views only.
- A1_RESEARCH allows research generation and thesis monitoring.
- A2_ALERT allows alerts and interventions.
- A3_ORDER_DRAFT allows OrderIntent and OrderDraft creation only after required gates pass.
- A4_APPROVAL_EXECUTION allows execution only after explicit human approval.
- A5_CONTROLLED_AUTO allows only whitelisted controlled actions within strict limits.
- A6_ADAPTIVE_AUTO_FUTURE is reserved and not implemented.

Controlled auto is limited to DCA, rebalance, stop-loss, take-profit, and stablecoin risk migration. It requires whitelisted assets, passed gates, RiskBudget compliance, and AuditLog records.

Automation policy does not execute trades.

## Boundary: AI Command Bar

The AI Command Bar is a deterministic typed-tool router, not a free-form chatbot.

Supported command intents include portfolio summary, position lookup, risk exposure, thesis review/capture, market news summary, signal lookup, behavior pattern review, monthly decision review, order draft lookup, and scenario analysis.

Command Bar responsibilities:

- detect intent from natural language
- route only to typed internal tools
- store `CommandQuery`, `CommandToolCall`, and `CommandResult`
- write `AuditLog` for command lifecycle and blocked actions
- cite `data_snapshot_id` when market or account data is used
- reject execution requests fail-closed
- allow passive `OrderIntent` creation only when `AutomationPolicy` is at least `A3_ORDER_DRAFT`

## Boundary: Data Catalog And Contract

Data catalog and data contract layers own source identity, ingestion metadata, quality status, snapshot IDs, lineage, and use permissions.

Every market/account/research data object that can influence trading workflow must carry:

- source
- source timestamp
- ingestion timestamp
- latency
- realtime or delayed flag
- confidence
- trading usability flag
- data quality status
- raw payload hash where applicable
- `data_snapshot_id`

If data quality is unknown, stale, incomplete, untrusted, or failed, downstream order workflow must fail closed.

## Boundary: MCP / Tools

MCP servers, command-bar tools, sidecars, and external adapters are downstream helpers only.

They must not bypass:

- InvestmentConstitution
- StrategyPlaybook
- InvestmentThesis
- DecisionGates
- RiskEngine
- BehaviorEngine
- AutomationPolicy
- ApprovalWorkflow
- AuditLog
- MonthlyDecisionReview

## Boundary: Observability And Audit

Observability and audit own traceability for decisions, blocked transitions, AI report rejection, gate results, policy decisions, approvals, executions, reviews, and operational health.

Every trade-related flow must create audit records. Fail-closed decisions are product behavior, not silent errors.

The command bar does not execute trades and does not call broker, exchange, wallet, or execution adapters.

## Boundary: Execution

Execution adapters are downstream-only.

Execution can only receive approved orders after:

- InvestmentConstitution
- StrategyPlaybook if strategy-driven
- InvestmentThesis or explicit user rationale
- ResearchGate
- ThesisGate
- RiskGate
- BehaviorGate
- ExecutionGate
- OrderDraft
- ApprovalPolicy

Live trading is disabled by default.
Paper trading must exist before live trading.
No LLM agent may call execution methods.

## Boundary: Review Loop

Review loop owns:

- TradeJournal
- PostTradeReview
- MonthlyDecisionReview
- behavior summaries
- thesis accuracy review
- strategy playbook update proposals
- constitution update proposals

Review loop may propose changes but must not silently change user rules without approval.

MonthlyDecisionReview is first-class.

## Terminal Workspaces

The product should be organized as workspaces:

- Portfolio workspace
- Market monitor workspace
- Research workspace
- Thesis workspace
- Strategy playbook workspace
- Signal workspace
- Order review workspace
- Risk and behavior workspace
- Journal workspace
- Monthly review workspace
- Settings and constitution workspace

Each workspace may expose an AI command bar, but command capabilities must be permissioned by workflow state and automation level.

## Open Source Integration Boundary

Open-source integrations must follow:

- `docs/OPEN_SOURCE_MAP.md`
- `docs/LICENSE_POLICY.md`
- `docs/SIDECAR_POLICY.md`
- `THIRD_PARTY_NOTICES.md`

Reference projects may inform architecture, workflow, UX, or modeling, but they do not replace the self-developed control plane.

No external project, sidecar, dependency, or advanced module may bypass RiskEngine, BehaviorGate, ApprovalWorkflow, AuditLog, or decision gates.

## Task Acceptance Standards

Every implementation task must include, when applicable:

- migrations if schema changes
- typed schemas
- services
- API endpoints
- tests, including blocked paths
- audit logs for important actions
- docs updates
- no live trading by default
- no execution bypass

Completion reports must include implementation summary, files changed, commands run, test results, safety review, intentionally omitted scope, and the next smallest useful task.
