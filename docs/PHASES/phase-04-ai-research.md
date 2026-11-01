# Phase 04 — AI Research

## Deliverables

- Research workflow + UI for notes/theses
- Prompt + output logging with redaction rules

## Implemented Foundation

- `AIProvider` interface with deterministic `MockAIProvider`
- `OpenAIProvider` placeholder that makes no external calls
- Markdown prompt templates for portfolio, stock, technical, crypto, and risk reviews
- `ReportGenerator` service that validates AI JSON before persistence
- `POST /reports/generate` endpoint for mock report generation
- `ResearchReport`, `AgentRun`, and `AuditLog` persistence path

## Safety Constraints

- Reports use only caller-provided `input_facts` and `data_snapshot_id`.
- Missing facts must be represented as unavailable data, not inferred data.
- Reports cannot contain executable order instructions.
- Invalid JSON or schema-invalid output is rejected and logged.
- No broker, exchange, wallet, paper-trading, or live-trading path exists in this phase.
