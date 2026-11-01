# IBKR Client Portal Read-only Private Verify Runbook

Last updated: 2026-07-17

This runbook verifies one real IBKR stock account through Client Portal Gateway without calling order, trade, transfer, or withdrawal endpoints. Passing local tests or using a recorded sample payload is not real evidence.

## Safety boundary

The adapter allowlist contains only these GET paths:

- `/portfolio/accounts`
- `/portfolio/{accountId}/positions/{pageId}`
- `/portfolio/{accountId}/ledger`

It exposes no quote, candle, order-placement, cancellation, transfer, withdrawal, or signing method. Every imported account keeps live trading disabled and every evidence packet records `execution_available=false`.

## Preconditions

1. Run IBKR Client Portal Gateway in the user's private environment and complete its interactive login.
2. Configure an `ibkr_readonly` connection from the normal Data Sources interface:
   - `gateway_host` and `gateway_port` point to the Gateway;
   - optional `account_id` selects one account visible to that session;
   - `credentials_ref` is a reference/marker only and never contains a cookie or password;
   - insecure TLS is accepted only for a loopback Gateway.
3. Capture and redact two proof files outside the repository:
   - active Gateway session/account access;
   - a read-only boundary review showing that the application uses only the three GET endpoint families above.
4. Remove account number, login name, email, phone, session cookie and other identifiers from the images/PDF before use. The CLI hashes files but cannot judge whether pixels were properly redacted; a human must review them.

## Validate inputs without calling IBKR

```bash
./scripts/private_verify_ibkr.py \
  --user-id '<current application user>' \
  --gateway-session-proof /private/path/gateway-session-redacted.png \
  --read-only-boundary-proof /private/path/read-only-boundary-redacted.pdf
```

The default is dry-run. It validates the target and proof files and writes mode-0600 evidence with file hashes, explicitly recording that no Gateway call occurred.

## Execute real verification

```bash
ATOS_SESSION_TOKEN='optional-managed-app-session-from-shell' \
./scripts/private_verify_ibkr.py \
  --api-base-url http://127.0.0.1:8000 \
  --user-id '<current application user>' \
  --gateway-session-proof /private/path/gateway-session-redacted.png \
  --read-only-boundary-proof /private/path/read-only-boundary-redacted.pdf \
  --execute
```

Loopback HTTP is allowed only for the private local application; remote targets must use credential-free HTTPS. The managed application session is read from `ATOS_SESSION_TOKEN` and never written to disk.

The verification succeeds only when the live application reports all of the following from a new authenticated sync:

- account Snapshot recorded;
- quality score at least 0.8 and Quality Report recorded;
- Catalog lineage recorded;
- ledger sync recorded;
- reconciliation status `ok` with a persisted run;
- zero orders observed and the exact read-endpoint allowlist retained;
- audit evidence artifact recorded;
- execution and production capability both false.

The local evidence file contains hashes of user/resource identifiers and proof files, plus aggregate position/balance counts and quality/reconciliation status. It excludes the raw provider response, account ID, session token, credentials, proof paths, Gateway cookie and full application resource IDs.

## Failure handling

- Any unavailable/expired Gateway session, unexpected payload, incomplete quality, reconciliation break, nonzero order evidence, missing proof or changed endpoint contract fails closed.
- Do not relabel dry-run, fixture, sample payload, Paper account metadata, or screenshots alone as a verified real account.
- Reauthenticate the Gateway or repair data mapping, then run a new verification; never edit a failed evidence file into a passing one.
- Passing this check proves a read-only stock-account data source only. It does not authorize G7 broker Sandbox orders or G8 live trading.
