# Phase -1 — Product Wedge Docs

## Objective

Align the repository with the v4 master prompt before adding new product surface area.

Phase -1 is documentation and governance only. It defines what the product is, what it is not, which safety rules are non-negotiable, and which phase order future implementation must follow.

## Product Wedge

AI Trading OS is an AI-native Personal Financial Terminal for multi-asset investors.

It remembers why the user bought, whether new actions still match the user's stated logic, and when behavior or data quality should block a trade workflow.

The product is not:

- an autonomous black-box trading bot
- an investment advisor
- a profit-promise product
- a Bloomberg, TradingView, or broker clone
- a crypto bot or wallet signer

## Required Phase -1 Deliverables

- `AGENTS.md` states the v4 safety rules and phase order.
- `PROJECT_BRIEF.md` states the product wedge, non-goals, and 23-layer architecture.
- `ROADMAP.md` separates the new v4 phase index from historical v3 implementation slices.
- `README.md` links the v4 Phase -1/0 baseline for local operators.
- Open-source reuse remains governed by `docs/LICENSE_POLICY.md`, `docs/OPEN_SOURCE_MAP.md`, `docs/SIDECAR_POLICY.md`, and `THIRD_PARTY_NOTICES.md`.

## Acceptance

- No schema change.
- No API change.
- No broker, exchange, or wallet integration.
- No live execution path.
- No private key, seed phrase, trading password, or withdrawal-enabled CEX key handling.
- Future work starts at the smallest safe phase unless the user explicitly asks to continue.

## Next Phase

Phase 0 keeps the existing local scaffold and regression baseline healthy before implementation resumes.
