# Stage 4 Frontend Real Workflow

This stage surfaces the Stage 1-3 safe workflow in the UI.

## Scope

- Data Sources panel now shows a Research Data Trust report from `/data-catalog/trust-report`.
- Data Sources account connections now expose read-only account preflight actions from `/data-sources/connections/{connection_id}/read-only-preflight`.
- Settings ledger area now loads `/ledger/preflight`.
- Ledger sync and reconciliation UI now shows `data_trust_status` and preflight checks.

## Verified UI Flow

1. Open Data Sources.
2. Review freshness and Research Data Trust.
3. Run account preflight for read-only broker/exchange/wallet connections.
4. Open Settings.
5. Review Ledger Preflight, data trust, source availability, latest reconciliation, and safety boundary.
6. Run ledger sync/reconcile while keeping execution unavailable.

## Safety Boundary

- The UI only calls read-only preflight, data trust, account sample sync, ledger sync, and reconciliation endpoints.
- It does not expose broker order routing, live execution, wallet signing, DEX swap, or withdrawal controls.
- Trust and ledger warnings remain visible instead of being hidden behind success states.

## Verification

- Frontend typecheck passed.
- Browser verification passed on `http://127.0.0.1:3000` for Data Sources and Settings.
- Browser console had no warnings or errors during verification.
- Full regression passed after the UI change.
