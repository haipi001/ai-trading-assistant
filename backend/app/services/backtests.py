from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import BacktestRun
from app.models import Candle
from app.models import StrategyPlaybook
from app.models import StrategyRule
from app.models.core import utc_now


class BacktestRunError(ValueError):
    pass


class BacktestRunNotFoundError(BacktestRunError):
    pass


class BacktestRunsService:
    def __init__(self, db: Session):
        self.db = db

    def list_runs(self, limit: int = 100) -> list[BacktestRun]:
        return list(
            self.db.scalars(
                select(BacktestRun).order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc()).limit(limit)
            ).all()
        )

    def get_run(self, run_id: str) -> BacktestRun:
        run = self.db.get(BacktestRun, run_id)
        if run is None:
            raise BacktestRunNotFoundError("backtest run not found")
        return run

    def create_run(self, payload: dict[str, Any]) -> BacktestRun:
        self._require_playbook(payload["strategy_playbook_id"])
        run = BacktestRun(
            **payload,
            status="pending",
            results_json={
                "execution_available": False,
                "engine_status": "not_started",
                "real_orders_created": 0,
            },
        )
        self.db.add(run)
        self.db.flush()
        self._write_audit_log(
            action="backtest_run.created",
            entity_id=run.id,
            payload_json={
                "strategy_playbook_id": run.strategy_playbook_id,
                "status": run.status,
                "execution_available": False,
            },
        )
        self.db.commit()
        self.db.refresh(run)
        return run

    def start_run(self, run_id: str) -> BacktestRun:
        run = self.get_run(run_id)
        now = utc_now()
        run.started_at = run.started_at or now
        playbook = self._require_playbook(run.strategy_playbook_id)
        # Multi-asset portfolio mode: parameters_json.assets is a list of
        # {asset_id, weight}. Each leg runs the same review-only MA-cross
        # engine on its own capital sleeve; results are combined into a
        # portfolio equity curve. Single-asset runs keep the proven path.
        portfolio_legs = _portfolio_legs(run.parameters_json)
        if portfolio_legs is not None:
            blocked_portfolio = self._portfolio_preflight_blockers(run, playbook, portfolio_legs)
            if blocked_portfolio:
                run.completed_at = now
                run.status = "blocked"
                run.results_json = blocked_portfolio
                self.db.flush()
                self._write_audit_log(
                    action="backtest_run.blocked",
                    entity_id=run.id,
                    payload_json={
                        "strategy_playbook_id": run.strategy_playbook_id,
                        "status": run.status,
                        "execution_available": False,
                        "real_orders_created": 0,
                        "portfolio": True,
                        "blocking_reasons": blocked_portfolio["blocking_reasons"],
                    },
                )
                self.db.commit()
                self.db.refresh(run)
                return run
            run.results_json = self._simulate_portfolio(run, playbook, portfolio_legs)
            run.completed_at = now
            run.status = "completed"
            self.db.flush()
            self._write_audit_log(
                action="backtest_run.completed",
                entity_id=run.id,
                payload_json={
                    "strategy_playbook_id": run.strategy_playbook_id,
                    "status": run.status,
                    "execution_available": False,
                    "real_orders_created": 0,
                    "portfolio": True,
                    "simulated_trades_created": run.results_json["simulated_trades_created"],
                },
            )
            self.db.commit()
            self.db.refresh(run)
            return run
        blocked_results = self._preflight_blockers(run, playbook)
        if blocked_results:
            run.completed_at = now
            run.status = "blocked"
            run.results_json = blocked_results
            self.db.flush()
            self._write_audit_log(
                action="backtest_run.blocked",
                entity_id=run.id,
                payload_json={
                    "strategy_playbook_id": run.strategy_playbook_id,
                    "status": run.status,
                    "execution_available": False,
                    "real_orders_created": 0,
                    "blocking_reasons": blocked_results["blocking_reasons"],
                },
            )
            self.db.commit()
            self.db.refresh(run)
            return run

        run.results_json = self._simulate_ma_cross(run, playbook)
        run.completed_at = now
        run.status = "completed"
        self.db.flush()
        self._write_audit_log(
            action="backtest_run.completed",
            entity_id=run.id,
            payload_json={
                "strategy_playbook_id": run.strategy_playbook_id,
                "status": run.status,
                "execution_available": False,
                "real_orders_created": 0,
                "simulated_trades_created": run.results_json["simulated_trades_created"],
            },
        )
        self.db.commit()
        self.db.refresh(run)
        return run

    def promotion_preflight(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        results = dict(run.results_json or {})
        blockers: list[str] = []
        warnings: list[str] = []
        if run.status != "completed" or results.get("engine_status") != "completed":
            blockers.append("backtest_run_not_completed")
        if results.get("execution_available") is not False:
            blockers.append("backtest_results_must_keep_execution_disabled")
        if results.get("real_orders_created") != 0 or results.get("paper_orders_created") != 0:
            blockers.append("backtest_must_not_create_orders")
        data_contract = results.get("data_contract") if isinstance(results.get("data_contract"), dict) else {}
        if data_contract.get("source") != "local_candles":
            blockers.append("unsupported_or_missing_data_contract")
        if int(data_contract.get("candle_count") or 0) < int(data_contract.get("minimum_candles") or 1):
            blockers.append("insufficient_candles_for_promotion")
        metrics = results.get("metrics") if isinstance(results.get("metrics"), dict) else {}
        walk_forward = results.get("walk_forward") if isinstance(results.get("walk_forward"), dict) else {}
        if not metrics:
            blockers.append("metrics_missing")
        if walk_forward.get("enabled") and walk_forward.get("status") != "completed":
            blockers.append("walk_forward_not_completed")
        if not walk_forward.get("enabled"):
            warnings.append("walk_forward_not_requested")
        if int(results.get("simulated_trades_created") or 0) == 0:
            warnings.append("no_simulated_trades_created")
        total_return = float(metrics.get("total_return_pct") or 0)
        max_drawdown = float(metrics.get("max_drawdown_pct") or 0)
        if max_drawdown > 25:
            warnings.append("max_drawdown_above_review_threshold")
        checks = [
            promotion_check("completion", "Completed simulation", "block" if "backtest_run_not_completed" in blockers else "ok", {"run_status": run.status, "engine_status": results.get("engine_status")}),
            promotion_check("data_contract", "Read-only data contract", "block" if any(reason in blockers for reason in ["unsupported_or_missing_data_contract", "insufficient_candles_for_promotion"]) else "ok", data_contract),
            promotion_check("metrics", "Metrics available", "block" if "metrics_missing" in blockers else "warn" if warnings else "ok", metrics),
            promotion_check("walk_forward", "Walk-forward evidence", "block" if "walk_forward_not_completed" in blockers else "warn" if "walk_forward_not_requested" in warnings else "ok", walk_forward),
            promotion_check("safety_boundary", "Promotion safety boundary", "ok", {"order_creation_allowed": False, "execution_available": False}),
        ]
        if blockers:
            status = "blocked"
        elif warnings:
            status = "review_required"
        else:
            status = "eligible_for_research_review"
        response = {
            "backtest_run_id": run.id,
            "strategy_playbook_id": run.strategy_playbook_id,
            "status": status,
            "total_return_pct": total_return,
            "max_drawdown_pct": max_drawdown,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": promotion_next_actions(status),
            "checks": checks,
            "order_creation_allowed": False,
            "paper_order_creation_allowed": False,
            "live_order_creation_allowed": False,
            "execution_available": False,
        }
        self._write_audit_log(
            action="backtest_run.promotion_preflight_checked",
            entity_id=run.id,
            payload_json=response,
        )
        self.db.commit()
        return response

    def research_packet(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        preflight = self.promotion_preflight(run_id)
        results = dict(run.results_json or {})
        data_contract = results.get("data_contract") if isinstance(results.get("data_contract"), dict) else {}
        metrics = results.get("metrics") if isinstance(results.get("metrics"), dict) else {}
        strategy = results.get("strategy") if isinstance(results.get("strategy"), dict) else {}
        walk_forward = results.get("walk_forward") if isinstance(results.get("walk_forward"), dict) else {}
        checks = [
            promotion_check(
                "promotion_preflight",
                "Promotion preflight",
                "block" if preflight["blockers"] else "warn" if preflight["warnings"] else "ok",
                {"status": preflight["status"], "blockers": preflight["blockers"], "warnings": preflight["warnings"]},
            ),
            promotion_check(
                "reproducibility",
                "Reproducibility",
                "ok" if data_contract and run.parameters_json else "block",
                {"parameters_json": run.parameters_json, "data_contract": data_contract},
            ),
            promotion_check(
                "risk_review",
                "Risk review",
                "warn" if float(metrics.get("max_drawdown_pct") or 0) > 10 else "ok",
                {"metrics": metrics, "manual_risk_review_required": True},
            ),
            promotion_check(
                "walk_forward_review",
                "Walk-forward review",
                "ok" if walk_forward.get("status") == "completed" else "warn",
                {"walk_forward": walk_forward, "manual_review_required": True},
            ),
            promotion_check(
                "execution_boundary",
                "Execution boundary",
                "ok",
                {"order_creation_allowed": False, "execution_available": False},
            ),
        ]
        blockers = list(preflight["blockers"])
        if any(check["key"] == "reproducibility" and check["status"] == "block" for check in checks):
            blockers.append("research_packet_reproducibility_missing")
        status = "blocked" if blockers else "ready_for_research_review"
        response = {
            "backtest_run_id": run.id,
            "strategy_playbook_id": run.strategy_playbook_id,
            "packet_status": status,
            "promotion_status": preflight["status"],
            "blockers": blockers,
            "warnings": preflight["warnings"],
            "next_actions": dedupe_list(
                preflight["next_actions"]
                + [
                    "Attach this packet to research review only; do not create paper or live orders from a backtest.",
                    "Compare against benchmark, slippage, and liquidity assumptions before any strategy rule change.",
                ]
            ),
            "data_contract": data_contract,
            "metrics": metrics,
            "strategy": strategy,
            "walk_forward": walk_forward,
            "checks": checks,
            "order_creation_allowed": False,
            "execution_available": False,
        }
        self._write_audit_log(
            action="backtest_run.research_packet_created",
            entity_id=run.id,
            payload_json=response,
        )
        self.db.commit()
        return response

    def _preflight_blockers(self, run: BacktestRun, playbook: StrategyPlaybook) -> dict[str, Any] | None:
        params = run.parameters_json or {}
        asset_id = str(params.get("asset_id") or "").strip()
        timeframe = str(params.get("timeframe") or "1d").strip()
        strategy_dsl = normalize_strategy_dsl(params)
        short_window = int(strategy_dsl["short_window"])
        long_window = int(strategy_dsl["long_window"])
        minimum_candles = max(long_window + 1, 5)
        blockers: list[str] = []
        next_actions: list[str] = []
        candle_count = 0
        if not playbook.is_active:
            blockers.append("strategy_playbook_inactive")
            next_actions.append("Activate or clone the strategy playbook before simulation.")
        if not asset_id:
            blockers.append("missing_asset_id")
            next_actions.append("Set parameters_json.asset_id to a locally stored asset before starting the backtest.")
        if short_window <= 0 or long_window <= 0 or short_window >= long_window:
            blockers.append("invalid_ma_windows")
            next_actions.append("Use positive MA windows with short_window smaller than long_window.")
        if not strategy_dsl["valid"]:
            blockers.extend(strategy_dsl["blockers"])
            next_actions.append("Use the supported read-only DSL: engine=ma_cross with short and long MA windows.")
        if asset_id and timeframe and short_window > 0 and long_window > 0 and short_window < long_window:
            candle_count = len(self._historical_candles(asset_id=asset_id, timeframe=timeframe, run=run))
            if candle_count < minimum_candles:
                blockers.append("insufficient_local_candles")
                next_actions.append("Import or sync enough read-only candles for the requested asset, timeframe, and date range.")
        if not blockers:
            return None
        return {
            "execution_available": False,
            "real_orders_created": 0,
            "paper_orders_created": 0,
            "simulated_trades_created": 0,
            "final_capital": str(run.initial_capital),
            "initial_capital": str(run.initial_capital),
            "engine_status": "blocked",
            "blocking_reasons": blockers,
            "next_actions": next_actions,
            "data_contract": {
                "source": "local_candles",
                "asset_id": asset_id or None,
                "timeframe": timeframe,
                "date_from": run.date_from.isoformat(),
                "date_to": run.date_to.isoformat(),
                "candle_count": candle_count,
                "minimum_candles": minimum_candles,
            },
            "strategy": {
                "playbook_id": playbook.id,
                "playbook_active": playbook.is_active,
                "short_window": short_window,
                "long_window": long_window,
                "dsl": strategy_dsl,
            },
        }

    def _simulate_ma_cross(self, run: BacktestRun, playbook: StrategyPlaybook) -> dict[str, Any]:
        params = run.parameters_json or {}
        asset_id = str(params["asset_id"])
        timeframe = str(params.get("timeframe") or "1d")
        strategy_dsl = normalize_strategy_dsl(params)
        short_window = int(strategy_dsl["short_window"])
        long_window = int(strategy_dsl["long_window"])
        position_pct = float(params.get("position_pct") or 1.0)
        fee_bps = float(params.get("fee_bps") or 0)
        slippage_bps = float(params.get("slippage_bps") or 0)
        max_volume_participation_pct = liquidity_participation(params)
        validate_cost_and_liquidity(fee_bps, slippage_bps, max_volume_participation_pct)
        position_pct = min(max(position_pct, 0.0), 1.0)
        candles = self._historical_candles(asset_id=asset_id, timeframe=timeframe, run=run)
        active_rules = self._active_rules(playbook.id)
        initial_capital = float(run.initial_capital)
        cash = initial_capital
        quantity = 0.0
        entry_price = 0.0
        realized_pnl = 0.0
        trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        liquidity_constrained_fills = 0

        for index, candle in enumerate(candles):
            close = float(candle.close)
            if index >= long_window:
                prior_closes = [float(item.close) for item in candles[:index]]
                short_ma = sum(prior_closes[-short_window:]) / short_window
                long_ma = sum(prior_closes[-long_window:]) / long_window
                fee_rate = fee_bps / 10_000
                slippage_rate = slippage_bps / 10_000
                if short_ma > long_ma and cash > 0:
                    fill_price = close * (1 + slippage_rate)
                    deploy_cash = cash * position_pct
                    desired_quantity = deploy_cash / (fill_price * (1 + fee_rate)) if fill_price else 0
                    quantity_bought = min(desired_quantity, candle_fill_capacity(candle, max_volume_participation_pct))
                    if quantity_bought > 0:
                        gross = quantity_bought * fill_price
                        fee = gross * fee_rate
                        cash -= gross + fee
                        quantity += quantity_bought
                        entry_price = fill_price
                        constrained = quantity_bought + 1e-12 < desired_quantity
                        liquidity_constrained_fills += int(constrained)
                        trades.append(
                            {
                                "timestamp": candle.timestamp.isoformat(),
                                "side": "buy",
                                "price": round(close, 6),
                                "fill_price": round(fill_price, 6),
                                "quantity": round(quantity_bought, 8),
                                "notional": round(deploy_cash, 6),
                                "fee": round(fee, 6),
                                "slippage_cost": round(quantity_bought * (fill_price - close), 6),
                                "requested_quantity": round(desired_quantity, 8),
                                "liquidity_constrained": constrained,
                                "reason": "short_ma_above_long_ma",
                            }
                        )
                elif short_ma < long_ma and quantity > 0:
                    fill_price = close * (1 - slippage_rate)
                    quantity_sold = min(quantity, candle_fill_capacity(candle, max_volume_participation_pct))
                    gross = quantity_sold * fill_price
                    fee = gross * fee_rate
                    net = gross - fee
                    realized_pnl += (fill_price - entry_price) * quantity_sold - fee
                    constrained = quantity_sold + 1e-12 < quantity
                    liquidity_constrained_fills += int(constrained)
                    trades.append(
                        {
                            "timestamp": candle.timestamp.isoformat(),
                            "side": "sell",
                            "price": round(close, 6),
                            "fill_price": round(fill_price, 6),
                            "quantity": round(quantity_sold, 8),
                            "notional": round(gross, 6),
                            "fee": round(fee, 6),
                            "slippage_cost": round(quantity_sold * (close - fill_price), 6),
                            "requested_quantity": round(quantity, 8),
                            "liquidity_constrained": constrained,
                            "reason": "short_ma_below_long_ma",
                        }
                    )
                    cash += net
                    quantity -= quantity_sold
                    if quantity <= 1e-12:
                        quantity = 0.0
                        entry_price = 0.0
            equity = cash + quantity * close
            equity_curve.append(
                {
                    "timestamp": candle.timestamp.isoformat(),
                    "equity": round(equity, 6),
                    "cash": round(cash, 6),
                    "quantity": round(quantity, 8),
                    "close": round(close, 6),
                }
            )

        if candles and quantity > 0:
            close = float(candles[-1].close)
            realized_pnl += (close - entry_price) * quantity
        final_capital = equity_curve[-1]["equity"]
        strategy_return_pct = ((final_capital - initial_capital) / initial_capital) * 100 if initial_capital else 0.0

        # Buy-and-hold benchmark: deploy the full initial capital at the first
        # usable close (after slippage/fee) and hold to the end. Answers "did
        # the strategy beat simply holding the asset?" — the single most honest
        # sanity check on any timing strategy. Review-only; no orders.
        benchmark = None
        if candles:
            entry_close = float(candles[0].close)
            exit_close = float(candles[-1].close)
            if entry_close > 0:
                bh_fill = entry_close * (1 + slippage_bps / 10_000)
                bh_fee = initial_capital * (fee_bps / 10_000)
                desired_bh_quantity = (initial_capital - bh_fee) / bh_fill if bh_fill else 0.0
                bh_quantity = min(desired_bh_quantity, candle_fill_capacity(candles[0], max_volume_participation_pct))
                bh_spent = bh_quantity * bh_fill + (bh_quantity * bh_fill * fee_bps / 10_000)
                bh_final = max(initial_capital - bh_spent, 0) + bh_quantity * exit_close
                bh_return_pct = ((bh_final - initial_capital) / initial_capital) * 100 if initial_capital else 0.0
                benchmark = {
                    "type": "buy_and_hold",
                    "entry_price": round(entry_close, 6),
                    "exit_price": round(exit_close, 6),
                    "final_capital": round(bh_final, 6),
                    "total_return_pct": round(bh_return_pct, 6),
                    "strategy_excess_return_pct": round(strategy_return_pct - bh_return_pct, 6),
                    "strategy_beats_benchmark": bool(final_capital > bh_final),
                    "liquidity_constrained": bh_quantity + 1e-12 < desired_bh_quantity,
                    "note": "Buy-and-hold applies the same fee, slippage, and first-session volume-participation cap. Unfilled capital remains cash; excess return is not risk-adjusted.",
                }
        return {
            "execution_available": False,
            "real_orders_created": 0,
            "paper_orders_created": 0,
            "simulated_trades_created": len(trades),
            "engine_status": "completed",
            "initial_capital": round(initial_capital, 6),
            "final_capital": final_capital,
            "metrics": {
                "total_return_pct": round(strategy_return_pct, 6),
                "max_drawdown_pct": round(max_drawdown_pct([point["equity"] for point in equity_curve]), 6),
                "realized_pnl": round(realized_pnl, 6),
                "trade_count": len(trades),
                "holding_quantity": round(quantity, 8),
                "liquidity_constrained_fills": liquidity_constrained_fills,
            },
            "benchmark": benchmark,
            "data_contract": {
                "source": "local_candles",
                "asset_id": asset_id,
                "timeframe": timeframe,
                "date_from": run.date_from.isoformat(),
                "date_to": run.date_to.isoformat(),
                "candle_count": len(candles),
                "minimum_candles": max(long_window + 1, 5),
            },
            "strategy": {
                "playbook_id": playbook.id,
                "playbook_active": playbook.is_active,
                "active_rule_count": len(active_rules),
                "short_window": short_window,
                "long_window": long_window,
                "position_pct": position_pct,
                "fee_bps": fee_bps,
                "slippage_bps": slippage_bps,
                "max_volume_participation_pct": max_volume_participation_pct,
                "dsl": strategy_dsl,
            },
            "walk_forward": walk_forward_result(
                candles=candles,
                initial_capital=initial_capital,
                params=params,
                strategy_dsl=strategy_dsl,
            ),
            "simulated_trades": trades,
            "equity_curve": equity_curve,
            "blocking_reasons": [],
            "next_actions": ["Review metrics manually before promoting any strategy rule or signal workflow."],
        }

    def _portfolio_preflight_blockers(
        self, run: BacktestRun, playbook: StrategyPlaybook, legs: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        params = run.parameters_json or {}
        timeframe = str(params.get("timeframe") or "1d").strip()
        strategy_dsl = normalize_strategy_dsl(params)
        short_window = int(strategy_dsl["short_window"])
        long_window = int(strategy_dsl["long_window"])
        minimum_candles = max(long_window + 1, 5)
        blockers: list[str] = []
        next_actions: list[str] = []
        leg_reports: list[dict[str, Any]] = []

        if not playbook.is_active:
            blockers.append("strategy_playbook_inactive")
            next_actions.append("Activate or clone the strategy playbook before simulation.")
        if short_window <= 0 or long_window <= 0 or short_window >= long_window:
            blockers.append("invalid_ma_windows")
            next_actions.append("Use positive MA windows with short_window smaller than long_window.")
        if not strategy_dsl["valid"]:
            blockers.extend(strategy_dsl["blockers"])
            next_actions.append("Use the supported read-only DSL: engine=ma_cross with short and long MA windows.")
        if int(params.get("rebalance_every") or 0) < 0:
            blockers.append("invalid_rebalance_every")
            next_actions.append("rebalance_every must be a non-negative integer (0 disables rebalancing).")

        seen: set[str] = set()
        weight_sum = 0.0
        for leg in legs:
            asset_id = leg["asset_id"]
            weight = float(leg["weight"])
            weight_sum += weight
            if asset_id in seen:
                blockers.append("duplicate_portfolio_asset")
                next_actions.append("Each portfolio asset_id must appear once; merge duplicate legs.")
            seen.add(asset_id)
            if weight <= 0:
                blockers.append("non_positive_portfolio_weight")
                next_actions.append("Give every portfolio leg a positive weight.")
            candle_count = 0
            if short_window > 0 and long_window > 0 and short_window < long_window:
                candle_count = len(self._historical_candles(asset_id=asset_id, timeframe=timeframe, run=run))
                if candle_count < minimum_candles:
                    blockers.append("insufficient_local_candles")
                    next_actions.append(
                        f"Import or sync at least {minimum_candles} read-only candles for asset {asset_id} on {timeframe}."
                    )
            leg_reports.append({"asset_id": asset_id, "weight": weight, "candle_count": candle_count})

        if weight_sum <= 0:
            blockers.append("portfolio_weights_sum_not_positive")
            next_actions.append("Portfolio weights must sum to a positive number so they can be normalized.")

        if not blockers:
            return None
        return {
            "execution_available": False,
            "real_orders_created": 0,
            "paper_orders_created": 0,
            "simulated_trades_created": 0,
            "final_capital": str(run.initial_capital),
            "initial_capital": str(run.initial_capital),
            "engine_status": "blocked",
            "mode": "portfolio",
            "blocking_reasons": dedupe_list(blockers),
            "next_actions": dedupe_list(next_actions),
            "data_contract": {
                "source": "local_candles",
                "timeframe": timeframe,
                "date_from": run.date_from.isoformat(),
                "date_to": run.date_to.isoformat(),
                "minimum_candles": minimum_candles,
                "legs": leg_reports,
            },
            "strategy": {
                "playbook_id": playbook.id,
                "playbook_active": playbook.is_active,
                "short_window": short_window,
                "long_window": long_window,
                "dsl": strategy_dsl,
            },
        }

    def _simulate_portfolio(
        self, run: BacktestRun, playbook: StrategyPlaybook, legs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        params = run.parameters_json or {}
        timeframe = str(params.get("timeframe") or "1d")
        strategy_dsl = normalize_strategy_dsl(params)
        short_window = int(strategy_dsl["short_window"])
        long_window = int(strategy_dsl["long_window"])
        fee_bps = float(params.get("fee_bps") or 0)
        slippage_bps = float(params.get("slippage_bps") or 0)
        max_volume_participation_pct = liquidity_participation(params)
        validate_cost_and_liquidity(fee_bps, slippage_bps, max_volume_participation_pct)
        initial_capital = float(run.initial_capital)
        weight_sum = sum(float(leg["weight"]) for leg in legs) or 1.0
        rebalance_every = int(params.get("rebalance_every") or 0)
        if rebalance_every < 0:
            raise BacktestRunError("rebalance_every must be a non-negative integer")

        # Fetch each leg's candles once; both the static and rebalanced paths use them.
        normalized_weights: dict[str, float] = {leg["asset_id"]: float(leg["weight"]) / weight_sum for leg in legs}
        legs_candles: dict[str, list[Candle]] = {
            leg["asset_id"]: self._historical_candles(asset_id=leg["asset_id"], timeframe=timeframe, run=run)
            for leg in legs
        }

        if rebalance_every > 0:
            return self._build_rebalanced_portfolio_result(
                run=run,
                playbook=playbook,
                legs=legs,
                legs_candles=legs_candles,
                weights=normalized_weights,
                strategy_dsl=strategy_dsl,
                short_window=short_window,
                long_window=long_window,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                initial_capital=initial_capital,
                timeframe=timeframe,
                rebalance_every=rebalance_every,
                max_volume_participation_pct=max_volume_participation_pct,
            )

        leg_results: list[dict[str, Any]] = []
        # equity_by_ts[timestamp] accumulates each leg's equity at that point;
        # legs are forward-filled independently so the portfolio curve is
        # defined on the union of all legs' candle timestamps.
        timeline: dict[str, dict[str, float]] = {}
        total_trades = 0
        strategy_final = 0.0
        benchmark_final = 0.0

        for leg in legs:
            asset_id = leg["asset_id"]
            weight = normalized_weights[asset_id]
            leg_capital = initial_capital * weight
            candles = legs_candles[asset_id]
            sim = simulate_ma_cross_leg(
                candles=candles,
                capital=leg_capital,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                short_window=short_window,
                long_window=long_window,
                max_volume_participation_pct=max_volume_participation_pct,
            )
            total_trades += len(sim["trades"])
            strategy_final += sim["final_capital"]
            benchmark_final += sim["benchmark_final_capital"]
            for point in sim["equity_curve"]:
                bucket = timeline.setdefault(point["timestamp"], {})
                bucket[asset_id] = point["equity"]
            leg_results.append(
                {
                    "asset_id": asset_id,
                    "weight": round(weight, 6),
                    "allocated_capital": round(leg_capital, 6),
                    "final_capital": round(sim["final_capital"], 6),
                    "total_return_pct": round(sim["total_return_pct"], 6),
                    "trade_count": len(sim["trades"]),
                    "buy_and_hold_return_pct": round(sim["benchmark_return_pct"], 6),
                    "candle_count": len(candles),
                    "liquidity_constrained_fills": sim["liquidity_constrained_fills"],
                }
            )

        # Build the combined portfolio equity curve, forward-filling each leg's
        # last known equity so an asset with sparser candles still contributes.
        ordered_ts = sorted(timeline.keys())
        last_equity: dict[str, float] = {leg["asset_id"]: initial_capital * (float(leg["weight"]) / weight_sum) for leg in legs}
        portfolio_curve: list[dict[str, Any]] = []
        for ts in ordered_ts:
            for asset_id, equity in timeline[ts].items():
                last_equity[asset_id] = equity
            portfolio_equity = sum(last_equity.values())
            portfolio_curve.append({"timestamp": ts, "equity": round(portfolio_equity, 6)})

        final_capital = round(portfolio_curve[-1]["equity"], 6) if portfolio_curve else round(initial_capital, 6)
        strategy_return_pct = ((final_capital - initial_capital) / initial_capital) * 100 if initial_capital else 0.0
        benchmark_return_pct = ((benchmark_final - initial_capital) / initial_capital) * 100 if initial_capital else 0.0

        benchmark = {
            "type": "buy_and_hold_portfolio",
            "final_capital": round(benchmark_final, 6),
            "total_return_pct": round(benchmark_return_pct, 6),
            "strategy_excess_return_pct": round(strategy_return_pct - benchmark_return_pct, 6),
            "strategy_beats_benchmark": bool(final_capital > benchmark_final),
            "note": "Weighted buy-and-hold of the same legs with identical fee/slippage on entry. Static-weight sleeves; no periodic rebalancing.",
        }
        return {
            "execution_available": False,
            "real_orders_created": 0,
            "paper_orders_created": 0,
            "simulated_trades_created": total_trades,
            "engine_status": "completed",
            "mode": "portfolio",
            "initial_capital": round(initial_capital, 6),
            "final_capital": final_capital,
            "metrics": {
                "total_return_pct": round(strategy_return_pct, 6),
                "max_drawdown_pct": round(max_drawdown_pct([point["equity"] for point in portfolio_curve]), 6),
                "trade_count": total_trades,
                "leg_count": len(legs),
            },
            "benchmark": benchmark,
            "legs": leg_results,
            "data_contract": {
                "source": "local_candles",
                "timeframe": timeframe,
                "date_from": run.date_from.isoformat(),
                "date_to": run.date_to.isoformat(),
                "candle_count": len(ordered_ts),
                "minimum_candles": max(long_window + 1, 5),
                "legs": [{"asset_id": leg["asset_id"], "candle_count": leg["candle_count"]} for leg in leg_results],
            },
            "strategy": {
                "playbook_id": playbook.id,
                "playbook_active": playbook.is_active,
                "short_window": short_window,
                "long_window": long_window,
                "fee_bps": fee_bps,
                "slippage_bps": slippage_bps,
                "max_volume_participation_pct": max_volume_participation_pct,
                "dsl": strategy_dsl,
            },
            "equity_curve": portfolio_curve,
            "walk_forward": portfolio_walk_forward_result(
                legs_candles=legs_candles,
                weights=normalized_weights,
                initial_capital=initial_capital,
                params=params,
                strategy_dsl=strategy_dsl,
            ),
            "blocking_reasons": [],
            "next_actions": ["Review portfolio metrics and per-leg contribution manually before promoting any rule."],
        }

    def _build_rebalanced_portfolio_result(
        self,
        *,
        run: BacktestRun,
        playbook: StrategyPlaybook,
        legs: list[dict[str, Any]],
        legs_candles: dict[str, list[Candle]],
        weights: dict[str, float],
        strategy_dsl: dict[str, Any],
        short_window: int,
        long_window: int,
        fee_bps: float,
        slippage_bps: float,
        initial_capital: float,
        timeframe: str,
        rebalance_every: int,
        max_volume_participation_pct: float | None,
    ) -> dict[str, Any]:
        sim = simulate_portfolio_rebalanced(
            legs_candles=legs_candles,
            weights=weights,
            initial_capital=initial_capital,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            short_window=short_window,
            long_window=long_window,
            rebalance_every=rebalance_every,
            max_volume_participation_pct=max_volume_participation_pct,
        )
        equity_curve = sim["equity_curve"]
        final_capital = round(sim["final_capital"], 6)
        strategy_return_pct = ((final_capital - initial_capital) / initial_capital) * 100 if initial_capital else 0.0

        # Benchmark: weighted buy-and-hold of the same legs (no rebalancing),
        # with identical entry fee/slippage — isolates what the rebalancing
        # strategy added or cost versus simply holding the target weights.
        benchmark_final = 0.0
        for asset_id, weight in weights.items():
            candles = legs_candles.get(asset_id) or []
            leg_capital = initial_capital * weight
            if not candles:
                benchmark_final += leg_capital
                continue
            entry_close = float(candles[0].close)
            exit_close = float(candles[-1].close)
            if entry_close > 0:
                bh_fill = entry_close * (1 + slippage_bps / 10_000)
                bh_fee = leg_capital * (fee_bps / 10_000)
                desired_bh_quantity = (leg_capital - bh_fee) / bh_fill if bh_fill else 0.0
                bh_quantity = min(desired_bh_quantity, candle_fill_capacity(candles[0], max_volume_participation_pct))
                bh_spent = bh_quantity * bh_fill * (1 + fee_bps / 10_000)
                benchmark_final += max(leg_capital - bh_spent, 0) + bh_quantity * exit_close
            else:
                benchmark_final += leg_capital
        benchmark_return_pct = ((benchmark_final - initial_capital) / initial_capital) * 100 if initial_capital else 0.0

        leg_results = [
            {
                "asset_id": leg["asset_id"],
                "weight": round(weights[leg["asset_id"]], 6),
                "target_capital": round(initial_capital * weights[leg["asset_id"]], 6),
                "trade_count": sim["trades_by_asset"].get(leg["asset_id"], 0),
                "candle_count": len(legs_candles.get(leg["asset_id"]) or []),
            }
            for leg in legs
        ]
        return {
            "execution_available": False,
            "real_orders_created": 0,
            "paper_orders_created": 0,
            "simulated_trades_created": sim["total_trades"],
            "engine_status": "completed",
            "mode": "portfolio",
            "initial_capital": round(initial_capital, 6),
            "final_capital": final_capital,
            "metrics": {
                "total_return_pct": round(strategy_return_pct, 6),
                "max_drawdown_pct": round(max_drawdown_pct([point["equity"] for point in equity_curve]), 6),
                "trade_count": sim["total_trades"],
                "leg_count": len(legs),
                "rebalance_events": sim["rebalance_events"],
                "liquidity_constrained_fills": sim["liquidity_constrained_fills"],
            },
            "rebalance": {
                "enabled": True,
                "rebalance_every_candles": rebalance_every,
                "rebalance_events": sim["rebalance_events"],
                "timeline_steps": sim["timeline_steps"],
                "note": "Legs are liquidated to cash at each boundary (with fee/slippage) and redistributed to target weights; trading then resumes on each leg's MA signal.",
            },
            "benchmark": {
                "type": "buy_and_hold_portfolio",
                "final_capital": round(benchmark_final, 6),
                "total_return_pct": round(benchmark_return_pct, 6),
                "strategy_excess_return_pct": round(strategy_return_pct - benchmark_return_pct, 6),
                "strategy_beats_benchmark": bool(final_capital > benchmark_final),
                "note": "Weighted buy-and-hold of the same legs (no rebalancing) with identical entry fee, slippage, and first-session volume-participation cap; unfilled capital remains cash.",
            },
            "legs": leg_results,
            "data_contract": {
                "source": "local_candles",
                "timeframe": timeframe,
                "date_from": run.date_from.isoformat(),
                "date_to": run.date_to.isoformat(),
                "candle_count": sim["timeline_steps"],
                "minimum_candles": max(long_window + 1, 5),
                "legs": [{"asset_id": leg["asset_id"], "candle_count": len(legs_candles.get(leg["asset_id"]) or [])} for leg in legs],
            },
            "strategy": {
                "playbook_id": playbook.id,
                "playbook_active": playbook.is_active,
                "short_window": short_window,
                "long_window": long_window,
                "fee_bps": fee_bps,
                "slippage_bps": slippage_bps,
                "max_volume_participation_pct": max_volume_participation_pct,
                "rebalance_every": rebalance_every,
                "dsl": strategy_dsl,
            },
            "equity_curve": equity_curve,
            "walk_forward": {
                "enabled": bool(((run.parameters_json or {}).get("walk_forward") or {}).get("enabled")),
                "status": "blocked" if bool(((run.parameters_json or {}).get("walk_forward") or {}).get("enabled")) else "not_requested",
                "blocking_reasons": ["rebalanced_portfolio_walk_forward_not_supported"] if bool(((run.parameters_json or {}).get("walk_forward") or {}).get("enabled")) else [],
                "summary": {},
                "order_creation_allowed": False,
                "execution_available": False,
            },
            "blocking_reasons": [],
            "next_actions": ["Review rebalanced portfolio metrics and turnover manually before promoting any rule."],
        }

    def _historical_candles(self, *, asset_id: str, timeframe: str, run: BacktestRun) -> list[Candle]:
        candles = list(
            self.db.scalars(
                select(Candle)
                .where(Candle.asset_id == asset_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.asc(), Candle.id.asc())
            ).all()
        )
        return [candle for candle in candles if run.date_from <= candle.timestamp.date() <= run.date_to]

    def _active_rules(self, strategy_playbook_id: str) -> list[StrategyRule]:
        return list(
            self.db.scalars(
                select(StrategyRule)
                .where(StrategyRule.strategy_playbook_id == strategy_playbook_id, StrategyRule.is_active.is_(True))
                .order_by(StrategyRule.priority.asc(), StrategyRule.created_at.desc(), StrategyRule.id.desc())
            ).all()
        )

    def _require_playbook(self, strategy_playbook_id: str) -> StrategyPlaybook:
        playbook = self.db.get(StrategyPlaybook, strategy_playbook_id)
        if playbook is None:
            raise BacktestRunError("strategy playbook not found")
        return playbook

    def _write_audit_log(self, *, action: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="backtest-runs-service",
                action=action,
                entity_type="BacktestRun",
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


def _portfolio_legs(params: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """Return normalized portfolio legs when parameters_json requests a
    multi-asset run, else None (single-asset path). A portfolio needs at
    least two well-formed {asset_id, weight} legs; anything malformed falls
    through to None so preflight/simulation can surface a clean blocker."""
    raw = (params or {}).get("assets")
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    legs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        asset_id = str(item.get("asset_id") or "").strip()
        if not asset_id:
            return None
        try:
            weight = float(item.get("weight") or 0)
        except (TypeError, ValueError):
            return None
        legs.append({"asset_id": asset_id, "weight": weight})
    return legs


def simulate_ma_cross_leg(
    *,
    candles: list[Candle],
    capital: float,
    fee_bps: float,
    slippage_bps: float,
    short_window: int,
    long_window: int,
    max_volume_participation_pct: float | None,
) -> dict[str, Any]:
    """Review-only single-leg MA-cross simulation used by the portfolio
    engine. Deploys the full leg capital on each entry (position_pct=1 per
    sleeve) and returns the equity curve, trades, and a buy-and-hold
    benchmark for this leg. No orders are ever created."""
    cash = capital
    quantity = 0.0
    entry_price = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    fee_rate = fee_bps / 10_000
    slippage_rate = slippage_bps / 10_000
    liquidity_constrained_fills = 0

    for index, candle in enumerate(candles):
        close = float(candle.close)
        if index >= long_window:
            prior_closes = [float(item.close) for item in candles[:index]]
            short_ma = sum(prior_closes[-short_window:]) / short_window
            long_ma = sum(prior_closes[-long_window:]) / long_window
            if short_ma > long_ma and cash > 0:
                fill_price = close * (1 + slippage_rate)
                desired_quantity = cash / (fill_price * (1 + fee_rate)) if fill_price else 0
                quantity_bought = min(desired_quantity, candle_fill_capacity(candle, max_volume_participation_pct))
                if quantity_bought > 0:
                    gross = quantity_bought * fill_price
                    fee = gross * fee_rate
                    constrained = quantity_bought + 1e-12 < desired_quantity
                    liquidity_constrained_fills += int(constrained)
                    trades.append({"timestamp": candle.timestamp.isoformat(), "side": "buy", "price": round(close, 6), "quantity": round(quantity_bought, 8), "requested_quantity": round(desired_quantity, 8), "liquidity_constrained": constrained})
                    quantity += quantity_bought
                    entry_price = fill_price
                    cash -= gross + fee
            elif short_ma < long_ma and quantity > 0:
                fill_price = close * (1 - slippage_rate)
                quantity_sold = min(quantity, candle_fill_capacity(candle, max_volume_participation_pct))
                gross = quantity_sold * fill_price
                fee = gross * fee_rate
                constrained = quantity_sold + 1e-12 < quantity
                liquidity_constrained_fills += int(constrained)
                trades.append({"timestamp": candle.timestamp.isoformat(), "side": "sell", "price": round(close, 6), "quantity": round(quantity_sold, 8), "requested_quantity": round(quantity, 8), "liquidity_constrained": constrained})
                cash += gross - fee
                quantity -= quantity_sold
                if quantity <= 1e-12:
                    quantity = 0.0
                    entry_price = 0.0
        equity = cash + quantity * close
        equity_curve.append({"timestamp": candle.timestamp.isoformat(), "equity": round(equity, 6)})

    final_capital = equity_curve[-1]["equity"] if equity_curve else capital
    total_return_pct = ((final_capital - capital) / capital) * 100 if capital else 0.0

    benchmark_final = capital
    benchmark_return_pct = 0.0
    if candles:
        entry_close = float(candles[0].close)
        exit_close = float(candles[-1].close)
        if entry_close > 0:
            bh_fill = entry_close * (1 + slippage_rate)
            bh_fee = capital * fee_rate
            desired_bh_quantity = (capital - bh_fee) / bh_fill if bh_fill else 0.0
            bh_quantity = min(desired_bh_quantity, candle_fill_capacity(candles[0], max_volume_participation_pct))
            bh_spent = bh_quantity * bh_fill * (1 + fee_rate)
            benchmark_final = max(capital - bh_spent, 0) + bh_quantity * exit_close
            benchmark_return_pct = ((benchmark_final - capital) / capital) * 100 if capital else 0.0
    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "final_capital": final_capital,
        "total_return_pct": total_return_pct,
        "benchmark_final_capital": benchmark_final,
        "benchmark_return_pct": benchmark_return_pct,
        "liquidity_constrained_fills": liquidity_constrained_fills,
    }


def simulate_portfolio_rebalanced(
    *,
    legs_candles: dict[str, list[Candle]],
    weights: dict[str, float],
    initial_capital: float,
    fee_bps: float,
    slippage_bps: float,
    short_window: int,
    long_window: int,
    rebalance_every: int,
    max_volume_participation_pct: float | None,
) -> dict[str, Any]:
    """Lock-step multi-asset MA-cross with periodic rebalancing to target
    weights. Each leg runs its own MA signal (from its full close history) on a
    shared timeline. Every `rebalance_every` timeline steps, all legs are
    liquidated to cash at the current close (paying real fee/slippage) and the
    combined cash is redistributed to the target weights, then trading resumes.
    Review-only: no orders are ever created."""
    fee_rate = fee_bps / 10_000
    slippage_rate = slippage_bps / 10_000
    assets = list(weights.keys())
    state: dict[str, dict[str, Any]] = {
        asset: {"cash": initial_capital * weights[asset], "qty": 0.0, "entry": 0.0, "closes": [], "last_close": None, "trades": 0}
        for asset in assets
    }
    by_ts: dict[str, dict[str, Candle]] = {
        asset: {candle.timestamp.isoformat(): candle for candle in legs_candles.get(asset, [])} for asset in assets
    }
    union_ts = sorted({ts for asset in assets for ts in by_ts[asset]})

    equity_curve: list[dict[str, Any]] = []
    rebalance_events = 0
    liquidity_constrained_fills = 0
    total_steps = len(union_ts)
    for index, ts in enumerate(union_ts):
        for asset in assets:
            candle = by_ts[asset].get(ts)
            if candle is None:
                continue
            st = state[asset]
            close = float(candle.close)
            prior = st["closes"]
            if len(prior) >= long_window:
                short_ma = sum(prior[-short_window:]) / short_window
                long_ma = sum(prior[-long_window:]) / long_window
                if short_ma > long_ma and st["cash"] > 0:
                    fill_price = close * (1 + slippage_rate)
                    desired_quantity = st["cash"] / (fill_price * (1 + fee_rate)) if fill_price else 0
                    quantity_bought = min(desired_quantity, candle_fill_capacity(candle, max_volume_participation_pct))
                    if quantity_bought > 0:
                        gross = quantity_bought * fill_price
                        fee = gross * fee_rate
                        liquidity_constrained_fills += int(quantity_bought + 1e-12 < desired_quantity)
                        st["qty"] += quantity_bought
                        st["entry"] = fill_price
                        st["cash"] -= gross + fee
                        st["trades"] += 1
                elif short_ma < long_ma and st["qty"] > 0:
                    fill_price = close * (1 - slippage_rate)
                    quantity_sold = min(st["qty"], candle_fill_capacity(candle, max_volume_participation_pct))
                    gross = quantity_sold * fill_price
                    fee = gross * fee_rate
                    liquidity_constrained_fills += int(quantity_sold + 1e-12 < st["qty"])
                    st["cash"] += gross - fee
                    st["qty"] -= quantity_sold
                    if st["qty"] <= 1e-12:
                        st["qty"] = 0.0
                        st["entry"] = 0.0
                    st["trades"] += 1
            st["closes"].append(close)
            st["last_close"] = close

        portfolio_equity = 0.0
        for asset in assets:
            st = state[asset]
            last_close = st["last_close"]
            portfolio_equity += st["cash"] + (st["qty"] * last_close if last_close is not None else 0.0)
        equity_curve.append({"timestamp": ts, "equity": round(portfolio_equity, 6)})

        is_boundary = rebalance_every > 0 and (index + 1) % rebalance_every == 0 and index < total_steps - 1
        if is_boundary:
            # Liquidate every leg to cash at the current close (real fee/slippage),
            # then redistribute the combined cash back to target weights.
            for asset in assets:
                st = state[asset]
                last_close = st["last_close"]
                if st["qty"] > 0 and last_close:
                    fill_price = last_close * (1 - slippage_rate)
                    candle = by_ts[asset].get(ts)
                    capacity = candle_fill_capacity(candle, max_volume_participation_pct) if candle is not None else 0.0
                    quantity_sold = min(st["qty"], capacity)
                    gross = quantity_sold * fill_price
                    fee = gross * fee_rate
                    liquidity_constrained_fills += int(quantity_sold + 1e-12 < st["qty"])
                    st["cash"] += gross - fee
                    st["qty"] -= quantity_sold
                    if st["qty"] <= 1e-12:
                        st["qty"] = 0.0
                        st["entry"] = 0.0
                    st["trades"] += 1
            total_cash = sum(state[asset]["cash"] for asset in assets)
            for asset in assets:
                state[asset]["cash"] = total_cash * weights[asset]
            rebalance_events += 1

    final_capital = equity_curve[-1]["equity"] if equity_curve else round(initial_capital, 6)
    return {
        "equity_curve": equity_curve,
        "final_capital": final_capital,
        "total_trades": sum(state[asset]["trades"] for asset in assets),
        "trades_by_asset": {asset: state[asset]["trades"] for asset in assets},
        "rebalance_events": rebalance_events,
        "timeline_steps": total_steps,
        "liquidity_constrained_fills": liquidity_constrained_fills,
    }


def max_drawdown_pct(equity_values: list[float]) -> float:
    if not equity_values:
        return 0
    peak = equity_values[0]
    max_drawdown = 0.0
    for equity in equity_values:
        peak = max(peak, equity)
        if peak:
            max_drawdown = min(max_drawdown, (equity - peak) / peak)
    return abs(max_drawdown) * 100


def validate_cost_and_liquidity(fee_bps: float, slippage_bps: float, max_volume_participation_pct: float | None) -> None:
    if fee_bps < 0 or slippage_bps < 0:
        raise BacktestRunError("fee_bps and slippage_bps must be non-negative")
    if max_volume_participation_pct is not None and (max_volume_participation_pct <= 0 or max_volume_participation_pct > 100):
        raise BacktestRunError("max_volume_participation_pct must be greater than 0 and at most 100")


def liquidity_participation(params: dict[str, Any]) -> float | None:
    raw = params.get("max_volume_participation_pct")
    if raw is None or str(raw).strip() == "":
        return None
    return float(raw)


def candle_fill_capacity(candle: Candle | None, max_volume_participation_pct: float | None) -> float:
    if max_volume_participation_pct is None:
        return float("inf")
    if candle is None:
        return 0.0
    return max(float(candle.volume or 0), 0.0) * max_volume_participation_pct / 100


def normalize_strategy_dsl(params: dict[str, Any]) -> dict[str, Any]:
    dsl = params.get("strategy_dsl")
    blockers: list[str] = []
    warnings: list[str] = []
    if dsl is None:
        short_window = int(params.get("short_window") or 3)
        long_window = int(params.get("long_window") or 5)
        return {
            "version": "local-readonly-v1",
            "engine": "ma_cross",
            "valid": True,
            "source": "legacy_parameters",
            "short_window": short_window,
            "long_window": long_window,
            "entry_rule": "short_ma_above_long_ma",
            "exit_rule": "short_ma_below_long_ma",
            "blockers": [],
            "warnings": [],
            "order_creation_allowed": False,
            "execution_available": False,
        }
    if not isinstance(dsl, dict):
        return {
            "version": "local-readonly-v1",
            "engine": "unsupported",
            "valid": False,
            "source": "strategy_dsl",
            "short_window": int(params.get("short_window") or 3),
            "long_window": int(params.get("long_window") or 5),
            "entry_rule": "short_ma_above_long_ma",
            "exit_rule": "short_ma_below_long_ma",
            "blockers": ["strategy_dsl_must_be_object"],
            "warnings": [],
            "order_creation_allowed": False,
            "execution_available": False,
        }

    engine = str(dsl.get("engine") or "ma_cross")
    version = str(dsl.get("version") or "local-readonly-v1")
    entry = dsl.get("entry") if isinstance(dsl.get("entry"), dict) else {}
    exit_rule = dsl.get("exit") if isinstance(dsl.get("exit"), dict) else {}
    ma_entry = entry.get("short_ma_above_long_ma") if isinstance(entry.get("short_ma_above_long_ma"), dict) else {}
    ma_exit = exit_rule.get("short_ma_below_long_ma") if isinstance(exit_rule.get("short_ma_below_long_ma"), dict) else {}
    short_window = int(ma_entry.get("short_window") or dsl.get("short_window") or params.get("short_window") or 3)
    long_window = int(ma_entry.get("long_window") or dsl.get("long_window") or params.get("long_window") or 5)
    exit_short = int(ma_exit.get("short_window") or short_window)
    exit_long = int(ma_exit.get("long_window") or long_window)
    if engine != "ma_cross":
        blockers.append("unsupported_strategy_engine")
    if version != "local-readonly-v1":
        warnings.append("strategy_dsl_version_not_native")
    if short_window != exit_short or long_window != exit_long:
        warnings.append("entry_exit_windows_normalized_to_entry_rule")
    if short_window <= 0 or long_window <= 0 or short_window >= long_window:
        blockers.append("invalid_ma_windows")
    return {
        "version": version,
        "engine": engine,
        "valid": not blockers,
        "source": "strategy_dsl",
        "short_window": short_window,
        "long_window": long_window,
        "entry_rule": "short_ma_above_long_ma",
        "exit_rule": "short_ma_below_long_ma",
        "blockers": dedupe_list(blockers),
        "warnings": dedupe_list(warnings),
        "order_creation_allowed": False,
        "execution_available": False,
    }


def portfolio_walk_forward_result(
    *,
    legs_candles: dict[str, list[Candle]],
    weights: dict[str, float],
    initial_capital: float,
    params: dict[str, Any],
    strategy_dsl: dict[str, Any],
) -> dict[str, Any]:
    config = params.get("walk_forward") if isinstance(params.get("walk_forward"), dict) else {}
    if not bool(config.get("enabled")):
        return {"enabled": False, "status": "not_requested", "folds": [], "summary": {}, "order_creation_allowed": False, "execution_available": False}
    short_window = int(strategy_dsl["short_window"])
    long_window = int(strategy_dsl["long_window"])
    minimum = max(long_window + 1, 5)
    train_size = max(int(config.get("train_candles") or config.get("fold_size") or minimum), minimum)
    test_size = max(int(config.get("test_candles") or config.get("fold_size") or minimum), minimum)
    step_size = max(int(config.get("step_size") or test_size), 1)
    required = train_size + test_size
    common_length = min((len(candles) for candles in legs_candles.values()), default=0)
    if common_length < required:
        return {"enabled": True, "status": "blocked", "blocking_reasons": ["insufficient_candles_for_portfolio_walk_forward"], "folds": [], "summary": {"minimum_leg_candles": common_length, "required_candles": required}, "order_creation_allowed": False, "execution_available": False}

    folds: list[dict[str, Any]] = []
    for start in range(0, common_length - required + 1, step_size):
        leg_rows: list[dict[str, Any]] = []
        combined_curve = [0.0 for _ in range(test_size)]
        for asset_id, weight in weights.items():
            candles = legs_candles[asset_id][start:start + required]
            result = simulate_ma_cross_on_candles(
                candles=candles,
                initial_capital=initial_capital * weight,
                short_window=short_window,
                long_window=long_window,
                position_pct=1.0,
                fee_bps=float(params.get("fee_bps") or 0),
                slippage_bps=float(params.get("slippage_bps") or 0),
                max_volume_participation_pct=liquidity_participation(params),
                evaluation_start_index=train_size,
            )
            for index, equity in enumerate(result["equity_curve"][:test_size]):
                combined_curve[index] += float(equity)
            leg_rows.append({"asset_id": asset_id, "weight": round(weight, 6), "out_of_sample": {key: result[key] for key in ("total_return_pct", "max_drawdown_pct", "trade_count")}})
        final_capital = combined_curve[-1] if combined_curve else initial_capital
        total_return = ((final_capital - initial_capital) / initial_capital) * 100 if initial_capital else 0.0
        reference = next(iter(legs_candles.values()))[start:start + required]
        folds.append({
            "index": len(folds) + 1,
            "in_sample": {"date_from": reference[0].timestamp.date().isoformat(), "date_to": reference[train_size - 1].timestamp.date().isoformat(), "candle_count": train_size},
            "out_of_sample": {"date_from": reference[train_size].timestamp.date().isoformat(), "date_to": reference[-1].timestamp.date().isoformat(), "candle_count": test_size, "total_return_pct": round(total_return, 6), "max_drawdown_pct": round(max_drawdown_pct(combined_curve), 6)},
            "legs": leg_rows,
        })
    returns = [float(fold["out_of_sample"]["total_return_pct"]) for fold in folds]
    drawdowns = [float(fold["out_of_sample"]["max_drawdown_pct"]) for fold in folds]
    return {
        "enabled": True,
        "status": "completed",
        "mode": "portfolio_static_weight_sleeves",
        "train_candles": train_size,
        "test_candles": test_size,
        "step_size": step_size,
        "split_policy": "chronological_train_then_out_of_sample_test_per_leg",
        "folds": folds,
        "summary": {"fold_count": len(folds), "positive_fold_count": sum(1 for value in returns if value > 0), "positive_fold_ratio": round(sum(1 for value in returns if value > 0) / len(folds), 6) if folds else 0, "average_return_pct": round(sum(returns) / len(returns), 6) if returns else 0, "worst_drawdown_pct": round(max(drawdowns), 6) if drawdowns else 0, "metric_scope": "out_of_sample_only", "manual_review_required": True},
        "limitations": "Legs are aligned by chronological row index after per-asset filtering; calendars must be reviewed when assets trade on different sessions.",
        "order_creation_allowed": False,
        "execution_available": False,
    }


def walk_forward_result(
    *,
    candles: list[Candle],
    initial_capital: float,
    params: dict[str, Any],
    strategy_dsl: dict[str, Any],
) -> dict[str, Any]:
    config = params.get("walk_forward") if isinstance(params.get("walk_forward"), dict) else {}
    enabled = bool(config.get("enabled"))
    if not enabled:
        return {
            "enabled": False,
            "status": "not_requested",
            "folds": [],
            "summary": {},
            "order_creation_allowed": False,
            "execution_available": False,
        }
    short_window = int(strategy_dsl["short_window"])
    long_window = int(strategy_dsl["long_window"])
    minimum = max(long_window + 1, 5)
    train_size = max(int(config.get("train_candles") or config.get("fold_size") or minimum), minimum)
    test_size = max(int(config.get("test_candles") or config.get("fold_size") or minimum), minimum)
    step_size = max(int(config.get("step_size") or test_size), 1)
    required = train_size + test_size
    if len(candles) < required:
        return {
            "enabled": True,
            "status": "blocked",
            "blocking_reasons": ["insufficient_candles_for_walk_forward"],
            "folds": [],
            "summary": {"candle_count": len(candles), "required_candles": required, "train_candles": train_size, "test_candles": test_size},
            "order_creation_allowed": False,
            "execution_available": False,
        }

    folds: list[dict[str, Any]] = []
    for start in range(0, len(candles) - required + 1, step_size):
        train_candles = candles[start:start + train_size]
        test_candles = candles[start + train_size:start + required]
        in_sample = simulate_ma_cross_on_candles(
            candles=train_candles,
            initial_capital=initial_capital,
            short_window=short_window,
            long_window=long_window,
            position_pct=float(params.get("position_pct") or 1.0),
            fee_bps=float(params.get("fee_bps") or 0),
            slippage_bps=float(params.get("slippage_bps") or 0),
            max_volume_participation_pct=liquidity_participation(params),
        )
        out_of_sample = simulate_ma_cross_on_candles(
            candles=train_candles + test_candles,
            initial_capital=initial_capital,
            short_window=short_window,
            long_window=long_window,
            position_pct=float(params.get("position_pct") or 1.0),
            fee_bps=float(params.get("fee_bps") or 0),
            slippage_bps=float(params.get("slippage_bps") or 0),
            max_volume_participation_pct=liquidity_participation(params),
            evaluation_start_index=len(train_candles),
        )
        folds.append({
            "index": len(folds) + 1,
            "in_sample": {"date_from": train_candles[0].timestamp.date().isoformat(), "date_to": train_candles[-1].timestamp.date().isoformat(), "candle_count": len(train_candles), **in_sample},
            "out_of_sample": {"date_from": test_candles[0].timestamp.date().isoformat(), "date_to": test_candles[-1].timestamp.date().isoformat(), "candle_count": len(test_candles), **out_of_sample},
            "total_return_pct": out_of_sample["total_return_pct"],
            "max_drawdown_pct": out_of_sample["max_drawdown_pct"],
            "trade_count": out_of_sample["trade_count"],
        })
    returns = [float(fold["total_return_pct"]) for fold in folds]
    drawdowns = [float(fold["max_drawdown_pct"]) for fold in folds]
    positive_count = sum(1 for value in returns if value > 0)
    return {
        "enabled": True,
        "status": "completed",
        "train_candles": train_size,
        "test_candles": test_size,
        "step_size": step_size,
        "split_policy": "chronological_train_then_out_of_sample_test",
        "parameter_policy": "fixed_user_supplied_parameters; training metrics are descriptive and never selected using test results",
        "folds": folds,
        "summary": {
            "fold_count": len(folds),
            "positive_fold_count": positive_count,
            "positive_fold_ratio": round(positive_count / len(folds), 6) if folds else 0,
            "average_return_pct": round(sum(returns) / len(returns), 6) if returns else 0,
            "worst_drawdown_pct": round(max(drawdowns), 6) if drawdowns else 0,
            "manual_review_required": True,
            "metric_scope": "out_of_sample_only",
        },
        "cost_model": {"fee_bps": float(params.get("fee_bps") or 0), "slippage_bps": float(params.get("slippage_bps") or 0), "max_volume_participation_pct": liquidity_participation(params)},
        "order_creation_allowed": False,
        "execution_available": False,
    }


def simulate_ma_cross_on_candles(
    *,
    candles: list[Candle],
    initial_capital: float,
    short_window: int,
    long_window: int,
    position_pct: float,
    fee_bps: float,
    slippage_bps: float = 0.0,
    max_volume_participation_pct: float | None = None,
    evaluation_start_index: int = 0,
) -> dict[str, Any]:
    position_pct = min(max(position_pct, 0.0), 1.0)
    fee_rate = fee_bps / 10_000
    slippage_rate = slippage_bps / 10_000
    cash = initial_capital
    quantity = 0.0
    equity_curve: list[float] = []
    trade_count = 0
    for index, candle in enumerate(candles):
        close = float(candle.close)
        if index >= max(long_window, evaluation_start_index):
            prior_closes = [float(item.close) for item in candles[:index]]
            short_ma = sum(prior_closes[-short_window:]) / short_window
            long_ma = sum(prior_closes[-long_window:]) / long_window
            if short_ma > long_ma and cash > 0:
                deploy_cash = cash * position_pct
                fee = deploy_cash * fee_rate
                fill_price = close * (1 + slippage_rate)
                desired_quantity = deploy_cash / (fill_price * (1 + fee_rate)) if fill_price else 0
                quantity_bought = min(desired_quantity, candle_fill_capacity(candle, max_volume_participation_pct))
                if quantity_bought > 0:
                    gross = quantity_bought * fill_price
                    fee = gross * fee_rate
                    cash -= gross + fee
                    quantity += quantity_bought
                    trade_count += 1
            elif short_ma < long_ma and quantity > 0:
                fill_price = close * (1 - slippage_rate)
                quantity_sold = min(quantity, candle_fill_capacity(candle, max_volume_participation_pct))
                gross = quantity_sold * fill_price
                fee = gross * fee_rate
                cash += gross - fee
                quantity -= quantity_sold
                if quantity <= 1e-12:
                    quantity = 0.0
                trade_count += 1
        if index >= evaluation_start_index:
            equity_curve.append(cash + quantity * close)
    final_capital = equity_curve[-1] if equity_curve else initial_capital
    return {
        "total_return_pct": round(((final_capital - initial_capital) / initial_capital) * 100, 6) if initial_capital else 0,
        "max_drawdown_pct": round(max_drawdown_pct(equity_curve), 6),
        "trade_count": trade_count,
        "equity_curve": [round(value, 6) for value in equity_curve],
    }


def promotion_check(key: str, label: str, status: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "evidence": evidence,
    }


def promotion_next_actions(status: str) -> list[str]:
    if status == "blocked":
        return ["Complete a read-only backtest with valid local candles before research review."]
    if status == "review_required":
        return ["Review metrics, drawdown, and simulated trades manually before changing strategy metadata."]
    return ["Create a human review task or strategy-rule proposal; do not create order drafts from this preflight."]


def dedupe_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
