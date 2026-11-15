# Strategy workbench increment — 2026-11-15

Implemented: JSON strategy templates and model generation entry, editor validation, SMA/RSI long-only historical simulation, CSV import, data-backed representative-symbol scanning, result/script JSON export, and workbench styling. The terminal launcher starts the local API before opening the frontend. Investment constitution changes add guided sections and local draft autosave.

Backtests use closed candles, next-bar opening fills, configurable fees/slippage, marked-to-market final holdings, and trade/equity outputs. Only the version-1 SMA/RSI JSON schema is supported; legacy arbitrary scripts are not executable. Online data availability and sample length depend on the source. CSV inputs are user-provided, not independently verified market evidence.

Validation: 4 strategy-engine tests; 2 constitution backend tests; constitution UI persistence/publish test using a mocked endpoint; undeclared-identifier check; terminal build. Real model generation and the full browser workflow remain unverified. The attempted Binance historical-data check timed out. This increment is not full strategy-module acceptance or live-trading enablement.
