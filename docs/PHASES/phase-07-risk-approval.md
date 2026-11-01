# Phase 08 — Risk Engine + Approval

## Deliverables

- Hard-rule risk engine for `OrderIntent`
- `RiskCheck` persistence for every risk evaluation
- Gated `OrderDraft` creation after passed risk check
- Human approval, rejection, and modify workflow
- Audit logging for risk outcomes and approval decisions

## Implemented API

- `POST /risk/check-order`
- `POST /orders/intents/{id}/draft`
- `POST /orders/drafts/{id}/approve`
- `POST /orders/drafts/{id}/reject`
- `POST /orders/drafts/{id}/modify`

## Hard Rules

- Live account orders are blocked unless `live_trading_enabled` is true.
- Account mode must allow order drafting.
- Asset must be tradable.
- Manual or auto asset enablement must match order mode.
- Order notional must stay below `max_order_notional`.
- Final position weight must stay below `max_position_pct`.
- Daily loss, leverage, liquidity, volatility, and kill switch rules must pass.

## Safety Constraints

- Risk failures write `RiskCheck` and `AuditLog`.
- Drafts created through Phase 8 require passed risk status.
- Draft approval requires latest risk check to be passed.
- Approval and rejection write `AuditLog`.
- No live execution or paper execution is implemented in this phase.
