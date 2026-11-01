# Stage 2 Data Trust Layer

This stage adds a shared trust report for downstream research, order-draft, ledger, and daily-review workflows.

## Scope

- Added `GET /data-catalog/trust-report`.
- Supported scopes: `research`, `order_draft`, `ledger`, and `daily_review`.
- The report evaluates the latest `DataCatalogEntry` per required dataset.
- Each item includes freshness age, quality status, quality score, blockers, and recommended actions.
- The report returns `trusted`, `review_only`, or `blocked`.

## Scope Requirements

| Scope | Required datasets | Trading-usable required |
| --- | --- | --- |
| `research` | `market_quotes`, `market_candles` | yes |
| `order_draft` | `market_quotes`, `market_candles`, `read_only_account` | market data only |
| `ledger` | `read_only_account` | no |
| `daily_review` | `market_quotes`, `read_only_account` | no |

## Trust Rules

- Missing required datasets block the scope.
- Missing linked snapshot or quality report makes the dataset invalid.
- Non-`VALID` quality blocks trust.
- Stale data blocks trust using the same freshness windows as the data source layer.
- Review-only datasets remain usable only for review and ledger context.
- Execution remains unavailable; trust reports do not approve orders, route trades, sign wallet transactions, or enable withdrawals.

## Remaining Work

- Wire the trust report into decision gates and UI panels.
- Add strict reconciliation-based promotion rules for read-only account datasets.
- Add version/hash provenance for raw payloads before any higher-stakes automation.
