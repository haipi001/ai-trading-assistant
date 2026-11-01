# AI Trading OS v4 — Project Brief

## Product Definition

AI Trading OS is an AI-native Personal Financial Terminal for multi-asset investors.

It unifies stocks, crypto, and on-chain assets; tracks portfolio memory; captures investment thesis; automates research; applies decision gates; protects trades with risk and behavior checks; and continuously improves the user's self-logic through post-trade review.

This product is not merely an AI trading assistant.
It is a terminal that automates the user's investment workflow, trading workflow, risk discipline, decision journaling, and self-logic review.

The v4 product wedge is:

> Bloomberg remembers the market. Brokers remember orders. TradingView remembers charts. We remember why the user bought, and when the user is about to violate their own logic.

The system should help cross-market investors unify stocks, ETFs, crypto exchange assets, stablecoins, and public on-chain wallet assets without becoming an investment advisor, a profit-promise product, or an autonomous black-box trading bot.

## Core Principle

Automate the user's investment process and self-discipline, not uncontrolled trading.

AI agents may research, explain, summarize, detect changes, and propose actions.
AI agents must never directly execute trades.

## Target Workflow

The system should automate:

1. portfolio data collection
2. data cataloging and data quality checks
3. market, news, and Web3 risk monitoring
4. research generation
5. thesis tracking
6. trading idea evaluation
7. decision gates
8. risk and behavior checks
9. order draft creation
10. human approval workflow
11. controlled paper or approved live execution
12. trade journaling
13. post-trade review
14. monthly decision-quality review
15. playbook and rule update proposals

## Required Trade Flow

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

## Required Architecture

The system is organized around these layers:

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

## Non-goals

- Uncontrolled speculation
- Fully autonomous, unbounded live trading
- LLM agents directly executing orders
- Broker, exchange, or wallet calls from research agents
- Credential or key storage in-repo
- Seed phrase or raw private key handling
- Web3 signing by default
- External sidecars bypassing the core gates, approvals, or audit trail

## Core Tenets

- Safe by default.
- Terminal-first, not chatbot-only.
- InvestmentConstitution, StrategyPlaybook, and InvestmentThesis sit above RiskEngine as first-class self-logic modules.
- Every action is traceable.
- Every order ties back to a thesis or explicit user rationale.
- Data quality uncertainty fails closed.
- Behavior risk is a first-class risk.
- Review loops improve the user's self-logic over time.
- Adapters, agents, risk, gates, execution, and review remain replaceable modules.

## Build Order

Do not start with broker integration. Build in this order:

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

Unless the user explicitly asks to continue, start with Phase -1 and Phase 0 only.
