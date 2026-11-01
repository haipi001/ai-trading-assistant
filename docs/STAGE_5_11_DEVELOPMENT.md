# Stage 5-11 Development Plan And Current Slice

Date: 2026-06-16

This document tracks the first implementation pass for Stage 5, 6, 7, 8, 9, 10, and 11. The scope is governance-first: surface readiness, blockers, and next actions before any execution capability.

## Stage Map

| Stage | Goal | Current Slice | Acceptance |
| --- | --- | --- | --- |
| 5 Strategy Playbook | Connect every order workflow to a human-approved strategy playbook. | Stage readiness checks whether `OrderIntent.strategy_playbook_id` exists, is active, and still requires human approval. | Missing or inactive playbooks block progression; non-human-approved playbooks require review. |
| 6 Investment Thesis | Ensure each trade has a clear thesis or explicit user rationale. | Stage readiness checks linked `InvestmentThesis` status and falls back to explicit rationale only as review-required. | Active/monitoring theses pass; missing thesis without rationale blocks. |
| 7 Thesis Capture + Monitor | Keep thesis evidence fresh before orders are reviewed. | Stage readiness checks the latest `ThesisCheckpoint` freshness and invalidation flags. | Invalidating checkpoints block; stale or weakening checkpoints require review. |
| 8 Decision Gates | Require research, thesis, risk, behavior, and execution gates. | Stage readiness verifies the five latest gate types and their statuses. | Missing or blocked gates block; warnings require human review. |
| 9 Risk Engine | Require hard risk checks before draft review. | Stage readiness reads the latest `RiskCheck` for the order intent. | Missing or failed hard risk checks block. |
| 10 Behavior Engine | Record behavioral intervention state before approval. | Stage readiness reads the latest `BehaviorIntervention`. | BLOCK interventions block; hard-confirm/no response and bypassed interventions require review. |
| 11 Workflow State Machine | Make skipped or blocked transitions auditable. | Stage readiness reads the latest `WorkflowState` for the order intent or draft. | BLOCKED workflow state blocks; missing workflow state requires review. |

## Implemented In This Slice

- Backend: added `StageReadinessService` to aggregate Stage 5-11 checks for recent order intents and latest drafts.
- Backend: added `GET /workflows/stage-5-11-readiness` with queue counts, item readiness, blockers, next actions, per-stage checks, and `execution_available=false`.
- Backend schemas: added `StageReadinessCheckRead`, `StageReadinessItemRead`, and `StageReadinessQueueRead`.
- Frontend: Workflow panel now displays Stage 5-11 readiness counts and item-level check tables.
- Tests: focused backend tests cover an unprepared blocked order intent and a fully prepared order draft that is ready only for human review.

## Safety Boundary

- No live trading was enabled.
- No broker, exchange, wallet, DEX, withdrawal, signing, or order-placement write path was added.
- Stage readiness is read-only aggregation over existing records.
- `ready_for_human_review` means reviewable by a human, not executable.
- The endpoint and UI always expose `execution_available=false`.
- The frontend adds status inspection only; it does not create approvals, execute drafts, or mutate workflow state.

## Development Plan

1. Stage 5: add playbook coverage reports by asset, market, and strategy type; require explicit playbook selection in every order-entry surface.
2. Stage 6: add thesis quality scoring, thesis-to-position coverage dashboards, and contradiction detection against current order rationale.
3. Stage 7: add scheduled thesis checkpoint reminders, stale thesis queues, and structured evidence ingestion from read-only research/data sources.
4. Stage 8: normalize gate evidence payloads and expose gate replay/debug views for each order intent.
5. Stage 9: expand hard risk checks for concentration, liquidity, volatility, account mode, and portfolio-level drawdown using reconciled ledger inputs.
6. Stage 10: add behavior profile trend views, cooldown timers, and hard-confirm response capture in approval workflows.
7. Stage 11: route order workflows through explicit state transitions instead of ad hoc CRUD writes, with blocked-transition audit reports.

## Verification

Focused verification for this slice:

```bash
cd backend
.venv/bin/pytest tests/test_stage_5_11_readiness.py -q

cd ../frontend
npm run typecheck
```

Expected current result: backend focused tests pass and frontend typecheck passes. Full regression should remain green before continuing to a broader mutation or approval workflow slice.
