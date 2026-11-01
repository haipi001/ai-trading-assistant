# Thesis Capture

Convert the user's stated rationale into a structured InvestmentThesis.

Rules:
- Use only structured input facts.
- Do not create orders, order drafts, approvals, or executions.
- If facts are missing, represent the missing areas as limitations in the structured output.
- Keep invalidation conditions explicit and reviewable.

Required JSON fields:
- entry_reason
- key_drivers
- invalidation_conditions
- expected_horizon
- target_condition
- max_loss_tolerance_pct
- position_plan
- confidence
