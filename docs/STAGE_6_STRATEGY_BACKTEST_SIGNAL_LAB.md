# Stage 6 Strategy Backtest Signal Lab

This stage turns the strategy/backtest/signal lab into a usable read-only experiment loop.

## Scope

- Signal generation already supports request candles or stored candles for RSI, MA cross, volume anomaly, and volatility spike.
- Signal review queue remains available for human review before any guarded draft workflow.
- Backtest runs now fail closed when required local data is missing, and complete a deterministic MA-cross simulation when enough stored candles exist.
- Backtest results include data contract metadata, strategy parameters, simulated trades, equity curve, and metrics.

## Backtest Contract

`POST /backtest-runs/{run_id}/start` only completes when:

- `parameters_json.asset_id` is present.
- `parameters_json.timeframe` points to stored local candles.
- The selected date range has enough candles for `short_window` and `long_window`.
- The strategy playbook is active.
- Moving-average windows are valid.

Otherwise the run is marked `blocked` with `blocking_reasons` and `next_actions`.

## Safety Boundary

- Backtests never create `OrderIntent`, `OrderDraft`, paper execution, live execution, or broker calls.
- Backtest results always include `execution_available=false`, `real_orders_created=0`, and `paper_orders_created=0`.
- Simulated trades live only inside `BacktestRun.results_json`.
- Signal-to-order-intent conversion still requires explicit user enablement and permitted automation level.

## Verification

- Focused backend tests cover completed local-candle simulation, insufficient-data blocking, strategy-rule metadata routes, and signal review queue behavior.
