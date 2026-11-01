# Binance Spot Read-only Private Verify Runbook

Last updated: 2026-06-19

This runbook defines the private verification path for `binance_spot_readonly`. It must be run only in a private environment with a real read-only Binance Spot API key. Do not paste API keys or secrets into the UI, logs, docs, git, screenshots, or evidence packets.

## Objective

Prove that the Binance Spot adapter can perform authenticated read-only account sync without exposing trading, withdrawal, wallet signing, DEX swap, auto-approval, or gate-bypass capability.

The verification output is an evidence packet containing:

- Account snapshot metadata and redacted balances.
- Data quality report.
- Withdrawal-disabled proof.
- Permission screenshot reference.
- Adapter audit packet.
- Blockers and next actions.

## Preconditions

- Binance API key is created with Spot/account read permission only.
- Trading permission is disabled.
- Withdrawal permission is disabled.
- Universal transfer, margin, futures, and wallet withdrawal capabilities are disabled unless explicitly needed for a separate read-only adapter.
- IP allowlist is enabled when possible.
- Secret is stored in a local or hosted secret manager.
- The application receives only a secret reference, for example `env:BINANCE_SPOT_READONLY_JSON` or `secret://trading/binance_spot_readonly`.
- The secret value is a JSON object with `api_key` and `api_secret`.

## Permission Screenshot Proof

Capture screenshots outside the repository and store only redacted artifact references in the evidence packet.

Required screenshots:

- API key overview showing the key label and read-only/account scope.
- Trading permission disabled.
- Withdrawal permission disabled.
- IP restriction or allowlist configuration.
- Creation or last edited timestamp if visible.

Do not include full API key, secret, UID, phone, email, or account identifiers. Redact before attaching to any packet.

## Private Verify Steps

1. Create or confirm the data source connection:

   - Provider: `binance_spot_readonly`
   - Mode: read-only
   - Credentials: secret reference only
   - Account label: non-sensitive alias such as `binance-main-readonly`

2. Run read-only preflight.

   Expected result:

   - `has_credentials_ref=true`
   - `authenticated_sync_available=true`
   - no missing read-only requirements
   - no trading, withdrawal, or signing capability reported

3. Run private verify.

   Expected result:

   - adapter calls only Binance Spot account/balance read endpoints
   - account snapshot is produced
   - quality report is produced
   - audit packet is produced
   - withdrawal-disabled proof is attached or referenced

4. Save evidence packet.

   The packet may include:

   - `provider`
   - `connection_id`
   - `snapshot_id`
   - `quality_report_id`
   - `audit_packet_id`
   - `permission_screenshot_refs`
   - `withdrawal_disabled_proof`
   - `created_at`
   - `verified_by`
   - `blockers`
   - `next_actions`

   The packet must not include:

   - raw API key
   - API secret
   - full account identifiers
   - unredacted screenshots
   - withdrawal address lists

## Audit Checklist

- Adapter exposes no order placement method.
- Adapter exposes no withdrawal method.
- Adapter exposes no transfer method.
- Adapter uses signed read-only account endpoints only.
- Request logs redact signatures and credentials.
- Response logs redact sensitive identifiers.
- Snapshot data is marked `raw` until quality report passes.
- Quality report must pass before data promotion from `raw` to `reviewed`.
- Human review is required before any data promotion to `trusted`.
- Evidence packet can be downloaded by an authorized admin.

## Failure Handling

If any check fails:

- Mark the evidence packet as blocked.
- Do not promote data beyond `raw`.
- Do not enable pilot gates.
- Rotate the API key if a secret was exposed.
- Attach only redacted failure details.
- Open a repair or security review task.

## Continued Prohibitions

This verification does not authorize live trading. The following remain prohibited:

- automatic live execution
- wallet signing
- withdrawal
- DEX swap
- automatic approval
- bypassing legal, ops, allowlist, limits, monitoring, rollback, or kill switch gates
