from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from datetime import timezone
from statistics import mean
from statistics import stdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.market_data_readonly import YahooFinancePublicMarketDataAdapter
from app.api.domain import write_audit_log
from app.models import Asset
from app.models import Account
from app.models import Candle
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import ExportArtifact
from app.models import ExchangeExposure
from app.models import Position
from app.models import ProtocolPosition
from app.models import Reminder
from app.models import RiskBudget
from app.models import StablecoinExposure
from app.services.data_catalog import DataCatalogService
from app.services.data_catalog import DataTrustGateError


MIN_RETURN_OBSERVATIONS = 60
CRYPTO_SYMBOL_MAP = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"}


RISK_LOCAL_NEXT_STEPS = [
    {
        "key": "time_series",
        "label": "同步只读日线序列",
        "detail": "使用只读行情和本地持仓生成对齐收益序列，先验证覆盖率、样本数和缺失资产。",
        "action": "run_portfolio_time_series_risk",
        "route": "/?module=risk",
    },
    {
        "key": "var_drawdown",
        "label": "复核 VaR 与回撤预算",
        "detail": "检查 95%/99% VaR、Expected Shortfall、最大回撤和预算消耗，超过阈值进入 Today Queue。",
        "action": "review_var_drawdown",
        "route": "/?module=risk",
    },
    {
        "key": "correlation_liquidity",
        "label": "复核相关性与流动性",
        "detail": "查看高相关大仓位、20D ADV、压力清算天数和压力测试解释。",
        "action": "review_correlation_liquidity",
        "route": "/?module=risk",
    },
    {
        "key": "evidence_packet",
        "label": "下载风险证据包",
        "detail": "保存 snapshot、quality report、audit packet，用于人工复核和后续回放。",
        "action": "download_portfolio_risk_evidence",
        "route": "/?module=risk",
    },
]


def portfolio_risk_gate(latest: dict[str, Any] | None = None) -> dict[str, Any]:
    has_latest = latest is not None
    coverage = float(latest.get("coverage_pct") or 0) if latest else 0.0
    observations = int(latest.get("observations") or 0) if latest else 0
    excluded = latest.get("excluded") or [] if latest else []
    budget_used = ((latest.get("drawdown") or {}).get("budget_used_pct") if latest else None)
    high_correlation_pairs = latest.get("high_correlation_pairs") or [] if latest else []
    liquidity_summary = latest.get("liquidity_summary") or {} if latest else {}
    stressed_days = float(liquidity_summary.get("max_stressed_days") or 0)
    missing: list[str] = []
    if not has_latest:
        missing.append("portfolio_time_series_risk")
    if coverage < 99:
        missing.append("full_position_market_data_coverage")
    if observations < MIN_RETURN_OBSERVATIONS:
        missing.append("minimum_aligned_return_observations")
    if excluded:
        missing.append("excluded_position_symbols")
    review_required = bool(
        missing
        or (budget_used is not None and float(budget_used) >= 80)
        or high_correlation_pairs
        or stressed_days >= 5
    )
    return {
        "label": "组合风险晋级门槛",
        "status": "review_ready" if has_latest and not missing else "action_required",
        "can_review_portfolio_risk": has_latest,
        "can_create_today_queue_alerts": has_latest,
        "can_open_risk_drilldown": has_latest,
        "can_use_for_plan_context": has_latest and observations >= MIN_RETURN_OBSERVATIONS,
        "can_unlock_order_approval": False,
        "can_execute_trades": False,
        "execution_available": False,
        "review_required": review_required,
        "required_before_plan": [
            "coverage_pct >= 99",
            f"observations >= {MIN_RETURN_OBSERVATIONS}",
            "excluded symbols reviewed",
            "VaR, drawdown, correlation, liquidity, stress tests manually reviewed",
        ],
        "missing": missing,
        "why_not_execution": "Portfolio risk is pre-trade review evidence only. It cannot approve orders, execute trades, sign wallets, withdraw funds, or bypass gates.",
    }


class PortfolioTimeSeriesRiskError(ValueError):
    pass


class PortfolioTimeSeriesRiskService:
    def __init__(self, db: Session, adapter: YahooFinancePublicMarketDataAdapter | None = None):
        self.db = db
        self.adapter = adapter or YahooFinancePublicMarketDataAdapter(
            {"symbol_map": CRYPTO_SYMBOL_MAP, "timeout_seconds": 8}
        )

    def latest(self, *, user_id: str) -> dict[str, Any] | None:
        artifact = self.db.scalar(
            select(ExportArtifact)
            .where(
                ExportArtifact.user_id == user_id,
                ExportArtifact.export_type == "portfolio_time_series_risk",
            )
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )
        if artifact is None:
            return None
        return {**artifact.payload_json, "artifact_id": artifact.id, "created_at": artifact.created_at.isoformat()}

    def evidence_packet(self, *, user_id: str) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        latest = self.latest(user_id=user_id)
        has_latest = latest is not None
        packet: dict[str, Any] = {
            "packet_type": "portfolio_time_series_risk_evidence_packet",
            "user_id": user_id,
            "generated_at": generated_at.isoformat(),
            "status": "ready_for_risk_review" if has_latest else "action_required",
            "latest_risk": latest,
            "latest_risk_artifact_id": latest.get("artifact_id") if latest else None,
            "snapshot_id": latest.get("snapshot_id") if latest else None,
            "quality_report_id": latest.get("quality_report_id") if latest else None,
            "metrics_available": {
                "var": bool(latest and latest.get("var")),
                "drawdown": bool(latest and latest.get("drawdown")),
                "correlation_matrix": bool(latest and latest.get("correlation_matrix")),
                "liquidity": bool(latest and latest.get("liquidity")),
                "stress_tests": bool(latest and latest.get("stress_tests")),
            },
            "local_next_steps": RISK_LOCAL_NEXT_STEPS,
            "risk_gate": portfolio_risk_gate(latest),
            "missing": [] if has_latest else ["portfolio_time_series_risk"],
            "next_action": (
                "Review VaR, drawdown budget, correlation, liquidity, and stress scenarios before creating or approving any plan."
                if has_latest
                else "Run the read-only portfolio risk calculation first, then download this packet again."
            ),
            "safe_boundary": "Read-only risk evidence only; no orders, no wallet signing, no withdrawals, no automatic approvals, no gate bypass.",
            "safe_boundaries": [
                "Uses read-only market and position evidence only.",
                "Does not create, approve, submit, or modify orders.",
                "Does not enable wallet signing, withdrawals, DEX swaps, or broker execution.",
                "Any action must return to a human-reviewed plan, risk gate, and approval flow.",
            ],
            "contains_secrets": False,
            "execution_available": False,
            "production_capability": False,
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="portfolio_time_series_risk_evidence_packet",
            format="json",
            status=packet["status"],
            payload_json=packet,
            summary_json={
                "status": packet["status"],
                "latest_risk_artifact_id": packet["latest_risk_artifact_id"],
                "snapshot_id": packet["snapshot_id"],
                "quality_report_id": packet["quality_report_id"],
                "execution_available": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        artifact.payload_json = packet
        write_audit_log(
            self.db,
            action="portfolio_risk.evidence_packet_created",
            entity_type="ExportArtifact",
            entity_id=artifact.id,
            payload_json={
                "status": packet["status"],
                "latest_risk_artifact_id": packet["latest_risk_artifact_id"],
                "contains_secrets": False,
                "execution_available": False,
            },
            actor_id=user_id,
        )
        self.db.commit()
        return packet

    def sync_market_data_for_review(self, *, user_id: str, lookback_days: int = 252) -> dict[str, Any]:
        if lookback_days < MIN_RETURN_OBSERVATIONS or lookback_days > 365:
            raise PortfolioTimeSeriesRiskError("lookback_days must be between 60 and 365")
        rows = list(self.db.execute(select(Position, Asset).join(Asset, Asset.id == Position.asset_id)).all())
        assets = {
            asset.id: asset
            for position, asset in rows
            if float(position.market_value or 0) > 0 and asset.asset_type.lower() not in {"cash", "stablecoin"}
        }
        if not assets:
            raise PortfolioTimeSeriesRiskError("no non-cash positions with positive market value")

        candle_payload: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for asset in assets.values():
            try:
                adapter_rows = self.adapter.get_candles(asset.symbol, "1d", lookback_days)
                if len(adapter_rows) < MIN_RETURN_OBSERVATIONS + 1:
                    raise PortfolioTimeSeriesRiskError(
                        f"only {len(adapter_rows)} daily candles; at least {MIN_RETURN_OBSERVATIONS + 1} required"
                    )
                for row in adapter_rows:
                    candle_payload.append(
                        {
                            "asset_id": asset.id,
                            "symbol": asset.symbol,
                            "timeframe": "1d",
                            "timestamp": normalize_dt(row.timestamp).isoformat(),
                            "open": float(row.open),
                            "high": float(row.high),
                            "low": float(row.low),
                            "close": float(row.close),
                            "volume": float(row.volume),
                            "source": "yfinance_public",
                        }
                    )
            except Exception as exc:
                failures.append({"symbol": asset.symbol, "error": str(exc)[:240]})

        covered_symbols = {row["symbol"] for row in candle_payload}
        coverage = len(covered_symbols) / len(assets)
        as_of = max(
            (datetime.fromisoformat(row["timestamp"]) for row in candle_payload),
            default=datetime.now(timezone.utc),
        )
        snapshot = DataSnapshot(
            snapshot_type="market_candles",
            as_of=as_of,
            data_json={
                "provider": "yfinance_public",
                "timeframe": "1d",
                "lookback_days": lookback_days,
                "candles": candle_payload,
                "failures": failures,
            },
            metadata_json={
                "provider": "yfinance_public",
                "symbols_requested": sorted(asset.symbol for asset in assets.values()),
                "symbols_imported": sorted(covered_symbols),
                "read_only": True,
                "execution_available": False,
            },
        )
        self.db.add(snapshot)
        self.db.flush()
        quality = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source="yfinance_public",
            metric_type="portfolio_risk_market_data_coverage",
            score=coverage if candle_payload else 0,
            details_json={
                "requested_assets": len(assets),
                "covered_assets": len(covered_symbols),
                "failures": failures,
                "minimum_observations": MIN_RETURN_OBSERVATIONS,
            },
        )
        self.db.add(quality)
        self.db.flush()
        entry = DataCatalogService(self.db).create_entry(
            dataset_type="market_candles",
            source="yfinance_public",
            source_ref=f"portfolio-risk:{user_id}",
            row_count=len(candle_payload),
            snapshot=snapshot,
            quality_report=quality,
            lineage_json={
                "consumer": "portfolio_time_series_risk",
                "symbols": sorted(covered_symbols),
                "data_origin": "authenticated_public_provider",
            },
            contract_json={
                "execution_available": False,
                "allowed_decision_scopes": ["portfolio_risk"],
                "requires_manual_promotion": True,
            },
        )
        write_audit_log(
            self.db,
            action="portfolio_risk.market_data_synced_for_review",
            entity_type="DataCatalogEntry",
            entity_id=entry.id,
            payload_json={
                "snapshot_id": snapshot.id,
                "quality_report_id": quality.id,
                "quality_status": entry.quality_status,
                "promotion_stage": "raw",
                "execution_available": False,
            },
            actor_id=user_id,
        )
        self.db.commit()
        return {
            "status": "promotion_required",
            "snapshot_id": snapshot.id,
            "quality_report_id": quality.id,
            "catalog_entry_id": entry.id,
            "quality_status": entry.quality_status,
            "promotion_stage": "raw",
            "symbols": sorted(covered_symbols),
            "failures": failures,
            "next_action": "Review this exact market-data snapshot and promote raw → reviewed → trusted before running portfolio risk.",
            "execution_available": False,
        }

    def sync_and_analyze(
        self,
        *,
        user_id: str,
        lookback_days: int = 252,
        drawdown_budget_pct: float | None = None,
        sync_market_data: bool = True,
        data_snapshot_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if lookback_days < MIN_RETURN_OBSERVATIONS or lookback_days > 365:
            raise PortfolioTimeSeriesRiskError("lookback_days must be between 60 and 365")
        if sync_market_data:
            return self.sync_market_data_for_review(user_id=user_id, lookback_days=lookback_days)
        if not data_snapshot_ids:
            raise PortfolioTimeSeriesRiskError("trusted market candle data_snapshot_ids are required")

        rows = list(self.db.execute(select(Position, Asset).join(Asset, Asset.id == Position.asset_id)).all())
        investable = [
            (position, asset)
            for position, asset in rows
            if float(position.market_value or 0) > 0 and asset.asset_type.lower() not in {"cash", "stablecoin"}
        ]
        if not investable:
            raise PortfolioTimeSeriesRiskError("no non-cash positions with positive market value")

        total_value = sum(float(position.market_value or 0) for position, _ in investable)
        series = self._trusted_snapshot_series(data_snapshot_ids=data_snapshot_ids, lookback_days=lookback_days)
        errors: list[dict[str, str]] = []
        synced_rows = 0
        for _position, asset in investable:
            if asset.symbol not in series:
                errors.append({"symbol": asset.symbol, "error": "trusted_snapshot_symbol_missing"})

        if not series:
            raise PortfolioTimeSeriesRiskError("no position has enough daily candle history")

        included = [(position, asset) for position, asset in investable if asset.symbol in series]
        included_value = sum(float(position.market_value or 0) for position, _ in included)
        weights: dict[str, float] = defaultdict(float)
        for position, asset in included:
            weights[asset.symbol] += float(position.market_value or 0) / included_value
        returns = {symbol: daily_returns(candles) for symbol, candles in series.items()}
        common_dates = sorted(set.intersection(*(set(values) for values in returns.values())))
        if len(common_dates) < MIN_RETURN_OBSERVATIONS:
            raise PortfolioTimeSeriesRiskError(
                f"only {len(common_dates)} aligned return observations; at least {MIN_RETURN_OBSERVATIONS} required"
            )

        portfolio_returns = [
            sum(weights[symbol] * returns[symbol][day] for symbol in weights)
            for day in common_dates
        ]
        correlation = correlation_matrix(returns, common_dates)
        historical = value_at_risk(portfolio_returns)
        volatility = stdev(portfolio_returns) * math.sqrt(252) if len(portfolio_returns) > 1 else 0.0
        drawdown = drawdown_metrics(portfolio_returns)
        budget_limit = drawdown_budget_pct or self._drawdown_budget(user_id) or 0.15
        liquidity = [
            liquidity_metrics(position, asset, series[asset.symbol])
            for position, asset in included
        ]
        stress_tests = stress_scenarios(included, total_value, portfolio_returns)
        high_correlation_pairs = material_correlation_pairs(correlation, weights)
        account_map = {item.id: item for item in self.db.scalars(select(Account)).all()}
        exposures = portfolio_exposures(rows, account_map=account_map)
        factor_proxies = empirical_factor_proxies(included, returns=returns, portfolio_returns=dict(zip(common_dates, portfolio_returns)), weights=weights)
        external_exposures = {
            "exchanges": exposure_rows(list(self.db.scalars(select(ExchangeExposure).where(ExchangeExposure.user_id == user_id)).all()), "exchange_name"),
            "protocols": exposure_rows(list(self.db.scalars(select(ProtocolPosition)).all()), "protocol_name"),
            "stablecoins": exposure_rows(list(self.db.scalars(select(StablecoinExposure).where(StablecoinExposure.user_id == user_id)).all()), "symbol"),
            "note": "External read-only exposure tables are shown separately and are not added to portfolio_value to avoid double counting.",
        }
        coverage = included_value / total_value if total_value else 0.0
        as_of = max(candle.timestamp for candles in series.values() for candle in candles)
        previous_artifact = self.db.scalar(
            select(ExportArtifact)
            .where(
                ExportArtifact.user_id == user_id,
                ExportArtifact.export_type == "portfolio_time_series_risk",
            )
            .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
            .limit(1)
        )

        packet: dict[str, Any] = {
            "status": "VALID" if coverage >= 0.99 and not errors else "PARTIAL",
            "provider": "yfinance_public",
            "as_of": normalize_dt(as_of).isoformat(),
            "lookback_days": lookback_days,
            "observations": len(common_dates),
            "portfolio_value": round(total_value, 2),
            "market_data_rows_synced": synced_rows,
            "input_data_snapshot_ids": data_snapshot_ids,
            "coverage_pct": round(coverage * 100, 2),
            "included_symbols": sorted(series),
            "excluded": errors,
            "weights": {key: round(value, 6) for key, value in weights.items()},
            "annualized_volatility_pct": round(volatility * 100, 3),
            "var": historical,
            "drawdown": {
                **drawdown,
                "budget_limit_pct": round(budget_limit * 100, 3),
                "budget_used_pct": round(abs(drawdown["max_drawdown_pct"]) / (budget_limit * 100) * 100, 2)
                if budget_limit > 0
                else None,
            },
            "correlation_matrix": correlation,
            "high_correlation_pairs": high_correlation_pairs,
            "liquidity": liquidity,
            "liquidity_summary": {
                "max_normal_days": round(max((item["normal_liquidation_days"] for item in liquidity), default=0), 3),
                "max_stressed_days": round(max((item["stressed_liquidation_days"] for item in liquidity), default=0), 3),
            },
            "stress_tests": stress_tests,
            "exposures": exposures,
            "factor_proxies": factor_proxies,
            "external_exposures": external_exposures,
            "risk_changes": risk_change_evidence(
                previous_artifact.payload_json if previous_artifact is not None else None,
                {
                    "weights": weights,
                    "correlation_matrix": correlation,
                    "drawdown": {
                        "budget_used_pct": round(abs(drawdown["max_drawdown_pct"]) / (budget_limit * 100) * 100, 2)
                        if budget_limit > 0
                        else None,
                    },
                },
                previous_artifact_id=previous_artifact.id if previous_artifact is not None else None,
            ),
            "methodology": {
                "returns": "close-to-close daily simple returns; aligned dates; current market-value weights",
                "var": "historical one-day VaR and expected shortfall at 95% and 99%; parametric normal VaR shown for comparison",
                "drawdown": "compounded portfolio return curve over aligned observation window",
                "liquidity": "position quantity divided by 20-day average volume at 10% normal and 5% stressed participation",
                "limitations": "public read-only end-of-day data; no intraday gap, spread, market-impact, FX, or options convexity model",
                "classification": "sector, industry, theme, and factor tags come only from explicit asset classification fields with source provenance; no symbol/name inference",
                "overlapping_exposures": "theme and factor-tag buckets are non-exclusive and may sum above 100%",
            },
            "local_next_steps": RISK_LOCAL_NEXT_STEPS,
            "risk_gate": portfolio_risk_gate(
                {
                    "coverage_pct": round(coverage * 100, 2),
                    "observations": len(common_dates),
                    "excluded": errors,
                    "drawdown": {
                        "budget_used_pct": round(abs(drawdown["max_drawdown_pct"]) / (budget_limit * 100) * 100, 2)
                        if budget_limit > 0
                        else None,
                    },
                    "high_correlation_pairs": high_correlation_pairs,
                    "liquidity_summary": {
                        "max_stressed_days": round(max((item["stressed_liquidation_days"] for item in liquidity), default=0), 3),
                    },
                }
            ),
            "execution_available": False,
        }
        snapshot = DataSnapshot(
            snapshot_type="portfolio_risk_time_series",
            as_of=normalize_dt(as_of),
            data_json={"dates": [day.isoformat() for day in common_dates], "portfolio_returns": portfolio_returns},
            metadata_json={
                "provider": "yfinance_public",
                "symbols": sorted(series),
                "coverage_pct": packet["coverage_pct"],
                "read_only": True,
                "execution_available": False,
                "input_data_snapshot_ids": data_snapshot_ids,
            },
        )
        self.db.add(snapshot)
        self.db.flush()
        quality = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source="yfinance_public",
            metric_type="portfolio_time_series_coverage",
            score=coverage,
            details_json={
                "observations": len(common_dates),
                "included_symbols": sorted(series),
                "excluded": errors,
                "minimum_observations": MIN_RETURN_OBSERVATIONS,
            },
        )
        self.db.add(quality)
        self.db.flush()
        risk_catalog_entry = DataCatalogService(self.db).create_entry(
            dataset_type="portfolio_risk_time_series",
            source="portfolio_time_series_risk",
            source_ref=f"portfolio-risk:{user_id}",
            row_count=len(common_dates),
            snapshot=snapshot,
            quality_report=quality,
            lineage_json={
                "input_data_snapshot_ids": data_snapshot_ids,
                "provider": "yfinance_public",
                "symbols": sorted(series),
            },
            contract_json={
                "execution_available": False,
                "review_only": True,
                "input_snapshots_must_be_trusted": True,
            },
        )
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="portfolio_time_series_risk",
            format="json",
            status="ready" if packet["status"] == "VALID" else "partial",
            payload_json={
                **packet,
                "snapshot_id": snapshot.id,
                "quality_report_id": quality.id,
                "catalog_entry_id": risk_catalog_entry.id,
            },
            summary_json={
                "status": packet["status"],
                "coverage_pct": packet["coverage_pct"],
                "observations": len(common_dates),
                "var_95_pct": historical["historical_95"]["var_pct"],
                "max_drawdown_pct": drawdown["max_drawdown_pct"],
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        self._upsert_risk_reminders(user_id, artifact.id, packet)
        write_audit_log(
            self.db,
            action="portfolio_risk.time_series_analyzed",
            entity_type="ExportArtifact",
            entity_id=artifact.id,
            payload_json={
                "provider": "yfinance_public",
                "status": packet["status"],
                "coverage_pct": packet["coverage_pct"],
                "observations": len(common_dates),
                "execution_available": False,
            },
            actor_id=user_id,
        )
        self.db.commit()
        return {**artifact.payload_json, "artifact_id": artifact.id, "created_at": artifact.created_at.isoformat()}

    def _trusted_snapshot_series(self, *, data_snapshot_ids: list[str], lookback_days: int) -> dict[str, list[Any]]:
        service = DataCatalogService(self.db)
        series: dict[str, list[Any]] = {}
        for snapshot_id in dict.fromkeys(data_snapshot_ids):
            try:
                service.require_trusted_snapshot(snapshot_id, decision_scope="portfolio_risk")
            except DataTrustGateError as exc:
                raise PortfolioTimeSeriesRiskError(str(exc)) from exc
            snapshot = self.db.get(DataSnapshot, snapshot_id)
            rows = list(((snapshot.data_json if snapshot else {}) or {}).get("candles") or [])
            by_symbol: dict[str, list[Any]] = defaultdict(list)
            for row in rows:
                try:
                    by_symbol[str(row["symbol"])].append(
                        type(
                            "TrustedCandle",
                            (),
                            {
                                "timestamp": datetime.fromisoformat(str(row["timestamp"])),
                                "open": float(row["open"]),
                                "high": float(row["high"]),
                                "low": float(row["low"]),
                                "close": float(row["close"]),
                                "volume": float(row["volume"]),
                            },
                        )()
                    )
                except (KeyError, TypeError, ValueError):
                    raise PortfolioTimeSeriesRiskError(f"trusted snapshot {snapshot_id} contains invalid candle rows")
            for symbol, candles in by_symbol.items():
                candles.sort(key=lambda item: normalize_dt(item.timestamp))
                if len(candles) < MIN_RETURN_OBSERVATIONS + 1:
                    raise PortfolioTimeSeriesRiskError(
                        f"trusted snapshot has only {len(candles)} candles for {symbol}; at least {MIN_RETURN_OBSERVATIONS + 1} required"
                    )
                series[symbol] = candles[-(lookback_days + 1):]
        return series

    def _sync_asset(self, asset: Asset, limit: int) -> int:
        candles = self.adapter.get_candles(asset.symbol, "1d", limit)
        changed = 0
        for row in candles:
            timestamp = normalize_dt(row.timestamp)
            candle = self.db.scalar(
                select(Candle).where(
                    Candle.asset_id == asset.id,
                    Candle.timeframe == "1d",
                    Candle.timestamp == timestamp,
                    Candle.source == "yfinance_public",
                ).limit(1)
            )
            if candle is None:
                candle = Candle(asset_id=asset.id, timeframe="1d", timestamp=timestamp)
                self.db.add(candle)
            candle.open = row.open
            candle.high = row.high
            candle.low = row.low
            candle.close = row.close
            candle.volume = row.volume
            candle.source = "yfinance_public"
            changed += 1
        self.db.flush()
        return changed

    def _stored_candles(self, asset_id: str, limit: int) -> list[Candle]:
        rows = list(
            self.db.scalars(
                select(Candle)
                .where(Candle.asset_id == asset_id, Candle.timeframe == "1d")
                .order_by(Candle.timestamp.desc(), Candle.id.desc())
                .limit(limit + 1)
            ).all()
        )
        rows.reverse()
        by_day: dict[Any, Candle] = {}
        for candle in rows:
            by_day[normalize_dt(candle.timestamp).date()] = candle
        return [by_day[key] for key in sorted(by_day)]

    def _drawdown_budget(self, user_id: str) -> float | None:
        budgets = list(self.db.scalars(select(RiskBudget).where(RiskBudget.user_id == user_id)).all())
        limits = [float(item.max_loss_pct) for item in budgets if float(item.max_loss_pct or 0) > 0]
        if not limits:
            return None
        value = min(limits)
        return value / 100 if value > 1 else value

    def _upsert_risk_reminders(self, user_id: str, artifact_id: str, packet: dict[str, Any]) -> None:
        conditions: list[tuple[str, str, str, dict[str, Any]]] = []
        budget_used = packet["drawdown"].get("budget_used_pct") or 0
        if budget_used >= 80:
            conditions.append(("drawdown_budget", "High drawdown budget consumption", f"Historical maximum drawdown has consumed {budget_used:.1f}% of the configured budget.", {"current_budget_used_pct": budget_used, "threshold_pct": 80}))
        var_95 = packet["var"]["historical_95"]["var_pct"]
        if var_95 >= 3:
            conditions.append(("var_95", "Elevated one-day portfolio VaR", f"Historical 95% one-day VaR is {var_95:.2f}% of portfolio value.", {"current_var_pct": var_95, "threshold_pct": 3}))
        stressed_days = packet["liquidity_summary"]["max_stressed_days"]
        if stressed_days >= 5:
            conditions.append(("liquidity", "Stressed liquidity requires review", f"A position may require {stressed_days:.1f} days to liquidate at 5% ADV participation.", {"current_stressed_days": stressed_days, "threshold_days": 5}))
        if packet["high_correlation_pairs"]:
            pair = packet["high_correlation_pairs"][0]
            conditions.append(("correlation", "Material positions are highly correlated", f"{pair['left']} and {pair['right']} correlation is {pair['correlation']:.2f}.", {"pair": [pair["left"], pair["right"]], "current_correlation": pair["correlation"], "threshold": 0.8}))

        changes = packet.get("risk_changes") or {}
        concentration_change = changes.get("concentration") or {}
        if concentration_change.get("alert"):
            conditions.append(("concentration_drift", "Material position concentration increased", concentration_change["detail"], concentration_change))
        correlation_change = changes.get("correlation") or {}
        if correlation_change.get("alert"):
            conditions.append(("correlation_change", "Material correlation increased", correlation_change["detail"], correlation_change))
        drawdown_change = changes.get("drawdown_budget") or {}
        if drawdown_change.get("alert"):
            conditions.append(("drawdown_budget_change", "Drawdown budget consumption increased", drawdown_change["detail"], drawdown_change))

        candidates = list(self.db.scalars(
            select(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.reminder_type == "portfolio_risk",
            ).order_by(Reminder.created_at.desc()).limit(500)
        ).all())
        active_keys = {risk_key for risk_key, _title, _detail, _evidence in conditions}
        now = datetime.now(timezone.utc)
        for reminder in candidates:
            payload = reminder.payload_json or {}
            risk_key = payload.get("risk_key")
            if risk_key and payload.get("condition_active", True) and risk_key not in active_keys:
                if reminder.status in {"pending", "snoozed"}:
                    reminder.status = "done"
                    reminder.completed_at = now
                reminder.payload_json = {
                    **payload,
                    "condition_active": False,
                    "auto_resolved_at": now.isoformat(),
                    "resolved_by_artifact_id": artifact_id,
                    "resolution_reason": "latest_trusted_risk_analysis_no_longer_meets_alert_condition",
                }
                write_audit_log(
                    self.db,
                    action="portfolio_risk.reminder_auto_resolved",
                    entity_type="Reminder",
                    entity_id=reminder.id,
                    payload_json={"risk_key": risk_key, "artifact_id": artifact_id, "execution_available": False},
                    actor_id=user_id,
                )

        for risk_key, title, detail, evidence in conditions:
            existing = next((item for item in candidates if (item.payload_json or {}).get("risk_key") == risk_key and (item.payload_json or {}).get("condition_active", True)), None)
            if existing is not None:
                existing.title = title
                if existing.status in {"pending", "snoozed"}:
                    existing.due_at = now
                existing.payload_json = {**existing.payload_json, "detail": detail, "artifact_id": artifact_id, "evidence": evidence, "condition_active": True, "last_observed_at": now.isoformat()}
                continue
            self.db.add(
                Reminder(
                    user_id=user_id,
                    title=title,
                    reminder_type="portfolio_risk",
                    related_entity_type="ExportArtifact",
                    related_entity_id=artifact_id,
                    due_at=now,
                    priority="high",
                    status="pending",
                    payload_json={
                        "risk_key": risk_key,
                        "detail": detail,
                        "artifact_id": artifact_id,
                        "evidence": evidence,
                        "condition_active": True,
                        "first_observed_at": now.isoformat(),
                        "last_observed_at": now.isoformat(),
                        "route": "risk",
                        "execution_available": False,
                    },
                )
            )
        self.db.flush()


def normalize_dt(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def daily_returns(candles: list[Candle]) -> dict[Any, float]:
    values: dict[Any, float] = {}
    for previous, current in zip(candles, candles[1:]):
        previous_close = float(previous.close)
        if previous_close <= 0:
            continue
        values[normalize_dt(current.timestamp).date()] = float(current.close) / previous_close - 1
    return values


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def value_at_risk(returns: list[float]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    average = mean(returns)
    sigma = stdev(returns) if len(returns) > 1 else 0.0
    for confidence, z_value in ((0.95, 1.644853626951), (0.99, 2.326347874041)):
        threshold = quantile(returns, 1 - confidence)
        tail = [value for value in returns if value <= threshold]
        result[f"historical_{int(confidence * 100)}"] = {
            "var_pct": round(max(0.0, -threshold) * 100, 3),
            "expected_shortfall_pct": round(max(0.0, -mean(tail)) * 100, 3) if tail else 0.0,
            "parametric_var_pct": round(max(0.0, z_value * sigma - average) * 100, 3),
        }
    return result


def correlation_matrix(returns: dict[str, dict[Any, float]], dates: list[Any]) -> dict[str, dict[str, float]]:
    symbols = sorted(returns)
    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for left in symbols:
        for right in symbols:
            if left == right:
                value = 1.0
            else:
                left_values = [returns[left][day] for day in dates]
                right_values = [returns[right][day] for day in dates]
                value = pearson(left_values, right_values)
            matrix[left][right] = round(value, 4)
    return dict(matrix)


def pearson(left: list[float], right: list[float]) -> float:
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else 0.0


def drawdown_metrics(returns: list[float]) -> dict[str, float]:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
    current_drawdown = equity / peak - 1
    return {
        "current_drawdown_pct": round(current_drawdown * 100, 3),
        "max_drawdown_pct": round(max_drawdown * 100, 3),
    }


def liquidity_metrics(position: Position, asset: Asset, candles: list[Candle]) -> dict[str, Any]:
    recent = candles[-20:]
    adv_shares = mean([float(item.volume or 0) for item in recent]) if recent else 0.0
    quantity = abs(float(position.quantity or 0))
    normal_days = quantity / (adv_shares * 0.10) if adv_shares > 0 else 999.0
    stressed_days = quantity / (adv_shares * 0.05) if adv_shares > 0 else 999.0
    return {
        "symbol": asset.symbol,
        "quantity": round(quantity, 6),
        "average_daily_volume_20d": round(adv_shares, 2),
        "normal_participation_pct": 10,
        "normal_liquidation_days": round(normal_days, 3),
        "stressed_participation_pct": 5,
        "stressed_liquidation_days": round(stressed_days, 3),
        "status": "high" if stressed_days >= 5 else "watch" if stressed_days >= 2 else "normal",
    }


def stress_scenarios(rows: list[tuple[Position, Asset]], total_value: float, returns: list[float]) -> list[dict[str, Any]]:
    crypto_value = sum(float(position.market_value or 0) for position, asset in rows if asset.asset_type.lower() in {"crypto", "cryptocurrency"})
    equity_value = sum(float(position.market_value or 0) for position, asset in rows if asset.asset_type.lower() in {"stock", "etf", "equity"})
    worst_5d = min((sum(returns[index:index + 5]) for index in range(max(1, len(returns) - 4))), default=0.0)
    scenarios = [
        ("broad_risk_off", -(equity_value * 0.20 + crypto_value * 0.30), "Equities -20%, crypto -30%; static current weights."),
        ("crypto_shock", -(crypto_value * 0.40), "Crypto assets -40%; other assets unchanged."),
        ("historical_worst_5d", total_value * worst_5d, "Worst rolling five-session return in the aligned observation window."),
    ]
    return [
        {
            "scenario": name,
            "estimated_loss": round(loss, 2),
            "estimated_loss_pct": round(loss / total_value * 100, 3) if total_value else 0.0,
            "explanation": explanation,
        }
        for name, loss, explanation in scenarios
    ]


def portfolio_exposures(rows: list[tuple[Position, Asset]], *, account_map: dict[str, Account]) -> dict[str, Any]:
    positive = [(position, asset) for position, asset in rows if float(position.market_value or 0) > 0]
    total = sum(float(position.market_value or 0) for position, _ in positive)

    def buckets(values) -> list[dict[str, Any]]:
        grouped: dict[str, float] = defaultdict(float)
        for label, amount in values:
            grouped[str(label or "Unclassified")] += amount
        return [
            {"name": name, "market_value": round(value, 2), "weight_pct": round(value / total * 100, 3) if total else 0.0}
            for name, value in sorted(grouped.items(), key=lambda item: item[1], reverse=True)
        ]

    classified_value = sum(float(position.market_value or 0) for position, asset in positive if asset.classification_source and (asset.sector or asset.industry or asset.themes_json or asset.factor_tags_json))
    return {
        "by_asset_type": buckets((asset.asset_type, float(position.market_value or 0)) for position, asset in positive),
        "by_currency": buckets((asset.currency, float(position.market_value or 0)) for position, asset in positive),
        "by_market": buckets((asset.market, float(position.market_value or 0)) for position, asset in positive),
        "by_venue": buckets((asset.venue, float(position.market_value or 0)) for position, asset in positive),
        "by_account": buckets(((account_map.get(position.account_id).name if account_map.get(position.account_id) else "Unknown account"), float(position.market_value or 0)) for position, asset in positive),
        "by_sector": buckets((asset.sector or "Unclassified", float(position.market_value or 0)) for position, asset in positive),
        "by_industry": buckets((asset.industry or "Unclassified", float(position.market_value or 0)) for position, asset in positive),
        "by_theme": buckets((theme, float(position.market_value or 0)) for position, asset in positive for theme in (asset.themes_json or ["Unclassified"])),
        "by_factor_tag": buckets((tag, float(position.market_value or 0)) for position, asset in positive for tag in (asset.factor_tags_json or ["Unclassified"])),
        "classification_coverage_pct": round(classified_value / total * 100, 3) if total else 0.0,
        "classification_sources": sorted({str(asset.classification_source) for _, asset in positive if asset.classification_source}),
        "classification_snapshot_ids": sorted({str(asset.classification_snapshot_id) for _, asset in positive if asset.classification_snapshot_id}),
        "total_market_value": round(total, 2),
    }


def empirical_factor_proxies(
    rows: list[tuple[Position, Asset]],
    *,
    returns: dict[str, dict[Any, float]],
    portfolio_returns: dict[Any, float],
    weights: dict[str, float],
) -> dict[str, Any]:
    portfolio_values = list(portfolio_returns.values())
    portfolio_variance = variance(portfolio_values) if len(portfolio_values) > 1 else 0.0
    symbols = []
    for _position, asset in rows:
        values = returns.get(asset.symbol) or {}
        dates = sorted(set(values) & set(portfolio_returns))
        asset_values = [values[date] for date in dates]
        benchmark_values = [portfolio_returns[date] for date in dates]
        beta = covariance(asset_values, benchmark_values) / portfolio_variance if portfolio_variance > 0 and len(dates) > 1 else None
        volatility = stdev(asset_values) * math.sqrt(252) if len(asset_values) > 1 else None
        symbols.append({"symbol": asset.symbol, "portfolio_beta_proxy": round(beta, 4) if beta is not None else None, "annualized_volatility_pct": round(volatility * 100, 3) if volatility is not None else None, "weight_pct": round(weights.get(asset.symbol, 0) * 100, 3), "explicit_factor_tags": list(asset.factor_tags_json or []), "method": "beta to current portfolio return series; descriptive proxy, not a named factor-model estimate"})
    return {"by_symbol": symbols, "benchmark": "current_portfolio", "named_factor_model_available": False, "limitations": "No Fama-French or commercial factor dataset is configured; explicit tags are classifications, while beta/volatility are empirical proxies."}


def exposure_rows(rows: list[Any], label_field: str) -> list[dict[str, Any]]:
    grouped: dict[str, float] = defaultdict(float)
    for row in rows:
        grouped[str(getattr(row, label_field) or "Unknown")] += float(getattr(row, "usd_value", 0) or 0)
    total = sum(grouped.values())
    return [{"name": name, "usd_value": round(value, 2), "weight_pct": round(value / total * 100, 3) if total else 0.0} for name, value in sorted(grouped.items(), key=lambda item: item[1], reverse=True)]


def risk_change_evidence(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    previous_artifact_id: str | None,
) -> dict[str, Any]:
    thresholds = {
        "position_weight_increase_pp": 5.0,
        "position_min_current_weight_pct": 20.0,
        "correlation_increase": 0.15,
        "correlation_min_current": 0.70,
        "drawdown_budget_increase_pp": 10.0,
        "drawdown_budget_review_pct": 80.0,
    }
    if not previous:
        return {
            "status": "baseline_created",
            "previous_artifact_id": None,
            "concentration": {"alert": False, "detail": "No prior trusted risk analysis is available; this run establishes the concentration baseline."},
            "correlation": {"alert": False, "detail": "No prior trusted risk analysis is available; this run establishes the correlation baseline."},
            "drawdown_budget": {"alert": False, "detail": "No prior trusted risk analysis is available; this run establishes the drawdown-budget baseline."},
            "thresholds": thresholds,
            "methodology": "Compares consecutive trusted portfolio-risk artifacts for the same user; no change alert is inferred from a single run.",
        }

    previous_weights = {str(key): float(value or 0) for key, value in (previous.get("weights") or {}).items()}
    current_weights = {str(key): float(value or 0) for key, value in (current.get("weights") or {}).items()}
    weight_changes = [
        {
            "symbol": symbol,
            "previous_weight_pct": round(previous_weights.get(symbol, 0) * 100, 3),
            "current_weight_pct": round(current_weights.get(symbol, 0) * 100, 3),
            "change_pp": round((current_weights.get(symbol, 0) - previous_weights.get(symbol, 0)) * 100, 3),
        }
        for symbol in sorted(set(previous_weights) | set(current_weights))
    ]
    concentration_candidates = [
        row for row in weight_changes
        if row["change_pp"] >= thresholds["position_weight_increase_pp"]
        and row["current_weight_pct"] >= thresholds["position_min_current_weight_pct"]
    ]
    concentration_candidates.sort(key=lambda row: row["change_pp"], reverse=True)
    concentration_top = concentration_candidates[0] if concentration_candidates else None

    previous_matrix = previous.get("correlation_matrix") or {}
    current_matrix = current.get("correlation_matrix") or {}
    correlation_changes: list[dict[str, Any]] = []
    for index, left in enumerate(sorted(current_matrix)):
        for right in sorted(current_matrix)[index + 1:]:
            if left not in previous_matrix or right not in (previous_matrix.get(left) or {}):
                continue
            current_value = float((current_matrix.get(left) or {}).get(right) or 0)
            previous_value = float((previous_matrix.get(left) or {}).get(right) or 0)
            correlation_changes.append({
                "left": left,
                "right": right,
                "previous_correlation": round(previous_value, 4),
                "current_correlation": round(current_value, 4),
                "change": round(current_value - previous_value, 4),
            })
    correlation_candidates = [
        row for row in correlation_changes
        if row["change"] >= thresholds["correlation_increase"]
        and row["current_correlation"] >= thresholds["correlation_min_current"]
        and current_weights.get(row["left"], 0) >= 0.05
        and current_weights.get(row["right"], 0) >= 0.05
    ]
    correlation_candidates.sort(key=lambda row: row["change"], reverse=True)
    correlation_top = correlation_candidates[0] if correlation_candidates else None

    previous_budget = (previous.get("drawdown") or {}).get("budget_used_pct")
    current_budget = (current.get("drawdown") or {}).get("budget_used_pct")
    budget_change = float(current_budget) - float(previous_budget) if previous_budget is not None and current_budget is not None else None
    budget_alert = bool(
        budget_change is not None
        and budget_change >= thresholds["drawdown_budget_increase_pp"]
        and float(current_budget) >= thresholds["drawdown_budget_review_pct"]
    )

    return {
        "status": "compared",
        "previous_artifact_id": previous_artifact_id,
        "concentration": {
            "alert": concentration_top is not None,
            "top_change": concentration_top,
            "changes": weight_changes,
            "detail": (
                f"{concentration_top['symbol']} weight increased {concentration_top['change_pp']:.1f} percentage points to {concentration_top['current_weight_pct']:.1f}%."
                if concentration_top else "No position crossed the configured concentration-drift threshold."
            ),
        },
        "correlation": {
            "alert": correlation_top is not None,
            "top_change": correlation_top,
            "changes": correlation_changes,
            "detail": (
                f"{correlation_top['left']} / {correlation_top['right']} correlation increased {correlation_top['change']:.2f} to {correlation_top['current_correlation']:.2f}."
                if correlation_top else "No material pair crossed the configured correlation-change threshold."
            ),
        },
        "drawdown_budget": {
            "alert": budget_alert,
            "previous_budget_used_pct": float(previous_budget) if previous_budget is not None else None,
            "current_budget_used_pct": float(current_budget) if current_budget is not None else None,
            "change_pp": round(budget_change, 3) if budget_change is not None else None,
            "detail": (
                f"Drawdown budget consumption increased {budget_change:.1f} percentage points to {float(current_budget):.1f}%."
                if budget_alert else "Drawdown-budget consumption did not cross the configured change threshold."
            ),
        },
        "thresholds": thresholds,
        "methodology": "Compares consecutive trusted portfolio-risk artifacts for the same user. Weight changes are percentage-point changes; correlations use aligned daily returns from each artifact.",
    }


def variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = mean(values)
    return sum((value - average) ** 2 for value in values) / (len(values) - 1)


def covariance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = mean(left)
    right_mean = mean(right)
    return sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right)) / (len(left) - 1)


def material_correlation_pairs(matrix: dict[str, dict[str, float]], weights: dict[str, float]) -> list[dict[str, Any]]:
    symbols = sorted(matrix)
    pairs = []
    for index, left in enumerate(symbols):
        for right in symbols[index + 1:]:
            value = matrix[left][right]
            if value >= 0.85 and weights.get(left, 0) >= 0.05 and weights.get(right, 0) >= 0.05:
                pairs.append({"left": left, "right": right, "correlation": value})
    return sorted(pairs, key=lambda item: item["correlation"], reverse=True)
