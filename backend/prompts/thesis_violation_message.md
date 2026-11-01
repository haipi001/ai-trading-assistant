# Thesis Violation Message

Create a user-facing intervention message when a current action conflicts with a recorded thesis.

Rules:
- Use only the prior thesis statement and current action.
- Do not execute trades.
- Do not create order drafts.
- Prefer HARD_CONFIRM for unresolved conflicts unless the caller explicitly provides another intervention level.

Required JSON fields:
- violation_type
- message
- explanation
- intervention_level
