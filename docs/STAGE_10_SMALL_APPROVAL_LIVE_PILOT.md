# Stage 10 Small Approval Live Pilot

This stage adds a small-notional live pilot readiness report.

## Scope

- Added `POST /live-execution/small-pilot-readiness`.
- Checks pilot notional size, human approval, live execution readiness, sandbox boundary, and rollback plan.
- Reuses the existing live `prepare` checks.
- Writes `live_execution.small_pilot_readiness_checked` audit logs.

## Pilot Rules

The readiness report blocks when:

- estimated notional is missing or zero
- estimated notional exceeds `max_notional`
- draft is not human approved
- live execution readiness has blocking reasons
- requested price or pilot limit is invalid

## Safety Boundary

- This endpoint is a readiness report only.
- It never creates `Execution`, never changes `OrderDraft.execution_status`, never creates positions, and never submits broker orders.
- It always returns `execution_available=false` and `real_broker_call_allowed=false`.
- Default local settings remain blocked because live trading and live execution are disabled.

## Verification

- Focused backend tests cover a small approved draft that remains blocked by live readiness and an oversized draft blocked by pilot notional limits.
