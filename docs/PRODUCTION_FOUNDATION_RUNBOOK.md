# Production Foundation Runbook

## Capability boundary

The production integration layer provides managed OIDC sessions, RBAC, user isolation checks, secret-reference resolution, allowlisted structured LLM calls, SLO evidence, invitations, activation analytics, pricing configuration, permissioned data-room exports, sandbox broker reconciliation, and Controlled Pilot evidence gates.

It does not enable automated live trading, wallet signing, withdrawals, DEX swaps, automatic approval, or gate bypass.

## Secret references

Supported reference forms:

- `env://NAME`
- `aws-sm://secret-id[#json-key]` with the optional `production` dependency
- `gcp-sm://project/secret[/version]` with `GCP_ACCESS_TOKEN_REF`
- `vault://mount/path#field` with `VAULT_ADDRESS` and `VAULT_TOKEN_REF`

Only references and verification metadata are persisted. Secret values must never be returned by an API, written to an audit log, or committed.

### Real Secret Manager lifecycle acceptance

Use a disposable, non-production AWS/GCP/Vault secret and an owner/admin managed session. The four phases must surround real provider-side changes; do not use the session signing key, data-source credential or alert webhook itself.

```bash
export ATOS_SESSION_TOKEN='temporary-managed-session'
export ATOS_SECRET_REFERENCE='aws-sm://disposable/atos-rotation-test'

./scripts/secret_manager_lifecycle_acceptance.py \
  --api-base-url https://api-staging.example.invalid \
  --phase baseline --execute

# Rotate the disposable secret in the cloud provider, then:
./scripts/secret_manager_lifecycle_acceptance.py \
  --api-base-url https://api-staging.example.invalid \
  --phase rotated --execute

# Disable/delete the disposable secret, then:
./scripts/secret_manager_lifecycle_acceptance.py \
  --api-base-url https://api-staging.example.invalid \
  --phase invalidated --execute

# Restore it as a new version, then:
./scripts/secret_manager_lifecycle_acceptance.py \
  --api-base-url https://api-staging.example.invalid \
  --phase recovered --execute

unset ATOS_SESSION_TOKEN ATOS_SECRET_REFERENCE
```

Baseline requires a provider version identifier. Rotation only passes when the version changes. Invalidation only passes after a prior rotation and when resolution returns 422 while the stored SecretReference becomes `invalid`. Recovery must resolve again and reactivate the reference. Failed verification stores only a stable error class, never the provider error message or secret value.

The mode-0600 state file contains a reference hash, provider backend, versions and phase results; it excludes the raw reference, session token and secret values. Dry-run phases explicitly record `real_secret_manager_call_performed=false` and are not external evidence.

## Managed auth

Set `MANAGED_AUTH_REQUIRED=true`, `OIDC_ISSUER`, `OIDC_USERINFO_URL`, `OIDC_CLIENT_ID`, and `AUTH_SESSION_SECRET_REF`. The login endpoint validates the provider userinfo response, maps the configured role claim onto the local RBAC matrix, issues a short-lived revocable session, and never stores the provider access token.

For a private Beta, also set `MANAGED_AUTH_INVITATION_REQUIRED=true`. Unknown OIDC subjects are then denied until an operator preissues an invitation. Invitations expire after `INVITATION_TTL_HOURS` (72 by default), lock after `INVITATION_MAX_ATTEMPTS` failed claims (5 by default), can be revoked by an operator, and are consumed once. The database stores only a SHA-256 digest; the raw code is returned only at creation and must be delivered through an approved private channel. An invited user's OIDC role claim cannot override the preissued role. After login, the user claims the code in Settings, then completes the existing first-run data-mode flow. Reissuing or revoking an invitation invalidates the previous code.

The Admin / Dev maintenance page contains the private-Beta invitation queue. Owners and admins can issue and revoke invitations; operators can inspect lifecycle status but cannot issue or revoke. Viewers cannot read the queue. The list API returns only invitee metadata, status, timestamps, failed-attempt count and lock state—never the code digest or raw code. The creation receipt displays the raw code once and explicitly performs no email or external-message delivery.

When managed auth is required, all non-public routes require a managed session. Non-admin users cannot override `user_id` query scope.

Migration `20260717_0021` adds tenant ownership to every user-owned legacy table. Before upgrading an existing single-user deployment, set `LEGACY_TENANT_USER_ID` to the exact OIDC `sub` that owns the existing rows. The migration backfills all legacy rows to that subject, makes every tenant column non-null, and creates tenant indexes. Do not leave the default `default-user` value when the managed OIDC subject differs. Back up the managed PostgreSQL database first, run the migration in staging, and verify the owner can see the pre-migration records while a second test identity receives no rows/404/403.

The application also binds top-level JSON `user_id` fields to the managed session and applies SQLAlchemy tenant criteria to every user-owned model. Cross-tenant inserts, updates, and deletes fail before flush. Only `Asset`, `Candle`, `Chain`, and `Quote` remain shared reference/market-data models; they contain no account credentials or private user records.

### Real two-identity staging acceptance

Create two temporary least-privileged identities in the real OIDC tenant. Both must receive `viewer` or `operator`, not owner/admin. Put their short-lived provider access tokens in process environment only:

```bash
export ATOS_OIDC_ACCESS_TOKEN_A='injected-temporarily'
export ATOS_OIDC_ACCESS_TOKEN_B='injected-temporarily'
./scripts/staging_oidc_isolation_acceptance.py \
  --api-base-url https://api-staging.example.invalid \
  --environment staging \
  --execute
unset ATOS_OIDC_ACCESS_TOKEN_A ATOS_OIDC_ACCESS_TOKEN_B
```

The runner verifies two distinct subjects/sessions, bounded session TTL, unauthenticated rejection, spoofed identity-header overwrite, query and JSON user-scope denial, tenant-filtered account lists, resource-ID isolation, privileged RBAC denial, session revocation and survival of the other identity's session. It creates clearly named staging-only Account and ExportArtifact records; it never invokes trading, broker, wallet-signing or external financial APIs.

The runner refuses HTTP/local targets, does not follow redirects, reads tokens only from environment, and writes mode-0600 evidence containing no access/session tokens or raw OIDC subjects. A dry run validates inputs but explicitly records `real_oidc_calls_performed=false`; it is not acceptance evidence.

Production execution requires both `--execute` and the separate `--allow-production` acknowledgement, but staging must pass first. Owner/admin cross-user administration is outside this least-privilege test and requires a separate approved administrative access review.

## Release and logging protection

Run `./scripts/migration_guard.sh` before every release. It requires exactly one migration head, upgrades a fresh isolated database, verifies ORM/migration parity with `alembic check`, downgrades one revision, re-upgrades, and checks parity again. CI also runs Python and frontend dependency audits, high/high Bandit SAST, and `scripts/secret_scan.py`. These are blocking checks, not readiness metadata.

Keep `SAFE_REQUEST_LOGGING_ENABLED=true`. The application disables Uvicorn's raw access logger and emits structured events containing only a server-generated request ID, HTTP method, route template, status, duration, outcome, and exception class. Query strings, headers, bodies, raw URL paths, user IDs, and exception messages are excluded. External log collectors must ingest this safe logger and must not re-enable proxy/application raw request logging without equivalent redaction.

Before staging/private Beta, also set `API_RATE_LIMIT_ENABLED=true` and configure Redis. Managed login requests are limited per client address, invalid managed-session attempts use a separate per-client bucket, and authenticated API traffic is limited per OIDC subject. Counters use atomic Redis operations and hash identities before forming keys. Exceeded limits return `429` with `Retry-After`; an unavailable rate-limit store returns `503` and fails closed. Defaults are 10 logins, 30 failed-auth attempts, and 120 authenticated requests per 60 seconds; tune these from observed staging traffic rather than disabling the control.

## Managed staging and production release

Managed deployments use `infra/compose.managed.yml` plus exactly one of `infra/compose.staging.yml` or `infra/compose.production.yml`. This contract contains no database/Redis container and no default password. It rejects missing images, database, Redis, OIDC, session secret reference, CORS, service name, or legacy owner. Managed auth, rate limiting, safe logging, observability, read-only automation and all execution locks are fixed in the contract.

Build immutable images before release. The frontend API URL is compiled into the standalone Next.js image:

```bash
docker build -t registry.example/atos-backend:GIT_SHA backend
docker build --build-arg NEXT_PUBLIC_BACKEND_URL=https://api.example.invalid \
  -t registry.example/atos-frontend:GIT_SHA frontend
```

Copy `infra/managed.env.example` outside the repository and inject the populated values through the deployment platform or a mode-0600 file. Validate without deployment:

```bash
./scripts/managed_release.py --environment staging \
  --env-file /secure/path/atos-staging.env
```

Deploy only with explicit execution:

```bash
MANAGED_DATABASE_URL='postgresql+psycopg://injected-by-platform' \
ATOS_RDS_INSTANCE_ID='atos-staging-db' \
./scripts/aws_rds_backup_snapshot_acceptance.py \
  --environment staging \
  --release-id "$RELEASE_ID" \
  --region ap-southeast-1 \
  --execute

./scripts/managed_release.py --environment staging \
  --env-file /secure/path/atos-staging.env \
  --restore-drill-evidence /secure/path/postgres-restore-drill-LATEST.json \
  --backup-snapshot-evidence /secure/path/aws-rds-backup-snapshot-LATEST.json \
  --readiness-url https://api-staging.example.invalid/health/ready \
  --execute
```

An executed deploy requires a mode-0600 evidence file from a real `managed_postgres_restore_drill.py --execute` run. It must be `passed`, match the release environment and target database fingerprint, confirm isolated restore plus schema/row-count parity, and be no more than 720 hours old by default. Dry-run, SQLite, cross-environment, other-database, stale, future-dated, or group/world-readable evidence fails closed before Docker or migration runs. Tighten the window with `--restore-drill-maximum-age-hours`; it cannot exceed 720 hours.

The AWS RDS runner creates a retained manual snapshot through the real AWS CLI, waits for `available`, and describes it again. Before creation it verifies that the RDS instance endpoint exactly matches the managed database URL, the engine is PostgreSQL, and source storage is encrypted with KMS. The final snapshot must be manual, newly created, available, encrypted, and KMS-backed. AWS credentials stay in the AWS credential chain; evidence stores only hashes of the instance, endpoint, and snapshot reference.

An executed deploy requires both gates: a recent successful restore drill and a current provider snapshot tied to the exact `RELEASE_ID`, environment and database fingerprint. Snapshot evidence defaults to a four-hour maximum age and cannot be relaxed beyond 24 hours. Dry-run, reused release evidence, another database, unencrypted storage/snapshot, non-manual snapshot, missing KMS, non-available state, or weak file permissions all fail before Docker runs. The snapshot is deliberately retained; deletion is a separate provider retention operation.

The restore gate proves that the same managed database was recently restorable, while the snapshot gate proves a current pre-migration recovery point exists. Neither local SQLite nor an artifact reference alone satisfies either gate. The implemented provider is AWS RDS DB instances; GCP Cloud SQL and Aurora clusters remain unsupported until dedicated adapters exist and must not be reported as verified by this runner.

Set `RELEASE_ID` to the immutable build identifier used by both image tags. The deploy action takes a non-blocking deployment lock, pulls the target images, runs `alembic upgrade head`, then requires both `alembic current --check-heads` and `alembic check` to pass against the target managed PostgreSQL database before it replaces backend/frontend. `/health/ready` must then return the exact target release ID. Credential-free release state and evidence are saved as mode-0600 files under ignored `private-evidence/managed-releases`; restore evidence is represented only by its SHA-256 digest, database fingerprint, completion time, and age, never by its path or connection URL.

The first executed deployment has no known-good rollback target and therefore requires the explicit `--allow-first-deploy-without-rollback` acknowledgement. Later successful deployments retain the current and previous immutable release descriptors. If migration, head verification, or schema-drift verification fails, the running application is left untouched. If replacement or readiness verification fails, the tool automatically restores the previous images and verifies their exact release ID. Exit code 2 means the target failed without changing the application or was automatically rolled back successfully; inspect the redacted `failed_stage` and outcome. Exit code 3 means rollback also failed and requires immediate operator intervention.

To deliberately restore the recorded previous release, use `--action rollback --execute`; do not edit the env file back by hand. Release and rollback never perform an automatic database downgrade. Migrations must remain compatible with the previous application throughout the rollback window; destructive cleanup belongs in a later release.

## Real LLM

Set `EXTERNAL_LLM_CALLS_ENABLED=true`, point `OPENAI_API_KEY_REF` at a secret manager, and include the exact `openai:MODEL` entry in `LLM_PROVIDER_ALLOWLIST_RAW`. Responses must match the strict research report JSON schema and pass the existing report evaluator before persistence.

Create versioned eval cases through `/production/research/eval-cases`, run them explicitly, and inspect `/production/research/eval-summary`. Eval runs remain research-only.

## Binance private verification

Follow `BINANCE_SPOT_READONLY_PRIVATE_VERIFY_RUNBOOK.md`, then run:

```bash
python scripts/private_verify_binance.py \
  --permission-proof-ref artifact://private/binance-permissions-redacted \
  --withdrawal-disabled-proof-ref artifact://private/binance-withdrawal-disabled-redacted
```

The command exits non-zero unless a real read-only snapshot and quality report are produced.

## Restore drill

For the local SQLite deployment:

```bash
python scripts/sqlite_restore_drill.py
```

The script performs an isolated backup and restore, runs `PRAGMA integrity_check`, compares core table counts, and saves private evidence. Production PostgreSQL restore must be repeated in the managed database environment.

For managed PostgreSQL, validate the drill contract first:

```bash
MANAGED_DATABASE_URL='postgresql+psycopg://injected-by-platform' \
./scripts/managed_postgres_restore_drill.py --environment staging \
  --backup-encryption-proof-ref artifact://provider/backup-encryption-policy \
  --retention-policy-ref artifact://provider/retention-policy
```

Add `--execute` only inside the isolated staging/operations environment. The script takes a logical dump, creates a randomly named isolated database, restores it, compares Alembic revision, table set and row counts, then destroys the temporary dump and restore database. Passwords use `PGPASSWORD`, never command arguments or evidence. Production mode refuses local hosts and PostgreSQL connections without required TLS.

This logical drill does not prove provider encryption, off-site durability, retention or cross-region recovery. Those remain external evidence even when the drill passes.

## Application data retention

Configure retention from Admin / Dev → Maintenance → Data retention policy. The default is preview-only. Saving a policy never deletes records. The application can remove only terminal `observability.slo_breached` telemetry after 30–3650 days and terminal Webhook delivery telemetry after 365–3650 days, scoped to the current tenant.

Applying cleanup requires all three controls: the policy is enabled, the operator has `readiness:write`, and the exact confirmation phrase `DELETE_EXPIRED_OPERATIONAL_TELEMETRY` is entered. The delete and audit summary commit in one database transaction. Open alerts, other tenants, audit logs, investment records, account snapshots, ledger/reconciliation, activation/Beta metrics, restore drills and acceptance evidence are excluded from this mechanism. User-account deletion is a separate privacy workflow and must not be simulated through telemetry retention.

Audit retention is recorded in the policy but application deletion remains disabled. Configure database/provider backup retention and immutable audit storage separately; the managed restore drill's `--retention-policy-ref` remains required external evidence.

## Privacy self-service

The normal Settings page exposes Privacy and personal data without requiring Admin / Dev. `GET /production/privacy` returns the versioned disclosure and a real per-tenant inventory. The disclosure is explicitly a private-beta candidate policy: AI output is not individualized investment advice, and qualified counsel must review the privacy terms and actual processor inventory before public launch.

`POST /production/privacy/export` scans every database table with a `user_id` column and exports only the authenticated tenant. Session records are omitted, prior export payloads are reduced to summaries, and secret-shaped fields or reference identifiers are replaced by a hash prefix. The packet and audit summary state that raw secret values are absent. The user can download the JSON directly from Settings.

Deletion uses a guarded two-step flow:

1. Enter `REQUEST_MY_DATA_DELETION`. The server creates a seven-day cooling-off period and returns a random verification nonce once; only its SHA-256 digest is stored.
2. The user may cancel at any time during the grace period, which invalidates the nonce. After the scheduled time, execution additionally requires the original nonce and exact `PERMANENTLY_DELETE_MY_DATA` phrase.

Execution deletes all rows owned by that tenant in reverse foreign-key order, including application session records and secret references. Other tenants and shared market reference data are untouched. Existing audit rows are reduced to a random pseudonym and minimal deletion marker; a pseudonymized completion receipt remains. The whole operation is transactional and fails closed on any constraint error. The application never held provider secret values, so users must separately delete provider-side secrets they no longer need.

Do not treat an unreviewed disclosure, a generated export, or a simulated deletion as legal compliance evidence. Before private Beta, exercise export with a test user. Before public launch, attach counsel-reviewed policy and real subprocessor evidence.

## Private Beta support queue

The normal Settings page exposes Help and feedback support. Authenticated users can submit `bug`, `question`, `feedback`, `data_quality`, `privacy`, or `security` tickets, view their own ticket status, resolution and assigned owner, and add follow-up information. Secret-shaped context keys or text such as API keys, passwords and Authorization headers are rejected. Security reports are always upgraded to urgent.

Every ticket creates both a tenant-owned `OperationalEvent` and a linked `WorkflowReviewTask` with a priority-specific due time. This makes the issue visible in the unified review queue instead of leaving it as an untracked log entry. Valid states are `open → triaged → in_progress/waiting_user → resolved → closed`; invalid transitions fail closed, and resolved/closed states require a resolution summary. A user reply to `waiting_user` returns the ticket to triage and reopens its task.

Support operators require `events:write`. The operator queue and transitions use an explicit, narrow tenant-scope bypass only after permission verification, allowing an authorized operator to support multiple Beta tenants without weakening ordinary user isolation. User list/detail/reply endpoints always remain tenant-scoped. Audit entries contain category, priority, transition and assignment metadata; user descriptions stay in the ticket rather than being copied into audit logs.

Before invitations, submit one non-sensitive test issue and move it through resolution. This proves the workflow only; real response-time and resolution-quality evidence must come from actual Beta users.

The operator metrics endpoint measures first-response time, resolution time, initial-response SLA rate, currently overdue tickets, and reopened tickets from the immutable ticket history plus task due time. It reports workflow metrics for all tickets, but `real_support_quality_evidence` becomes true only for active, non-test identities authenticated through a non-local HTTPS OIDC provider in staging or production. Local/default/demo/test/E2E tickets remain useful rehearsals and are explicitly excluded from real support-quality evidence.

## Private Beta cohort and behavior metrics

The normal Settings page defines the first ICP as a self-directed, thesis-driven investor who holds both US equities/ETFs and crypto. The user can self-attest the four ICP criteria, private-Beta consent and risk-disclosure acknowledgement. This record qualifies the intended audience only and is explicitly excluded from activation and retention metrics.

Private-Beta consent is versioned. Saving an affirmative profile must include the exact current Beta terms version, privacy-policy version and `ACCEPT_PRIVATE_BETA_TERMS` action. The record stores accepted and withdrawn timestamps, never treats consent as usage, and drops out of the qualified metric denominator automatically when either policy version changes. Users can withdraw consent in normal Settings; rejoining requires accepting the then-current versions again. The current privacy text remains a private-Beta candidate and still requires qualified legal review before public launch.

When both `MANAGED_AUTH_REQUIRED=true` and `MANAGED_AUTH_INVITATION_REQUIRED=true`, first-run initialization also enforces this consent record and ICP qualification server-side. The first-run dialog exposes the same versioned qualification card and keeps initialization disabled until the current record is ready. Local self-use deployments are not forced into private-Beta enrollment. Withdrawing consent after onboarding immediately blocks subsequent product API access for an invited managed-auth viewer. The consent profile, invitation claim, local-start status, privacy export/deletion, the viewer's support tickets, and logout remain available as recovery/exit routes. Re-accepting the current versions while meeting the ICP restores access on the next request. Staff roles bypass this participant gate. Withdrawal does not silently delete data, which remains governed by the separate privacy deletion workflow.

Authorized operators can read `/production/beta-analytics`. Metrics are derived from persisted product behavior rather than manually submitted `activation.*` events:

- activation: first `daily_close_record` after the user's first qualified timestamp;
- first-day loop: that close occurs within 24 hours;
- D7 retention: at least one daily open/close on days 7–13;
- four-week retention: at least one daily open/close in each of four consecutive seven-day windows;
- weekly frequency: distinct active days divided by observed weeks, capped at four;
- Thesis coverage: distinct held assets with an active Thesis divided by distinct held assets;
- review completion: daily closes divided by daily opens, capped at 100%.

The report returns only hashed user references. A verified report requires staging or production, managed auth, a non-local HTTPS OIDC issuer, non-test identities, and at least five identity-verified users observed and active across all four weeks. `default-user`, demo/test/sample/E2E identities, registered users without behavior, manual activation events and users observed for fewer than 28 days never satisfy the four-week gate. Local reports must remain `insufficient_real_beta_evidence` even if synthetic fixtures reproduce the calculation.

## External webhook alert delivery

Managed staging/production requires `EXTERNAL_NOTIFICATION_DELIVERY_ENABLED=true`, `ERROR_REPORTING_ENABLED=true`, and an exact comma-separated `NOTIFICATION_WEBHOOK_ALLOWED_HOSTS` allowlist. Only credential-free HTTPS endpoints on that allowlist are accepted; redirects, localhost, private/reserved IP literals, URL userinfo and header injection are rejected.

Store the webhook endpoint in a supported Secret Manager, never in LocalUserConfig or the database. The resolved secret can be either an HTTPS URL or JSON:

```json
{
  "url": "https://alerts.example.invalid/hooks/ai-trading-os",
  "authorization": "Bearer provider-token"
}
```

In the formal maintenance settings page:

1. Enter only the typed reference, such as `aws-sm://atos/alert-webhook` or `vault://secret/atos#webhook`.
2. Explicitly consent to real redacted operations-alert delivery.
3. Select “Verify reference and enable webhook”; this resolves the secret and records only verification metadata.
4. Select “Send real webhook test”. A 2xx response creates a delivered OperationalEvent; URL, token and request body are never persisted.
5. Confirm the responsible human actually received the test. API evidence alone is not accepted as proof of human receipt.

For a release-bound staging acceptance, provide a managed operator session through the environment and run the dedicated verifier:

```bash
ATOS_SESSION_TOKEN='injected-by-operator-shell' \
./scripts/staging_monitoring_acceptance.py \
  --api-base-url https://staging.example.invalid \
  --environment staging \
  --expected-release-id release-20260717-001 \
  --execute
```

Set `STAGING_FAULT_INJECTION_ENABLED=true` only for the isolated staging maintenance window. The production Compose overlay hard-locks it to `false`, the release validator rejects a production value of `true`, and the endpoint itself additionally requires exact `staging` / `managed-staging` runtime identity plus owner/admin permission. Disabled, local and production runtimes return 404.

The verifier refuses localhost, non-HTTPS and credential-bearing URLs. It first binds the test to the exact ready release and sends one real webhook test. It then requires a pre-drill SLO state of `ok` or `insufficient_data`, generates 100 controlled HTTP 503 responses by default, and evaluates the real Redis request metrics. Acceptance requires a newly created SLO breach event, sufficient real samples, an additional real external notification, and a second persisted delivery-count increase. Finally it requires the server-side `monitoring` stability check to be `ok` while execution remains disabled. Use `--fault-count` only when the staging SLO sample threshold is deliberately configured differently; accepted values are 1–110 and the resulting metrics must still independently prove a breach.

Run this only after the authenticated API rate-limit window is clear, because the default 100 failures plus verification calls approach the default 120-request limit. The injected 503s and open SLO event are intentionally real staging telemetry. After the responsible operator confirms receipt, disable `STAGING_FAULT_INJECTION_ENABLED`, generate healthy staging traffic, and rerun `/ops/observability/evaluate` until the event is resolved by genuine recovered metrics. Never delete or relabel the drill telemetry to manufacture recovery.

The mode-0600 evidence stores only event fingerprints and aggregate counts; it never stores the managed session token, webhook reference, endpoint or authorization value. A dry run explicitly records that no external message was sent.

This evidence proves application-to-provider delivery and server persistence. The named responsible operator must still confirm receipt in the external channel; the script does not infer human receipt from HTTP 2xx.

SLO breach evaluation automatically invokes the webhook. Failed sends create critical delivery events, retry on later scheduler evaluations with a bounded attempt count, and remain fail-closed. A later successful attempt resolves prior delivery failures. Duplicate scheduler evaluations do not resend an alert already marked delivered.

The outbound payload contains only service name, event/severity/status, internal alert event ID, aggregate SLO metrics and explicit `contains_customer_data=false` / `execution_available=false` flags. It excludes user IDs, holdings, account data, request paths, query strings, headers, bodies and credentials.

## Controlled Pilot

Each of `legal`, `limits`, `monitoring`, `rollback`, `kill_switch`, `allowlist`, and `operations` requires an artifact reference, named human reviewer, and verification timestamp. Passing all evidence gates only unlocks a separate human small-pilot review. It never enables production execution automatically.

## Managed AI evaluation pricing

Managed Compose forwards the external-provider references, exact model
allowlist and optional versioned pricing variables. External calls remain
disabled by default. Configure `AI_PRICING_VERSION` and both provider token
rates together; blank or incomplete rates leave cost unknown instead of using
an embedded vendor price.
