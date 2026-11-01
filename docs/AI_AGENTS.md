# AI Agents (Draft)

## Roles

- Research agent: generates watchlists, theses, and risk notes
- Signal agent: proposes trade intents with constraints and confidence
- Compliance/risk agent: checks rules, explains failures, suggests safer alternatives

## Guardrails

- Agents propose **intents**, never place orders directly.
- Prompts and outputs must be logged for auditability (with redaction rules).
