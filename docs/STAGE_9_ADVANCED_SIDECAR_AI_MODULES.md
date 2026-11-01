# Stage 9 Advanced Sidecar AI Modules

This stage adds a policy evaluator for proposed AI/sidecar modules.

## Scope

- Added `POST /modules/sidecar-policy/evaluate`.
- Added `ai_sidecar_policy` to the module registry.
- Evaluates whether a proposed sidecar can stay outside the local control plane.
- Writes `sidecar_policy.evaluated` audit logs.

## Policy Rules

The evaluator blocks sidecars that:

- create orders directly
- execute trades without local approval
- store local secrets
- mutate core state directly
- use an invalid control pattern
- become source of truth for self-logic, approvals, safety policy, risk, decision gates, audit, or ledger

The approved control pattern is:

`local_self_logic_to_sidecar_callback`

## Required Controls

- typed request/response contract
- minimum data scope
- local gates before sidecar
- local approval before execution sidecar
- local audit log for request and callback
- mock or disabled mode available
- fail closed on uncertain state

## Safety Boundary

- Policy evaluation is read-only.
- It never registers a real sidecar process, starts external services, creates orders, executes trades, stores secrets, or calls brokers.
- The response always sets `execution_available=false` and `real_broker_call_allowed=false`.

## Verification

- Focused backend tests cover an approved read-only research sidecar and a blocked sidecar that attempts to bypass the control plane.
