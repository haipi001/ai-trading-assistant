# Human-Controlled Eight-Project Foundation

The eight production projects expose two separate progress measures:

- `human_control_implementation_pct`: configuration, approval, simulation, drill, and audit surfaces implemented in code.
- `external_evidence_progress_pct`: evidence produced by real exchanges, models, identity tenants, monitoring services, brokers, legal reviewers, CI, and beta users.

The first measure can reach 100% before credentials are supplied. It never advances the second measure and never enables production execution.

## Control API

- `POST /production/human-control/initialize`: create safe defaults for all eight projects.
- `GET /production/human-control/status`: return control coverage and external blockers side by side.
- `PUT /production/human-control/projects/{project_key}`: update one project's metadata-only control policy.
- `POST /production/human-control/projects/{project_key}/drills/{scenario}`: record a simulated rehearsal artifact.
- `POST /production/human-control/data/simulate`: create a simulated read-only snapshot, quality report, event, and audit packet.
- `GET /production/human-control/data/stability`: summarize simulated run count, pass rate, and latency.
- `POST /production/research/eval-dataset/seed`: create 12 idempotent reference cases across stocks, crypto, portfolio risk, and thesis review.

All write routes require `readiness:write`. Drill and simulation artifacts contain `counts_as_external_evidence=false`.

## Data adapter boundary

Simulation uses the same persisted contract required by a later authenticated adapter:

1. `DataSourceConnection`
2. `DataSnapshot`
3. `DataQualityReport`
4. `OperationalEvent`
5. `ExportArtifact`

The real Binance path remains `POST /data-sources/connections/{connection_id}/sync-account`. A simulation uses provider `simulated_readonly` and snapshot type `read_only_account_simulation`, so production acceptance cannot mistake it for `binance_spot_readonly` evidence.

## LLM modes

- `mock`: deterministic local reports with no external calls or billing.
- `bring_your_own`: the user supplies an `env://`, `aws-sm://`, `gcp-sm://`, or `vault://` reference. Secret values are never persisted.
- `platform_managed`: uses the platform's configured provider and requires an active paid entitlement before a real call.

Every non-mock mode requires explicit human approval, a positive monthly budget, and a positive per-request budget. Research reports can select `provider=configured`; the server resolves the user's stored policy and fails closed.

Reference eval fixtures do not count as model runs. Semantic hallucination rate remains `null` until human-labeled review exists; structured validation is only a proxy and is not presented as a hallucination measurement.

## Safety boundary

Automated live trading, wallet signing, withdrawals, DEX swaps, automated approval, and gate bypass remain disabled. Completing human controls only prepares a controlled workflow; it does not approve a pilot or production execution.

## User-imported credentials (added 2026-07-06)

`bring_your_own` no longer requires hand-editing `.env`. The product now has a
self-service path:

- `POST /production/human-control/llm/credentials` — user submits provider
  (openai/deepseek), model, API key, budgets, and the approval checkbox. The
  key is written only to `backend/.user_secrets.env` (gitignored, mode 0600,
  loaded into process env at startup); config stores `env://USER_<PROVIDER>_API_KEY`.
  The raw value never enters the database, audit logs, or API responses.
- `POST /production/human-control/llm/test-call` — one real structured
  review-only call through the configured provider so the user can verify
  their key inside the product. Blocked without approval/budgets; the result
  is recorded as an operational event and `counts_as_external_evidence=false`.
- `GET/POST/DELETE /production/local-secrets` — generic named local secrets
  (names and references only in responses), so future read-only exchange keys
  (e.g. `USER_BINANCE_API_KEY`) follow the same pattern instead of manual env
  editing.
- Frontend: Settings workspace → "AI 模型与密钥（自定义导入）" card provides the
  form, one-click test call, and stored-reference list with delete.

Provider TLS requests now pin the `certifi` CA bundle; on machines where
Python's default trust store is incomplete, provider calls previously failed
with certificate errors even though the chain was valid.
