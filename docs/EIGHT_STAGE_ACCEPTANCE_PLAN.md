# Eight-Stage Production Acceptance

The product uses one evidence-backed acceptance ledger at `GET /production/acceptance`.
Progress is computed from persisted system state. Supplemental evidence cannot override a
missing connection, run, reconciliation, restore drill, or pilot gate.

1. Real Binance read-only verification: private authenticated snapshot, quality report,
   redacted permission screenshot, withdrawal-disabled proof, and audit packet.
2. Research evidence: allowlisted external model, secret reference, structured output,
   versioned eval cases, and persisted eval results.
3. Auth and secrets: managed OIDC, signed revocable sessions, RBAC, user isolation,
   verified secret references, and rotation evidence.
4. Production operations: monitoring, SLO targets, backup, and successful restore drill.
5. Commercial loop: invitation, activation, pricing configuration, and permissioned data room.
6. Broker sandbox: sandbox-only adapter, approved draft, idempotency, lifecycle audit,
   and broker-to-ledger reconciliation.
7. Controlled Pilot: legal, limits, monitoring, rollback, kill switch, allowlist, and
   operations evidence. Passing only permits a separate human review.
8. Release quality: Chromium, Firefox, WebKit, mobile, failure paths, accessibility,
   visual regression, and dependency security evidence.

## Evidence recording

`POST /production/acceptance/evidence/{stage_key}` requires `artifact_ref`, `reviewer`, and
`verified_at`. References must be redacted and must never contain credentials. CI evidence for
stage 8 may additionally record `cross_browser_verified`, `failure_paths_verified`,
`accessibility_verified`, and `visual_regression_verified`.

Run `scripts/production_acceptance.py` in the private environment to save a mode-0600 report.
The command exits with status 2 until every stage permits human small-pilot review.

Automated live trading, wallet signing, withdrawals, DEX swaps, automated approval, and gate
bypass remain prohibited regardless of acceptance percentage.
