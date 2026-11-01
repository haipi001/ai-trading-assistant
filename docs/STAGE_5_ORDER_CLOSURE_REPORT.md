# Stage 5 Order Closure Report

This stage adds a read-only order workflow closure layer.

## Scope

- Added `/workflows/order-closure-report`.
- Aggregates each order draft with its linked order intent, thesis or explicit rationale, latest five decision gates, latest risk check, human approval, latest paper execution, post-trade review, and safety boundary.
- Classifies each draft as `blocked`, `review_required`, or `closed`.
- Reports blockers and next actions for incomplete or inconsistent workflows.

## Closure Rules

- `blocked`: hard prerequisites are missing or failed, such as missing gates, failed risk check, rejected approval, missing review after execution, or non-paper execution in this safe slice.
- `review_required`: the draft is structurally valid but still needs human action, such as paper execution or completion of a pending post-trade review.
- `closed`: rationale/thesis, gates, risk, approval, paper execution, post-trade review, and safety boundary checks are all `ok`.

## Safety Boundary

- The endpoint is read-only.
- It never approves drafts, executes orders, creates post-trade reviews, applies playbook changes, or calls brokers.
- The response always sets `execution_available=false`.
- The current closure safe slice accepts only missing execution or paper execution records.

## Verification

- Focused backend tests cover approved draft waiting for paper execution, paper-filled draft waiting for post-trade review, and completed review closure.
