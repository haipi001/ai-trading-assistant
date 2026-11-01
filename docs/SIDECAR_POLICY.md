# Sidecar Policy

Sidecars are allowed only when they stay outside the core control plane.

## Purpose

Use a sidecar when an external system is useful for:

- data ingestion
- research generation
- simulation
- backtesting
- accounting
- execution after approval

Do not use a sidecar as the source of truth for self-logic, approvals, or safety policy.

## Mandatory Boundaries

A sidecar must not bypass:

- InvestmentConstitution
- StrategyPlaybook
- InvestmentThesis
- DecisionGates
- RiskEngine
- BehaviorGate
- ApprovalWorkflow
- AuditLog

## Approved Direction Of Control

The only acceptable control pattern is:

`local self-logic -> local gates -> local approval -> sidecar call -> result callback -> local audit and review`

## Sidecar Requirements

- Run as a separate process, service, or tool boundary.
- Use typed request and response contracts.
- Receive only the minimum data needed for the task.
- Return structured results that can be written into local audit and review records.
- Support a disabled or mock mode before any real execution mode is considered.
- Fail closed when state, permissions, or returned data are uncertain.

## Prohibited Sidecar Behaviors

- placing trades without local approval
- creating orders that bypass local gates
- storing local secrets outside the approved secret path
- becoming the sole ledger of record
- mutating core self-logic objects directly
- hiding execution details from local audit logs

## Typical Examples

- `OpenBB`: data-platform or research sidecar
- `rotki`: accounting or reconciliation sidecar
- `Freqtrade`: execution sidecar only after local approval
- `Hummingbot`: isolated execution or market-making sidecar only after local approval

Even when a sidecar license is permissive, execution authority must remain local and audited.
