# Stage 1 Read-only Auth Preflight

This stage turns the broker, exchange, and wallet account placeholders into an explicit safe onboarding gate.

## Scope

- Added `POST /data-sources/connections/{connection_id}/read-only-preflight`.
- The preflight is available only for `ibkr_readonly`, `futu_readonly`, `cex_readonly`, and `wallet_readonly`.
- It returns `blocked`, `ready_for_sample_sync`, or `sample_sync_available`.
- It lists missing requirements, blocking reasons, safety checks, next actions, and adapter metadata.
- It writes `data_source_connection.readonly_preflight_checked` audit logs.

## Provider Requirements

| Provider | Required metadata | Credentials |
| --- | --- | --- |
| `ibkr_readonly` | `gateway_host`, `gateway_port` | `credentials_ref` required |
| `futu_readonly` | `host`, `port` | `credentials_ref` required |
| `cex_readonly` | `exchange` | `credentials_ref` required |
| `wallet_readonly` | `public_address` | no credential required |

## Fail-closed Rules

- Inline secrets are rejected in `config_json`.
- Inline-looking credentials are rejected in `credentials_ref`.
- The following config flags block preflight when set to `true`: `execution_available`, `order_routing_available`, `withdrawals_allowed`, `signing_available`, `trading_enabled`, `live_trading_enabled`, `auto_execute_enabled`, and `dex_swap_enabled`.
- The response always reports execution, order routing, withdrawals, and signing as unavailable.
- A ready preflight only means the connection can run a sample read-only account sync; it does not enable live broker calls or execution.

## Remaining Work

- Real authenticated read-only adapter calls remain a later stage.
- Secret material is still never stored in this app; only metadata references are accepted.
- Scheduled read-only refresh should be enabled only after sample sync quality and ledger reconciliation are proven.
