# Stage 8 Controlled Live Sandbox

This stage adds a live-execution sandbox dry run that exercises the live gate checks without mutating order state.

## Scope

- Added `POST /live-execution/sandbox-run`.
- Reuses live execution prepare checks, price/quantity calculation, broker submission planning, and rollback plan generation.
- Records an audit log event for the sandbox run.
- Returns a machine-readable broker submission plan with `status=not_submitted`.

## Sandbox vs Execute

- `/live-execution/sandbox-run` does not create an `Execution`, does not update `OrderDraft.execution_status`, does not create positions, and does not create paper executions.
- `/live-execution/execute` remains a fail-closed blocked attempt that records a blocked live execution and journal entry.

## Safety Boundary

- The sandbox never calls a broker.
- It always returns `execution_available=false`, `sandbox_only=true`, and `real_broker_call_performed=false`.
- It keeps `external_order_id=null`.
- Existing blockers such as disabled live trading, disabled live execution, dry-run mode, broker disconnected, account not live, missing gates, failed risk, and kill switch remain visible.

## Verification

- Focused backend tests confirm sandbox-run does not mutate the draft, does not create live execution history, does not create paper executions, does not create positions, and writes `live_execution.sandbox_run` audit logs.
