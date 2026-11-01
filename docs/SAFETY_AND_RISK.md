# Safety and Risk

## Non-negotiable Defaults

- `live_trading_enabled = false` by default.
- `automation_level = A0_READ_ONLY` by default.
- Backtest and paper mode only unless a later task explicitly enables more.
- Web3 is read-only by default.
- No private keys.
- No seed phrases.
- No withdrawal-enabled CEX keys.
- No LLM direct execution.
- No signal direct execution.
- No strategy direct execution.
- No sidecar bypass around the main control system.

## Fail-closed Conditions

Block trade workflow progression when:

- data quality is unknown, stale, missing, incomplete, untrusted, or failed
- broker, exchange, wallet, order, or execution state is uncertain
- risk engine is unavailable
- AI output is invalid, hallucinated, unsupported, or contains executable order leakage
- required ResearchGate, ThesisGate, RiskGate, BehaviorGate, or ExecutionGate results are missing or not passed
- InvestmentConstitution, StrategyPlaybook, InvestmentThesis, or explicit user rationale is required but absent
- kill switch or live-execution disable flag is active

## Mandatory controls for any live mode

- Account allowlist + environment flag gate
- Position sizing limits (per-symbol, per-sector, portfolio-wide)
- Max daily loss / drawdown limit
- Order type restrictions (e.g., no market orders unless allowed)
- Circuit breaker on adapter errors or stale data
- Human approval workflow with audit logging
- Broker/exchange state reconciliation before execution
- Kill switch that blocks downstream execution
- Explicit user approval or explicitly permitted controlled automation policy

## Audit trail

Record at minimum:

- signal inputs, model versions, prompts (redacted if needed)
- risk checks and rationale
- approvals (who/when/what changed)
- order lifecycle events
- decision gate results
- behavior interventions and user responses
- thesis violations
- AI report evaluator failures
- workflow blocked transition reasons
- live-execution health checks and kill-switch events

## Prohibited In Early Phases

- live automated trading
- high-frequency trading
- broker credential handling beyond local secret references
- withdrawal-enabled CEX keys
- wallet signing
- DEX swaps
- bridge transactions
- token approvals
- copied execution paths from third-party projects

## AI Output Safety Validation (added 2026-07-05)

Lessons from the first real-provider (DeepSeek) eval run:

- **MockAIProvider only validates structure and workflow.** Real safety
  properties must be verified against real LLM providers plus red-team cases.
  Two gates that always passed under Mock were broken against real output:
  an exact-match eval check and a snake_case-only blocked-term list.
- **Blocked-action detection must cover how models actually write.** The
  detector in `app/ai/safety.py` normalizes snake_case / kebab-case /
  camelCase / punctuation / casing and matches English, Chinese, and
  mixed-language execution phrases. Rules carry category and severity;
  matches are structured and auditable.
- **Trade execution leakage is a critical safety failure.** Any AI output
  whose suggested action contains an execution instruction is rejected at
  schema validation, recorded in eval results, and audited. Red-team runs
  (`docs/RED_TEAM_CASES.md`) must show zero leakage.
- **AI-assisted review is not human-labeled evaluation.** `hallucination_rate`
  remains `null` in every eval result and summary until human-labeled review
  exists. See `docs/AI_EVALS.md`.
- **A safe-looking run is not model eligibility.** Each exact Provider/model
  needs 100 unique configured external calls across at least three task types
  and 100 unique human labels. Duplicate runs and Mock results do not increase
  this coverage. Two models must independently pass before comparison is ready
  for a human release decision, and the gate never enables a model itself.
- **Release blocks are model-specific and fail closed.** Any execution leakage
  permanently blocks that exact Provider/model version from further eval use;
  another model's state is calculated independently rather than copied from a
  loop or global status.
