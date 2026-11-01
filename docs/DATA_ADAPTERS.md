# Data Adapters

## Adapter types

- Market data (bars, ticks)
- Fundamentals
- Corporate actions
- News/sentiment
- On-chain data (phase 09+)
- Broker account read-only data
- CEX account read-only data
- Wallet public-address read-only data
- Custom HTTP read-only data

## Normalization

Adapters should output normalized records with:

- source
- symbol / instrument id
- timestamp (UTC recommended)
- data freshness metadata

## V4 Data Contract

Every market, account, wallet, research, or signal input that can influence a trading workflow must include:

- `source`
- `source_timestamp`
- `ingested_at`
- `latency_ms`
- `is_realtime`
- `is_delayed`
- `confidence`
- `can_be_used_for_trading`
- `data_quality_status`
- `raw_payload_hash`
- `data_snapshot_id`

Data quality statuses:

- `VALID`
- `INCOMPLETE`
- `FAILED`
- `UNKNOWN`
- `STALE` and `UNTRUSTED` remain reserved for later freshness and trust-policy enforcement.

Rules:

- AI reports cannot use account or market data without source, timestamp, and `data_snapshot_id`.
- Order drafts cannot be created from stale, incomplete, untrusted, failed, or unknown-quality trading data.
- If data quality is unknown, downstream trading workflow fails closed.

## Read-only First

Early adapters are read-only. They may import quotes, candles, balances, positions, and risk observations, but they must not route orders, sign wallet transactions, create DEX swaps, or handle withdrawal-enabled credentials.

## Read-only Account Onboarding Safe Slice

`POST /data-sources/connections/read-only-setup` configures IBKR, Futu, CEX, and Wallet account sources without storing secrets:

- `credentials_ref` may point to `env:`, `secretref:`, `vault:`, `keychain:`, or `local-secret:` storage.
- Inline-looking secret values are rejected.
- `config_json` must contain only non-sensitive adapter settings.
- The stored connection contract keeps `execution_available=false`, `order_routing_available=false`, `withdrawals_allowed=false`, and `signing_available=false`.
- `POST /data-sources/connections/{connection_id}/read-only-preflight` validates the setup before account sync. It reports missing metadata, unsafe flags, and provider-specific next actions while writing an audit log.
- Provider preflight requirements are intentionally minimal and metadata-only: IBKR needs `gateway_host` and `gateway_port`; Futu needs `host` and `port`; CEX needs `exchange`; Wallet needs `public_address`.
- `binance_spot_readonly` and `ibkr_readonly` have authenticated read-only sync paths. Each successful sync creates a `DataSnapshot`, `DataQualityReport`, `DataCatalogEntry`, ledger sync, reconciliation run, and audit chain while keeping execution disabled.
- `futu_readonly`, generic `cex_readonly`, and non-address wallet onboarding remain sample/typed contracts unless their provider-specific authenticated adapter is explicitly implemented. They must continue to display as unverified and fail closed without a sample snapshot.
- IBKR private verification is documented in `IBKR_CLIENT_PORTAL_READONLY_PRIVATE_VERIFY_RUNBOOK.md`; local fixtures and dry runs do not count as a real stock-account source.

## CSV Import Safe Slice

Manual CSV import is available for local onboarding and data recovery:

- `POST /imports/csv` supports `holdings`, `crypto_holdings`, `wallet_balances`, and `trades`.
- Holdings-style imports may upsert read-only local positions and create a portfolio snapshot.
- Trade-history imports create a snapshot and data-quality report only; they do not yet write normalized transaction records.
- Secret-like CSV columns such as API keys, passwords, tokens, seed phrases, or private keys are rejected.
- Imported assets are created with `tradable=false`, `manual_enabled=false`, and `auto_enabled=false`.

## Data Catalog Safe Slice

Every quote, candle, read-only account, and CSV import now writes a `DataCatalogEntry`:

- `GET /data-catalog/entries` lists datasets with source, row count, quality status, lineage, and contract metadata.
- `GET /data-catalog/overview` summarizes total datasets, trading-decision-usable datasets, blockers, and recent entries.
- Quote and candle datasets can become trading-decision-usable only when their quality score is complete.
- CSV and read-only account datasets default to review-only until reconciliation and stricter contract checks exist.

`GET /data-sources/freshness` summarizes freshness across cataloged datasets and expected core datasets. It reports `fresh`, `stale`, `missing`, or `blocked` plus the next read-only remediation action.
