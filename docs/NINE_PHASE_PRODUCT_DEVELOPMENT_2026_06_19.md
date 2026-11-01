# Nine-Phase Product Development Safe Slices - 2026-06-19

## What Was Developed

This pass turns the nine-stage product roadmap into callable, review-only product slices. The system can now inspect evidence, create founder daily workflow packets, normalize statement evidence, open audited ledger repair tasks, and show phase development status in the Complete Product workspace.

All new slices preserve the safety boundary:

- `execution_available=false`
- `production_capability=false`
- no live broker order routing
- no wallet signing
- no withdrawals
- no inline key storage

## New Or Expanded Backend Surface

- `GET /daily-use/onboarding`
- `POST /daily-use/onboarding`
- `POST /daily-use/daily-open`
- `POST /daily-use/daily-close`
- `GET /daily-use/drilldown/{queue_item_id}`
- Today Queue now also emits `portfolio_risk` actions for concentrated positions.
- `GET /ledger/statement-normalization-report`
- `POST /ledger/repair-workflow`
- `POST /ledger/repair-workflow/rerun-reconciliation`
- `GET /ledger/statement-imports/{batch_id}/rows/{row_index}`
- `GET /ledger/data-promotion-report`
- `GET /phase-development/summary`
- `GET /phase-development/{phase_key}`
- `POST /phase-development/real-readonly-data-proof/binance-private-verify`
- `POST /phase-development/research-evidence/configure`
- `GET /phase-development/research-evidence/eval`
- `GET /phase-development/portfolio-risk-terminal/drilldown/{dimension}`
- `POST /phase-development/private-beta-foundation/checklist`
- `POST /phase-development/traction-loop/configure`
- `POST /phase-development/broker-sandbox-proof/state`
- `POST /phase-development/controlled-pilot/gates`

Supported phase keys include:

- `founder_daily_use_alpha`
- `real_readonly_data_proof`
- `trusted_ledger` or `trusted_ledger_data_promotion`
- `research_evidence` or `research_evidence_thesis_delta`
- `portfolio_risk_terminal`
- `private_beta_foundation`
- `traction_loop` or `traction_commercial_loop`
- `broker_sandbox_proof` or `broker_sandbox_execution_proof`
- `controlled_pilot`

## Stage Status After This Pass

1. Founder Daily-Use Alpha: onboarding, daily open/close, and queue drilldown are implemented as review-only workflow packets.
2. Real Read-Only Data Proof: `binance_spot_readonly` evidence inspection is implemented. Private verification still requires a real read-only key in the user's private environment.
3. Trusted Ledger: statement normalization report, manual repair workflow, and raw/reviewed/trusted promotion report are implemented.
4. Research Evidence: safe LLM readiness, evidence packet presence, thesis delta, and eval readiness are exposed.
5. Portfolio Risk Terminal: exposure, concentration, stress scenarios, and risk drilldown payloads are exposed from holdings.
6. Private Beta Foundation: auth/RBAC/secrets/monitoring/backups/admin readiness evidence is exposed.
7. Traction Loop: waitlist, analytics, pricing hypothesis, demo/data-room export evidence is exposed.
8. Broker Sandbox Proof: sandbox contract, order state machine requirements, audit counts, and production execution lock are exposed.
9. Controlled Pilot: legal, ops, allowlist, limits, and hard-stop gates are exposed and remain locked until explicitly passed.

## Frontend Surface

`CompleteProductPanel` now loads `/phase-development/summary` and shows a nine-stage development status section beside the existing roadmap and buildout surfaces.

`OverviewPanel` now treats Today Action Queue as the primary daily-use control surface. It loads `/daily-use/action-queue`, exposes Daily Open, Daily Close, and Drilldown controls, and shows evidence count for the selected queue item.

## Second-Pass Development Update

This pass added real operation surfaces for the nine stages without crossing into production execution:

- Binance private read-only proof can attempt an authenticated read-only sync only when a `binance_spot_readonly` connection with `credentials_ref` exists. Missing or failed private verification returns a blocker packet instead of pretending success.
- Ledger repair can inspect a normalized statement row, create repair tasks, complete them through existing workflow review APIs, and rerun extended reconciliation.
- Research Evidence can store non-secret allowlist/configuration metadata and produce an eval packet for LLM secret reference, snapshot citation, structured evidence, and thesis delta.
- Portfolio Risk now exposes account/currency/venue/factor drilldowns and sends concentration anomalies into Today Queue.
- Private Beta, Traction, Broker Sandbox, and Controlled Pilot each have explicit checklist/state/gate update endpoints backed by local config, audit, operational events, or data-room export artifacts.
- Broker Sandbox state remains sandbox-only and rejects unsupported states. Controlled Pilot still reports `small_pilot_allowed=false` even when gates are recorded, requiring explicit human release outside this safe slice.

## Third-Pass Frontend Control Update

`CompleteProductPanel` now includes a `Nine-stage Ops Workbench` with direct controls for the current nine implementation tracks:

- Private `binance_spot_readonly` verification button that calls the authenticated read-only proof endpoint and shows blocker packets when no credentials reference exists.
- Ledger repair drawer with statement batch selection, row detail, task assignment, task completion, and rerun reconciliation.
- Research Evidence control surface for LLM allowlist, secret reference metadata, structured eval packet, and thesis-delta checks.
- Portfolio Risk terminal tabs for account, currency, venue, and factor drilldowns, plus stress scenario explanation and Today Queue anomaly rule text.
- Private Beta checklist for auth, RBAC, secret references, monitoring, backups, and admin console.
- Traction Loop control for waitlist/activation analytics/pricing/demo/data-room export configuration.
- Broker Sandbox state-machine control with idempotency key and sandbox-only adapter contract metadata.
- Controlled Pilot gate UI for legal, ops, allowlist, limits, monitoring, rollback, and kill switch.
- Human pilot review reminder that keeps live execution, wallet signing, withdrawal, DEX swap, automatic approval, and gate bypass explicitly unavailable.

Backend evidence packets now surface the matching stored configuration for research, private beta, traction, broker sandbox, and controlled pilot gates. The global secret guard remains strict; only the Private Beta checklist's boolean `secrets` status is allowed as non-secret readiness metadata.

## Follow-Up Plan

### Immediate

- Run private `binance_spot_readonly` verification with a real read-only key reference.
- Save the resulting account snapshot, quality report, and audit evidence packet.
- Add a small private verification runbook for `binance_spot_readonly`, including exchange-side key permission screenshots and withdrawal-disabled proof.
- Add visual evidence capture for private verification results: snapshot diff, quality score history, and audit packet download.

### Next Alpha Increment

- Persist daily open/close history instead of only latest local config packets.
- Add onboarding progress UI and first meaningful action analytics.
- Expand ledger repair drawer for skipped rows, duplicates, repair suggestions, and row-to-break linking.
- Add thesis delta views that compare latest research to active thesis checkpoints.
- Turn risk drilldown results into clickable lists that open the underlying position, thesis, ledger entry, and Today Queue action.
- Add persisted UI history for research eval results, sandbox lifecycle events, and pilot gate changes.

### Private Beta Readiness

- Replace local/header auth assumptions with production auth and RBAC.
- Configure secret manager references, monitoring, backup target, and restore drill evidence.
- Build admin views for users, events, jobs, backups, and data freshness.
- Create waitlist/invite status, analytics events, pricing hypothesis, demo path, and data-room export workflow.
- Add admin-only audit search, restore drill evidence, feature flags, invite codes, feedback inbox, and release notes.

### Sandbox And Pilot Gate

- Implement a sandbox-only broker adapter with idempotent state transitions.
- Reconcile sandbox fills back to ledger and audit every state change.
- Keep production credentials disabled until legal, ops, monitoring, allowlist, limits, rollback, and kill switch gates pass.
- Only after phases 1-8 have passing evidence should a tiny controlled pilot be reviewed by humans.
- Before any pilot review, add written legal scope, incident runbook, whitelist owner, hard limits, manual rollback drill, and kill-switch verification evidence.
