from dataclasses import dataclass
from datetime import datetime
import math
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset
from app.models import AuditLog
from app.models import Candle
from app.models import InvestmentThesis
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import Signal


ORDER_ALLOWED_LEVELS = {"A3_ORDER_DRAFT", "A4_APPROVAL_EXECUTION", "A5_CONTROLLED_AUTO"}
QUEUE_ACTIONS = {"draft_buy", "draft_sell", "reduce"}


class SignalOrderIntentNotAllowedError(ValueError):
    pass


@dataclass(frozen=True)
class CandleInput:
    close: float
    high: float | None = None
    low: float | None = None
    volume: float | None = None


@dataclass(frozen=True)
class SignalInputContext:
    source: str
    timeframe: str | None
    candle_count: int
    as_of: str | None


class SignalEngineService:
    def __init__(self, db: Session):
        self.db = db

    def generate(
        self,
        *,
        asset_id: str,
        candles: list[dict[str, Any]],
        signal_types: list[str],
        horizon: str,
        market_facts: dict[str, Any] | None = None,
        onchain_facts: dict[str, Any] | None = None,
    ) -> list[Signal]:
        parsed_candles, input_context = self._resolve_candle_inputs(
            asset_id=asset_id,
            candles=candles,
            horizon=horizon,
        )
        signals: list[Signal] = []
        for signal_type in signal_types:
            payload = self._build_signal_payload(
                signal_type=signal_type,
                asset_id=asset_id,
                candles=parsed_candles,
                horizon=horizon,
                market_facts=market_facts or {},
                onchain_facts=onchain_facts or {},
            )
            payload["evidence"] = {
                **payload.get("evidence", {}),
                "input": {
                    "source": input_context.source,
                    "timeframe": input_context.timeframe,
                    "candle_count": input_context.candle_count,
                    "as_of": input_context.as_of,
                },
            }
            signal = Signal(
                asset_id=asset_id,
                signal_type=payload["signal_type"],
                direction=payload["direction"],
                strength=payload["strength"],
                source="phase6_signal_engine",
                observation_json=payload,
            )
            self.db.add(signal)
            self.db.flush()
            self._write_audit_log(
                action="signal.generated",
                entity_type="Signal",
                entity_id=signal.id,
                payload_json={"asset_id": asset_id, "signal_type": signal.signal_type, "direction": signal.direction},
            )
            signals.append(signal)

        self.db.commit()
        for signal in signals:
            self.db.refresh(signal)
        return signals

    def _resolve_candle_inputs(
        self,
        *,
        asset_id: str,
        candles: list[dict[str, Any]],
        horizon: str,
    ) -> tuple[list[CandleInput], SignalInputContext]:
        if candles:
            parsed_candles = [parse_candle(candle) for candle in candles]
            return parsed_candles, SignalInputContext(
                source="request_candles",
                timeframe=None,
                candle_count=len(parsed_candles),
                as_of=None,
            )

        timeframe, limit = local_candle_plan_for_horizon(horizon)
        local_candles = list(
            self.db.scalars(
                select(Candle)
                .where(Candle.asset_id == asset_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc(), Candle.id.desc())
                .limit(limit)
            ).all()
        )
        local_candles.reverse()
        parsed_candles = [parse_candle_from_model(candle) for candle in local_candles]
        return parsed_candles, SignalInputContext(
            source="stored_candles" if parsed_candles else "stored_candles_unavailable",
            timeframe=timeframe,
            candle_count=len(parsed_candles),
            as_of=local_candles[-1].timestamp.isoformat() if local_candles else None,
        )

    def create_order_intent(
        self,
        *,
        signal: Signal,
        account_id: str,
        automation_level: str,
        signal_order_intents_enabled: bool,
        quantity: float | None,
        notional: float | None,
    ) -> OrderIntent:
        if not signal_order_intents_enabled or automation_level not in ORDER_ALLOWED_LEVELS:
            self._write_audit_log(
                action="signal.order_intent_blocked",
                entity_type="Signal",
                entity_id=signal.id,
                payload_json={
                    "automation_level": automation_level,
                    "signal_order_intents_enabled": signal_order_intents_enabled,
                },
            )
            self.db.commit()
            raise SignalOrderIntentNotAllowedError("signal-to-order-intent conversion is not allowed")

        thesis = self._latest_active_thesis(signal.asset_id)
        side = side_from_signal(signal)
        thesis_note = (
            f" Linked thesis {thesis.id} is attached for review."
            if thesis is not None
            else " No active thesis was attached; thesis review remains required."
        )
        order_intent = OrderIntent(
            source_type="signal",
            source_id=signal.id,
            asset_id=signal.asset_id,
            account_id=account_id,
            investment_thesis_id=thesis.id if thesis is not None else None,
            strategy_playbook_id=thesis.strategy_playbook_id if thesis is not None else None,
            source_signal_id=signal.id,
            side=side,
            order_type="market",
            quantity=quantity,
            notional=notional,
            limit_price=None,
            rationale=(
                f"Passive draft from signal {signal.signal_type}; requires thesis, risk checks, gates, "
                f"and approval before any execution.{thesis_note}"
            ),
            status="created",
        )
        self.db.add(order_intent)
        self.db.flush()
        self._write_audit_log(
            action="signal.order_intent_created",
            entity_type="OrderIntent",
            entity_id=order_intent.id,
            payload_json={
                "signal_id": signal.id,
                "automation_level": automation_level,
                "side": side,
                "signal_order_intents_enabled": signal_order_intents_enabled,
                "investment_thesis_id": thesis.id if thesis is not None else None,
                "strategy_playbook_id": thesis.strategy_playbook_id if thesis is not None else None,
            },
        )
        self.db.commit()
        self.db.refresh(order_intent)
        return order_intent

    def _latest_active_thesis(self, asset_id: str) -> InvestmentThesis | None:
        return self.db.scalar(
            select(InvestmentThesis)
            .where(
                InvestmentThesis.asset_id == asset_id,
                InvestmentThesis.status.in_(["active", "monitoring"]),
            )
            .order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc())
            .limit(1)
        )

    def list_review_queue(self, *, limit: int = 50) -> list[dict[str, Any]]:
        signals = list(
            self.db.scalars(
                select(Signal)
                .order_by(Signal.created_at.desc(), Signal.id.desc())
                .limit(max(limit * 3, limit))
            ).all()
        )
        queue_items: list[dict[str, Any]] = []
        for signal in signals:
            if signal.suggested_action not in QUEUE_ACTIONS:
                continue

            asset = self.db.get(Asset, signal.asset_id)
            if asset is None:
                continue

            thesis = self.db.scalar(
                select(InvestmentThesis)
                .where(
                    InvestmentThesis.asset_id == signal.asset_id,
                    InvestmentThesis.status.in_(["active", "monitoring"]),
                )
                .order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc())
                .limit(1)
            )
            order_intent = self.db.scalar(
                select(OrderIntent)
                .where(
                    (OrderIntent.source_signal_id == signal.id)
                    | ((OrderIntent.source_type == "signal") & (OrderIntent.source_id == signal.id))
                )
                .order_by(OrderIntent.created_at.desc(), OrderIntent.id.desc())
                .limit(1)
            )
            order_draft = None
            if order_intent is not None:
                order_draft = self.db.scalar(
                    select(OrderDraft)
                    .where(OrderDraft.order_intent_id == order_intent.id)
                    .order_by(OrderDraft.created_at.desc(), OrderDraft.id.desc())
                    .limit(1)
                )

            review_status, queue_reason, next_action = classify_review_status(
                signal=signal,
                has_active_thesis=thesis is not None,
                has_order_intent=order_intent is not None,
                has_order_draft=order_draft is not None,
            )
            input_context = signal.evidence.get("input", {}) if isinstance(signal.evidence, dict) else {}
            queue_items.append(
                {
                    "signal_id": signal.id,
                    "asset_id": signal.asset_id,
                    "asset_symbol": asset.symbol,
                    "asset_name": asset.name,
                    "signal_type": signal.signal_type,
                    "direction": signal.direction,
                    "strength": float(signal.strength),
                    "confidence": float(signal.confidence),
                    "suggested_action": signal.suggested_action,
                    "horizon": signal.horizon,
                    "review_status": review_status,
                    "priority": review_priority(signal),
                    "queue_reason": queue_reason,
                    "next_action": next_action,
                    "input_source": input_context.get("source") if isinstance(input_context.get("source"), str) else None,
                    "input_timeframe": input_context.get("timeframe") if isinstance(input_context.get("timeframe"), str) else None,
                    "input_candle_count": int(input_context.get("candle_count", 0) or 0),
                    "has_active_thesis": thesis is not None,
                    "latest_thesis_id": thesis.id if thesis is not None else None,
                    "has_order_intent": order_intent is not None,
                    "latest_order_intent_id": order_intent.id if order_intent is not None else None,
                    "has_order_draft": order_draft is not None,
                    "latest_order_draft_id": order_draft.id if order_draft is not None else None,
                    "created_at": signal.created_at,
                }
            )
            if len(queue_items) >= limit:
                break
        return queue_items

    def _build_signal_payload(
        self,
        *,
        signal_type: str,
        asset_id: str,
        candles: list[CandleInput],
        horizon: str,
        market_facts: dict[str, Any],
        onchain_facts: dict[str, Any],
    ) -> dict[str, Any]:
        if signal_type == "rsi":
            return rsi_signal(asset_id, candles, horizon)
        if signal_type == "ma_cross":
            return ma_cross_signal(asset_id, candles, horizon)
        if signal_type == "macd":
            return placeholder_signal(asset_id, "macd", horizon, "neutral", "MACD requires configured EMA windows.")
        if signal_type == "bollinger_band":
            return placeholder_signal(asset_id, "bollinger_band", horizon, "neutral", "Bollinger Band requires windowed volatility bands.")
        if signal_type == "volume_anomaly":
            return volume_anomaly_signal(asset_id, candles, horizon)
        if signal_type == "volatility_spike":
            return volatility_spike_signal(asset_id, candles, horizon)
        if signal_type in {"stock_capital_flow", "crypto_exchange_flow", "funding_rate"}:
            return placeholder_signal(asset_id, signal_type, horizon, "neutral", market_facts.get(signal_type, "Capital-flow data unavailable."))
        if signal_type in {"whale_transfer", "large_wallet_accumulation", "token_unlock", "liquidity_change"}:
            return placeholder_signal(asset_id, signal_type, horizon, "neutral", onchain_facts.get(signal_type, "On-chain data unavailable."))
        return placeholder_signal(asset_id, signal_type, horizon, "neutral", "Unknown signal type; observation recorded as unavailable.")

    def evaluate_signal_quality(self, *, horizon_candles: int = 5, limit: int = 500, minimum_sample_size: int = 30) -> dict[str, Any]:
        """Evaluate stored signals against realized forward returns from local
        candles: a bullish signal 'hits' when the close N candles later is
        higher than the close at signal time (and inversely for bearish).
        Signals without enough forward history are skipped and reported, not
        guessed — review-only output, never an execution input."""
        if horizon_candles < 1 or horizon_candles > 60:
            raise ValueError("horizon_candles must be between 1 and 60")
        if minimum_sample_size < 10 or minimum_sample_size > 1000:
            raise ValueError("minimum_sample_size must be between 10 and 1000")
        signals = list(
            self.db.scalars(
                select(Signal).order_by(Signal.created_at.desc(), Signal.id.desc()).limit(max(1, min(limit, 2000)))
            ).all()
        )
        evaluated: list[dict[str, Any]] = []
        skipped = 0
        skipped_reasons: dict[str, int] = {}
        for signal in signals:
            input_evidence = ((signal.observation_json or {}).get("evidence") or {}).get("input") or {}
            timeframe = str(input_evidence.get("timeframe") or "1d")
            as_of_raw = input_evidence.get("as_of")
            as_of = signal.created_at
            if as_of_raw:
                try:
                    as_of = datetime.fromisoformat(str(as_of_raw).replace("Z", "+00:00"))
                except ValueError:
                    skipped += 1
                    skipped_reasons["invalid_signal_input_as_of"] = skipped_reasons.get("invalid_signal_input_as_of", 0) + 1
                    continue
            base_candle = self.db.scalar(
                select(Candle)
                .where(Candle.asset_id == signal.asset_id, Candle.timeframe == timeframe, Candle.timestamp <= as_of)
                .order_by(Candle.timestamp.desc(), Candle.id.desc())
                .limit(1)
            )
            if base_candle is None:
                skipped += 1
                skipped_reasons["missing_point_in_time_base_candle"] = skipped_reasons.get("missing_point_in_time_base_candle", 0) + 1
                continue
            forward_candles = list(
                self.db.scalars(
                    select(Candle)
                    .where(Candle.asset_id == signal.asset_id, Candle.timeframe == timeframe, Candle.timestamp > base_candle.timestamp)
                    .order_by(Candle.timestamp.asc(), Candle.id.asc())
                    .limit(horizon_candles)
                ).all()
            )
            if len(forward_candles) < horizon_candles:
                skipped += 1
                skipped_reasons["insufficient_forward_candles"] = skipped_reasons.get("insufficient_forward_candles", 0) + 1
                continue
            base_close = float(base_candle.close)
            forward_close = float(forward_candles[horizon_candles - 1].close)
            if base_close <= 0:
                skipped += 1
                skipped_reasons["non_positive_base_close"] = skipped_reasons.get("non_positive_base_close", 0) + 1
                continue
            forward_return = (forward_close - base_close) / base_close
            direction = str(signal.direction).lower()
            if direction == "bullish":
                hit = forward_return > 0
            elif direction == "bearish":
                hit = forward_return < 0
            else:
                skipped += 1
                skipped_reasons["non_directional_signal"] = skipped_reasons.get("non_directional_signal", 0) + 1
                continue
            directional_return = forward_return if direction == "bullish" else -forward_return
            evaluated.append(
                {
                    "signal_id": signal.id,
                    "asset_id": signal.asset_id,
                    "signal_type": signal.signal_type,
                    "direction": direction,
                    "strength": float(signal.strength or 0),
                    "created_at": signal.created_at.isoformat(),
                    "timeframe": timeframe,
                    "base_candle_at": base_candle.timestamp.isoformat(),
                    "forward_candle_at": forward_candles[horizon_candles - 1].timestamp.isoformat(),
                    "forward_return_pct": round(forward_return * 100, 4),
                    "directional_return_pct": round(directional_return * 100, 4),
                    "hit": hit,
                }
            )
        by_type: dict[str, dict[str, Any]] = {}
        for item in evaluated:
            entry = by_type.setdefault(item["signal_type"], {"evaluated": 0, "hits": 0, "forward_returns": [], "directional_returns": []})
            entry["evaluated"] += 1
            entry["hits"] += 1 if item["hit"] else 0
            entry["forward_returns"].append(item["forward_return_pct"])
            entry["directional_returns"].append(item["directional_return_pct"])
        for entry in by_type.values():
            entry["hit_rate"] = round(entry["hits"] / entry["evaluated"], 4) if entry["evaluated"] else None
            entry["avg_forward_return_pct"] = round(mean(entry["forward_returns"]), 4) if entry["forward_returns"] else None
            entry["avg_directional_return_pct"] = round(mean(entry["directional_returns"]), 4) if entry["directional_returns"] else None
            interval = wilson_interval(entry["hits"], entry["evaluated"])
            entry["hit_rate_confidence_interval_95"] = interval
            entry["sample_status"] = "sufficient" if entry["evaluated"] >= minimum_sample_size else "insufficient"
            del entry["forward_returns"]
            del entry["directional_returns"]
        hits = sum(1 for item in evaluated if item["hit"])
        hit_rate = hits / len(evaluated) if evaluated else None
        # Baseline: would a signal add information over blindly betting the same
        # direction? For each evaluated signal, the "always right" direction is
        # whichever way price actually moved; a directional signal has an edge
        # only if its hit rate beats the base rate of its own direction being
        # correct on this sample. We compute that base rate from the realized
        # up/down frequency across the evaluated signals' forward returns.
        up_moves = sum(1 for item in evaluated if item["forward_return_pct"] > 0)
        down_moves = sum(1 for item in evaluated if item["forward_return_pct"] < 0)
        bullish_count = sum(1 for item in evaluated if item["direction"] == "bullish")
        bearish_count = sum(1 for item in evaluated if item["direction"] == "bearish")
        baseline_hit_rate = None
        edge_vs_baseline = None
        if evaluated:
            up_rate = up_moves / len(evaluated)
            down_rate = down_moves / len(evaluated)
            # Expected hit rate if signals were issued in the same direction
            # mix but had no predictive skill (each bullish scores up_rate,
            # each bearish scores down_rate).
            baseline_hit_rate = (bullish_count * up_rate + bearish_count * down_rate) / len(evaluated)
            edge_vs_baseline = hit_rate - baseline_hit_rate
        confidence_interval = wilson_interval(hits, len(evaluated)) if evaluated else None
        sample_sufficient = len(evaluated) >= minimum_sample_size
        statistically_supported_edge = bool(sample_sufficient and confidence_interval and baseline_hit_rate is not None and confidence_interval["lower"] > baseline_hit_rate)
        report = {
            "status": "evaluated" if evaluated else "insufficient_forward_data",
            "horizon_candles": horizon_candles,
            "signals_considered": len(signals),
            "signals_evaluated": len(evaluated),
            "signals_skipped_insufficient_data": skipped,
            "signals_skipped_by_reason": skipped_reasons,
            "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
            "avg_forward_return_pct": round(mean(item["forward_return_pct"] for item in evaluated), 4) if evaluated else None,
            "avg_directional_return_pct": round(mean(item["directional_return_pct"] for item in evaluated), 4) if evaluated else None,
            "statistical_evidence": {
                "minimum_sample_size": minimum_sample_size,
                "sample_sufficient": sample_sufficient,
                "hit_rate_confidence_interval_95": confidence_interval,
                "statistically_supported_edge": statistically_supported_edge,
                "quality_claim_allowed": statistically_supported_edge,
                "status": "supported_edge" if statistically_supported_edge else "insufficient_sample" if not sample_sufficient else "edge_not_supported",
                "note": "A quality claim requires the 95% Wilson lower bound for hit rate to exceed the zero-skill baseline and the minimum sample size. Point estimates alone never qualify.",
            },
            "baseline": {
                "baseline_hit_rate": round(baseline_hit_rate, 4) if baseline_hit_rate is not None else None,
                "edge_vs_baseline": round(edge_vs_baseline, 4) if edge_vs_baseline is not None else None,
                "has_positive_edge": bool(edge_vs_baseline is not None and edge_vs_baseline > 0),
                "statistically_supported_edge": statistically_supported_edge,
                "up_move_rate": round(up_moves / len(evaluated), 4) if evaluated else None,
                "down_move_rate": round(down_moves / len(evaluated), 4) if evaluated else None,
                "note": "Baseline = expected hit rate for the same direction mix with zero skill. A positive point estimate is descriptive only; quality requires minimum sample size and a 95% Wilson lower bound above baseline.",
            },
            "by_signal_type": by_type,
            "outcomes": evaluated[:200],
            "methodology": "point-in-time out-of-sample evaluation: base close is the stored input as-of candle (or latest same-timeframe candle at/before signal creation), followed by N strictly later candles; missing outcomes are skipped, never imputed",
            "evaluation_scope": "point_in_time_out_of_sample",
            "execution_available": False,
        }
        self._write_audit_log(
            action="signal_quality.evaluated",
            entity_type="Signal",
            entity_id=f"quality-report-h{horizon_candles}",
            payload_json={
                "signals_evaluated": len(evaluated),
                "signals_skipped": skipped,
                "hit_rate": report["hit_rate"],
                "execution_available": False,
            },
        )
        self.db.commit()
        return report

    def _write_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload_json: dict[str, Any],
    ) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="phase6-signal-engine",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


def parse_candle(payload: dict[str, Any]) -> CandleInput:
    close = float(payload["close"])
    return CandleInput(
        close=close,
        high=float(payload["high"]) if payload.get("high") is not None else close,
        low=float(payload["low"]) if payload.get("low") is not None else close,
        volume=float(payload["volume"]) if payload.get("volume") is not None else None,
    )


def parse_candle_from_model(candle: Candle) -> CandleInput:
    return CandleInput(
        close=float(candle.close),
        high=float(candle.high),
        low=float(candle.low),
        volume=float(candle.volume),
    )


def local_candle_plan_for_horizon(horizon: str) -> tuple[str, int]:
    if horizon == "intraday":
        return "1h", 72
    if horizon == "long_term":
        return "1d", 180
    return "1d", 60


def rsi_signal(asset_id: str, candles: list[CandleInput], horizon: str) -> dict[str, Any]:
    closes = [candle.close for candle in candles]
    if len(closes) < 2:
        return placeholder_signal(asset_id, "rsi", horizon, "neutral", "RSI data unavailable; at least 2 closes are required.")

    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    period_changes = changes[-14:]
    gains = [max(change, 0) for change in period_changes]
    losses = [abs(min(change, 0)) for change in period_changes]
    average_gain = mean(gains) if gains else 0
    average_loss = mean(losses) if losses else 0
    rsi = 100 if average_loss == 0 else 100 - (100 / (1 + (average_gain / average_loss)))

    if rsi <= 30:
        direction = "bullish"
        suggested_action = "watch"
    elif rsi >= 70:
        direction = "bearish"
        suggested_action = "reduce"
    else:
        direction = "neutral"
        suggested_action = "hold"

    return signal_payload(
        asset_id=asset_id,
        signal_type="rsi",
        direction=direction,
        strength=round(min(abs(rsi - 50) * 2, 100), 2),
        horizon=horizon,
        evidence={"rsi": round(rsi, 2), "periods": len(period_changes), "last_close": closes[-1]},
        invalidation_condition="RSI returns to the neutral 45-55 zone or price trend invalidates the setup.",
        suggested_action=suggested_action,
        confidence=0.7,
    )


def ma_cross_signal(asset_id: str, candles: list[CandleInput], horizon: str) -> dict[str, Any]:
    closes = [candle.close for candle in candles]
    if len(closes) < 5:
        return placeholder_signal(asset_id, "ma_cross", horizon, "neutral", "MA cross data unavailable; at least 5 closes are required.")

    short_window = 3
    long_window = 5
    short_ma = mean(closes[-short_window:])
    long_ma = mean(closes[-long_window:])
    prior_short_ma = mean(closes[-short_window - 1 : -1])
    prior_long_ma = mean(closes[-long_window - 1 : -1]) if len(closes) > long_window else long_ma

    crossed_up = prior_short_ma <= prior_long_ma and short_ma > long_ma
    crossed_down = prior_short_ma >= prior_long_ma and short_ma < long_ma
    if crossed_up:
        direction = "bullish"
        suggested_action = "draft_buy"
    elif crossed_down:
        direction = "bearish"
        suggested_action = "draft_sell"
    else:
        direction = "neutral"
        suggested_action = "hold"

    spread = abs(short_ma - long_ma) / long_ma if long_ma else 0
    return signal_payload(
        asset_id=asset_id,
        signal_type="ma_cross",
        direction=direction,
        strength=round(min(spread * 1000, 100), 2),
        horizon=horizon,
        evidence={
            "short_window": short_window,
            "long_window": long_window,
            "short_ma": round(short_ma, 4),
            "long_ma": round(long_ma, 4),
            "prior_short_ma": round(prior_short_ma, 4),
            "prior_long_ma": round(prior_long_ma, 4),
        },
        invalidation_condition="Short moving average crosses back through the long moving average.",
        suggested_action=suggested_action,
        confidence=0.72 if direction != "neutral" else 0.55,
    )


def volume_anomaly_signal(asset_id: str, candles: list[CandleInput], horizon: str) -> dict[str, Any]:
    volumes = [candle.volume for candle in candles if candle.volume is not None]
    if len(volumes) < 5:
        return placeholder_signal(asset_id, "volume_anomaly", horizon, "neutral", "Volume data unavailable; at least 5 volume points are required.")

    current = volumes[-1]
    baseline = mean(volumes[-5:-1])
    ratio = current / baseline if baseline else 0
    direction = "bullish" if ratio >= 1.8 else "neutral"
    return signal_payload(
        asset_id=asset_id,
        signal_type="volume_anomaly",
        direction=direction,
        strength=round(min(ratio * 25, 100), 2),
        horizon=horizon,
        evidence={"current_volume": current, "baseline_volume": round(baseline, 2), "ratio": round(ratio, 2)},
        invalidation_condition="Volume normalizes below 1.2x baseline.",
        suggested_action="watch",
        confidence=0.6,
    )


def volatility_spike_signal(asset_id: str, candles: list[CandleInput], horizon: str) -> dict[str, Any]:
    ranges = [((candle.high or candle.close) - (candle.low or candle.close)) / candle.close for candle in candles if candle.close]
    if len(ranges) < 5:
        return placeholder_signal(asset_id, "volatility_spike", horizon, "neutral", "Volatility data unavailable; at least 5 candles are required.")

    current = ranges[-1]
    baseline = mean(ranges[-5:-1])
    ratio = current / baseline if baseline else 0
    direction = "bearish" if ratio >= 2 else "neutral"
    return signal_payload(
        asset_id=asset_id,
        signal_type="volatility_spike",
        direction=direction,
        strength=round(min(ratio * 30, 100), 2),
        horizon=horizon,
        evidence={"current_range": round(current, 4), "baseline_range": round(baseline, 4), "ratio": round(ratio, 2)},
        invalidation_condition="Realized range falls back near recent baseline.",
        suggested_action="watch",
        confidence=0.58,
    )


def placeholder_signal(asset_id: str, signal_type: str, horizon: str, direction: str, evidence_text: Any) -> dict[str, Any]:
    return signal_payload(
        asset_id=asset_id,
        signal_type=signal_type,
        direction=direction,
        strength=0,
        horizon=horizon,
        evidence={"message": evidence_text},
        invalidation_condition="Data becomes available or placeholder assumption is replaced.",
        suggested_action="watch",
        confidence=0.1,
    )


def signal_payload(
    *,
    asset_id: str,
    signal_type: str,
    direction: str,
    strength: float,
    horizon: str,
    evidence: dict[str, Any],
    invalidation_condition: str,
    suggested_action: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "signal_type": signal_type,
        "direction": direction,
        "strength": strength,
        "horizon": horizon,
        "evidence": evidence,
        "invalidation_condition": invalidation_condition,
        "suggested_action": suggested_action,
        "confidence": confidence,
    }


def wilson_interval(hits: int, sample_size: int, z: float = 1.959963984540054) -> dict[str, Any] | None:
    if sample_size <= 0:
        return None
    proportion = hits / sample_size
    denominator = 1 + (z * z / sample_size)
    center = (proportion + z * z / (2 * sample_size)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) / sample_size) + (z * z / (4 * sample_size * sample_size))) / denominator
    return {"lower": round(max(0.0, center - margin), 4), "upper": round(min(1.0, center + margin), 4), "method": "wilson_95"}


def side_from_signal(signal: Signal) -> str:
    suggested_action = signal.observation_json.get("suggested_action")
    if suggested_action == "draft_sell":
        return "sell"
    if suggested_action == "draft_buy":
        return "buy"
    if signal.direction == "bearish":
        return "sell"
    return "buy"


def review_priority(signal: Signal) -> str:
    if signal.suggested_action in {"draft_buy", "draft_sell"} and (float(signal.confidence) >= 0.6 or float(signal.strength) >= 50):
        return "high"
    if signal.suggested_action == "reduce":
        return "medium"
    return "low"


def classify_review_status(
    *,
    signal: Signal,
    has_active_thesis: bool,
    has_order_intent: bool,
    has_order_draft: bool,
) -> tuple[str, str, str]:
    if has_order_draft:
        return (
            "draft_in_progress",
            "Signal already has a guarded draft. Continue review in the draft workflow.",
            "Open order draft",
        )
    if has_order_intent:
        return (
            "intent_created",
            "Signal already has an order intent. Continue gates and risk review before drafting.",
            "Continue gates",
        )
    if not has_active_thesis:
        return (
            "needs_thesis_review",
            "Actionable signal has no active thesis coverage yet.",
            "Review thesis",
        )
    return (
        "ready_for_draft_review",
        "Actionable signal has thesis coverage and is ready for guarded draft review.",
        "Create guarded draft",
    )
