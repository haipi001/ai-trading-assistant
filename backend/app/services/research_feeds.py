from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.request import Request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.market_data_readonly import open_readonly_url
from app.api.domain import write_audit_log
from app.core.config import Settings
from app.core.config import get_settings
from app.models import Asset
from app.models import Candle
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import ExportArtifact
from app.models import InvestmentThesis
from app.models import ThesisCheckpoint


class ResearchFeedError(ValueError):
    pass


class ResearchFeedService:
    def __init__(self, db: Session, *, settings: Settings | None = None, fetch_text=None):
        self.db = db
        self.settings = settings or get_settings()
        self.fetch_text = fetch_text or self._fetch_text

    def sync_nasdaq_news(self, *, symbols: list[str], limit_per_symbol: int = 10) -> dict:
        normalized = normalize_symbols(symbols)
        articles, errors = [], []
        for symbol in normalized:
            query = urlencode({"q": f"{symbol}|stocks", "limit": max(1, min(limit_per_symbol, 50)), "offset": 0})
            try:
                payload = json.loads(self.fetch_text(f"https://api.nasdaq.com/api/news/topic/articlebysymbol?{query}", nasdaq_headers(), self.settings.external_api_timeout_seconds))
                rows = ((payload.get("data") or {}).get("rows") or [])
                for row in rows:
                    articles.append({"symbol": symbol, "title": row.get("title"), "description": row.get("description"), "publisher": row.get("publisher"), "published_at": row.get("created"), "url": f"https://www.nasdaq.com{row.get('url')}" if str(row.get("url") or "").startswith("/") else row.get("url"), "related_symbols": row.get("related_symbols") or []})
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)})
        return self._finish("news", "nasdaq_public_news", {"articles": articles, "errors": errors}, len(articles), errors, {"schema": "news_article_v1", "citations_required": True})

    def latest_news(self) -> dict:
        """Read the latest persisted feed without implying a fresh network fetch."""
        snapshot = self.db.scalar(select(DataSnapshot).where(DataSnapshot.snapshot_type == "news").order_by(DataSnapshot.created_at.desc(), DataSnapshot.id.desc()).limit(1))
        checked_at = datetime.now(timezone.utc)
        if snapshot is None:
            return {"status": "missing", "articles": [], "fetched_at": None, "checked_at": checked_at.isoformat(), "age_seconds": None, "stale": True, "execution_available": False}
        fetched_at = _as_utc(snapshot.created_at)
        age = max(0, (checked_at - fetched_at).total_seconds())
        data = snapshot.data_json or {}
        return {"status": "partial" if data.get("errors") else "ready", "provider": (snapshot.metadata_json or {}).get("provider"), "snapshot_id": snapshot.id, "articles": data.get("articles") or [], "fetched_at": fetched_at.isoformat(), "checked_at": checked_at.isoformat(), "age_seconds": round(age, 3), "stale": age > 300, "refresh_interval_seconds": 60, "errors_count": len(data.get("errors") or []), "execution_available": False}

    def sync_sec_filings_and_fundamentals(self, *, symbols: list[str], limit_per_symbol: int = 12) -> dict:
        normalized = normalize_symbols(symbols)
        mapping_payload = json.loads(self.fetch_text("https://www.sec.gov/files/company_tickers.json", sec_headers(self.settings), self.settings.external_api_timeout_seconds))
        ticker_map = {str(item.get("ticker") or "").upper(): int(item["cik_str"]) for item in mapping_payload.values() if isinstance(item, dict) and item.get("ticker") and item.get("cik_str") is not None}
        filings, fundamentals, errors = [], [], []
        for symbol in normalized:
            cik = ticker_map.get(symbol)
            if cik is None:
                errors.append({"symbol": symbol, "error": "SEC CIK unavailable"})
                continue
            cik_text = f"{cik:010d}"
            try:
                submission = json.loads(self.fetch_text(f"https://data.sec.gov/submissions/CIK{cik_text}.json", sec_headers(self.settings), self.settings.external_api_timeout_seconds))
                recent = ((submission.get("filings") or {}).get("recent") or {})
                forms = recent.get("form") or []
                for index in range(min(len(forms), max(1, min(limit_per_symbol, 50)))):
                    accession = recent.get("accessionNumber", [None] * len(forms))[index]
                    primary = recent.get("primaryDocument", [None] * len(forms))[index]
                    accession_path = str(accession or "").replace("-", "")
                    filings.append({"symbol": symbol, "company": submission.get("name"), "cik": cik_text, "form": forms[index], "filing_date": recent.get("filingDate", [None] * len(forms))[index], "report_date": recent.get("reportDate", [None] * len(forms))[index], "accession_number": accession, "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/{primary}" if accession and primary else None})
                facts_payload = json.loads(self.fetch_text(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_text}.json", sec_headers(self.settings), self.settings.external_api_timeout_seconds))
                fundamentals.append({"symbol": symbol, "company": facts_payload.get("entityName"), "facts": summarize_sec_facts(facts_payload)})
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)})
        return self._finish("sec_filings_fundamentals", "sec_edgar", {"filings": filings, "fundamentals": fundamentals, "errors": errors}, len(filings) + len(fundamentals), errors, {"schema": "sec_filings_fundamentals_v1", "official_source": True, "citations_required": True})

    def sync_fred_macro(self, *, series: list[str] | None = None, history_limit: int = 120) -> dict:
        requested = list(dict.fromkeys((series or ["DGS10", "DGS2", "FEDFUNDS", "CPIAUCSL", "UNRATE"])))
        observations, errors = {}, []
        for series_id in requested:
            if not re.fullmatch(r"[A-Z0-9_\-]{1,32}", series_id):
                errors.append({"series": series_id, "error": "invalid series id"})
                continue
            try:
                body = self.fetch_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={quote(series_id)}", {"Accept": "text/csv", "User-Agent": "ai-trading-os-readonly/0.1"}, self.settings.external_api_timeout_seconds)
                rows = [row for row in csv.DictReader(io.StringIO(body)) if row.get(series_id) not in {None, "", "."}]
                observations[series_id] = [{"date": row.get("observation_date"), "value": float(row[series_id])} for row in rows[-max(1, min(history_limit, 1000)):]]
            except Exception as exc:
                errors.append({"series": series_id, "error": str(exc)})
        count = sum(len(items) for items in observations.values())
        return self._finish("macro_series", "fred_public_csv", {"series": observations, "errors": errors}, count, errors, {"schema": "fred_observation_v1", "source_agency": "Federal Reserve Bank of St. Louis"})

    def sync_onchain_metrics(self, *, metrics: list[str] | None = None, timespan: str = "90days") -> dict:
        allowlist = {"n-transactions", "hash-rate", "n-unique-addresses", "mempool-size", "estimated-transaction-volume-usd"}
        requested = list(dict.fromkeys(metrics or ["n-transactions", "hash-rate", "n-unique-addresses"]))
        values, errors = {}, []
        if not re.fullmatch(r"(?:30|60|90|180|365)days|[12]years", timespan):
            raise ResearchFeedError("unsupported on-chain timespan")
        for metric in requested:
            if metric not in allowlist:
                errors.append({"metric": metric, "error": "metric not allowlisted"})
                continue
            try:
                payload = json.loads(self.fetch_text(f"https://api.blockchain.info/charts/{metric}?{urlencode({'timespan': timespan, 'format': 'json'})}", {"Accept": "application/json", "User-Agent": "ai-trading-os-readonly/0.1"}, self.settings.external_api_timeout_seconds))
                values[metric] = {"name": payload.get("name"), "unit": payload.get("unit"), "period": payload.get("period"), "values": payload.get("values") or []}
            except Exception as exc:
                errors.append({"metric": metric, "error": str(exc)})
        count = sum(len(item["values"]) for item in values.values())
        return self._finish("onchain_metrics", "blockchain_info_public", {"network": "bitcoin", "metrics": values, "errors": errors}, count, errors, {"schema": "bitcoin_chart_metric_v1", "read_only": True})

    def sync_catalyst_calendar(self, *, symbols: list[str], days: int = 14) -> dict:
        normalized = set(normalize_symbols(symbols))
        events, errors = [], []
        start = datetime.now(timezone.utc).date()
        for offset in range(max(1, min(days, 31))):
            event_date = start + timedelta(days=offset)
            try:
                payload = json.loads(self.fetch_text(f"https://api.nasdaq.com/api/calendar/earnings?date={event_date.isoformat()}", nasdaq_headers(), self.settings.external_api_timeout_seconds))
                for row in ((payload.get("data") or {}).get("rows") or []):
                    symbol = str(row.get("symbol") or "").upper()
                    if normalized and symbol not in normalized:
                        continue
                    events.append({"event_type": "earnings", "date": event_date.isoformat(), "symbol": symbol, "title": f"{symbol} earnings", "time": row.get("time"), "fiscal_quarter_ending": row.get("fiscalQuarterEnding"), "eps_forecast": row.get("epsForecast"), "source_url": f"https://www.nasdaq.com/market-activity/earnings"})
            except Exception as exc:
                errors.append({"date": event_date.isoformat(), "error": str(exc)})
        for snapshot in self._latest_snapshots("corporate_actions", limit=5):
            for item in (snapshot.data_json.get("events") or []):
                symbol = str(item.get("symbol") or "").upper()
                if normalized and symbol not in normalized:
                    continue
                for date_key, event_type in [("ex_date", "dividend_ex_date"), ("payment_date", "dividend_payment")]:
                    parsed = parse_us_date(item.get(date_key))
                    if parsed and start <= parsed <= start + timedelta(days=days):
                        events.append({"event_type": event_type, "date": parsed.isoformat(), "symbol": symbol, "title": f"{symbol} cash dividend", "amount_per_share": item.get("amount_per_share"), "source_url": "https://www.nasdaq.com/market-activity/dividends"})
        events.sort(key=lambda item: (item.get("date") or "", item.get("symbol") or "", item.get("event_type") or ""))
        return self._finish("catalyst_calendar", "aggregated_public_catalysts", {"start_date": start.isoformat(), "days": days, "symbols": sorted(normalized), "events": events, "errors": errors}, len(events), errors, {"schema": "catalyst_event_v1", "requires_human_review": True}, allow_empty=True)

    def overview(self) -> dict:
        dataset_types = research_dataset_types()
        items = []
        for dataset_type in dataset_types:
            snapshot = self.db.scalar(select(DataSnapshot).where(DataSnapshot.snapshot_type == dataset_type).order_by(DataSnapshot.created_at.desc(), DataSnapshot.id.desc()).limit(1))
            items.append({
                "dataset_type": dataset_type,
                "label": research_dataset_label(dataset_type),
                "status": "ready" if snapshot else "missing",
                "snapshot_id": snapshot.id if snapshot else None,
                "as_of": snapshot.created_at.isoformat() if snapshot and snapshot.created_at else None,
                "row_count": snapshot.metadata_json.get("row_count", 0) if snapshot else 0,
                "source": snapshot.metadata_json.get("provider") if snapshot else None,
                "action_label": research_dataset_action(dataset_type),
                "route": "/?module=investment_logic&tab=ai&research_tab=feeds",
            })
        ready_count = sum(1 for item in items if item["status"] == "ready")
        missing = [item["dataset_type"] for item in items if item["status"] != "ready"]
        first_missing = next((item for item in items if item["status"] != "ready"), None)
        local_next_steps = research_local_next_steps(items)
        thesis_gate = research_thesis_gate(items=items, missing=missing)
        return {
            "items": items,
            "ready_count": ready_count,
            "total_count": len(items),
            "status": "ready_for_thesis_review" if not missing else "action_required",
            "missing": missing,
            "local_next_steps": local_next_steps,
            "thesis_gate": thesis_gate,
            "next_action": first_missing["action_label"] if first_missing else "打开研究报告并复查 Thesis",
            "safe_boundary": "研究 feed 只生成只读证据、报告和 Thesis checkpoint，不会创建订单、审批计划或交易。",
            "execution_available": False,
            "production_capability": False,
        }

    def evidence_packet(self, *, user_id: str = "default-user") -> dict:
        generated_at = datetime.now(timezone.utc)
        overview = self.overview()
        packet = {
            "packet_type": "research_feed_evidence_packet",
            "user_id": user_id,
            "generated_at": generated_at.isoformat(),
            **overview,
            "contains_secrets": False,
            "production_capability": False,
            "execution_available": False,
            "safe_boundaries": [
                "read_only_research_feeds_only",
                "no_order_submission",
                "no_auto_approval",
                "no_gate_bypass",
                "no_external_llm_call_from_feed_packet",
                "reports_require_human_thesis_review",
            ],
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="research_feed_evidence_packet",
            format="json",
            status=packet["status"],
            payload_json=packet,
            summary_json={
                "ready_count": packet["ready_count"],
                "total_count": packet["total_count"],
                "missing": packet["missing"],
                "contains_secrets": False,
                "production_capability": False,
            },
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        write_audit_log(
            self.db,
            action="research_feed.evidence_packet_created",
            entity_type="ExportArtifact",
            entity_id=artifact.id,
            payload_json={"ready_count": packet["ready_count"], "total_count": packet["total_count"], "missing": packet["missing"], "execution_available": False},
            actor_id="research-feed-service",
        )
        self.db.commit()
        return packet

    def thesis_delta(self, thesis_id: str) -> dict:
        """What changed since this thesis was last reviewed?

        Baseline = the newest ThesisCheckpoint, else thesis creation. Compares
        the baseline against locally stored evidence only (candles + already
        synced research-feed snapshots) — no network calls, so the report is
        reproducible and fail-closed: feeds that were never synced are reported
        `missing`, feeds synced before the baseline are `stale_since_baseline`.
        Review-only: the human decides supports/weakens/invalidates via a
        checkpoint; nothing here touches orders or gates."""
        thesis = self.db.get(InvestmentThesis, thesis_id)
        if thesis is None:
            raise ResearchFeedError("investment thesis not found")
        asset = self.db.get(Asset, thesis.asset_id)
        symbol = str(asset.symbol or "").upper() if asset else ""
        checkpoint = self.db.scalar(
            select(ThesisCheckpoint)
            .where(ThesisCheckpoint.thesis_id == thesis.id)
            .order_by(ThesisCheckpoint.created_at.desc(), ThesisCheckpoint.id.desc())
            .limit(1)
        )
        baseline_at = _as_utc(checkpoint.created_at if checkpoint else thesis.created_at)
        baseline_source = "last_checkpoint" if checkpoint else "thesis_created"
        flags: list[str] = []
        next_actions: list[str] = []

        # --- Price delta from locally stored candles (the hard number). ---
        candles = list(
            self.db.scalars(
                select(Candle)
                .where(Candle.asset_id == thesis.asset_id, Candle.timeframe == "1d")
                .order_by(Candle.timestamp.asc(), Candle.id.asc())
            ).all()
        )
        price_delta: dict | None = None
        if candles:
            baseline_candle = None
            for candle in candles:
                if _as_utc(candle.timestamp) <= baseline_at:
                    baseline_candle = candle
            reference = baseline_candle or candles[0]
            latest = candles[-1]
            ref_close = float(reference.close)
            latest_close = float(latest.close)
            change_pct = ((latest_close - ref_close) / ref_close) * 100 if ref_close else 0.0
            max_loss_pct = float(thesis.max_loss_tolerance_pct) * 100
            breached = change_pct <= -max_loss_pct if max_loss_pct > 0 else False
            if breached:
                flags.append("max_loss_tolerance_pressure")
                next_actions.append(
                    f"Price is {change_pct:.2f}% vs baseline, beyond the stated max loss tolerance ({max_loss_pct:.2f}%). Record a checkpoint and decide whether the thesis is invalidated."
                )
            price_delta = {
                "baseline_close": round(ref_close, 6),
                "baseline_close_at": _as_utc(reference.timestamp).isoformat(),
                "baseline_is_pre_thesis": baseline_candle is None,
                "latest_close": round(latest_close, 6),
                "latest_close_at": _as_utc(latest.timestamp).isoformat(),
                "change_pct": round(change_pct, 6),
                "max_loss_tolerance_pct": round(max_loss_pct, 6),
                "max_loss_tolerance_breached": breached,
            }
        else:
            flags.append("no_local_candles")
            next_actions.append("Import or sync 1d candles for this asset so the delta report has a price baseline.")

        # --- New facts per research feed, from stored snapshots only. ---
        baseline_date = baseline_at.date().isoformat()
        feeds: dict[str, dict] = {}

        def feed_snapshot(dataset_type: str) -> DataSnapshot | None:
            return self.db.scalar(
                select(DataSnapshot)
                .where(DataSnapshot.snapshot_type == dataset_type)
                .order_by(DataSnapshot.created_at.desc(), DataSnapshot.id.desc())
                .limit(1)
            )

        def feed_status(snapshot: DataSnapshot | None) -> str:
            if snapshot is None:
                return "missing"
            if _as_utc(snapshot.created_at) <= baseline_at:
                return "stale_since_baseline"
            return "fresh"

        news = feed_snapshot("news")
        news_items = []
        if news is not None:
            for article in (news.data_json.get("articles") or []):
                related = [str(item).upper() for item in (article.get("related_symbols") or [])]
                if symbol and (str(article.get("symbol") or "").upper() == symbol or symbol in related):
                    news_items.append({"title": article.get("title"), "publisher": article.get("publisher"), "published_at": article.get("published_at"), "url": article.get("url")})
        feeds["news"] = {"status": feed_status(news), "synced_at": _as_utc(news.created_at).isoformat() if news else None, "snapshot_id": news.id if news else None, "source_credibility": credibility("nasdaq_public_news", official=False), "new_items_for_symbol": len(news_items), "sample": news_items[:5]}

        sec = feed_snapshot("sec_filings_fundamentals")
        new_filings = []
        fundamentals_summary = None
        if sec is not None:
            for filing in (sec.data_json.get("filings") or []):
                if str(filing.get("symbol") or "").upper() == symbol and str(filing.get("filing_date") or "") > baseline_date:
                    new_filings.append({"form": filing.get("form"), "filing_date": filing.get("filing_date"), "url": filing.get("url")})
            for item in (sec.data_json.get("fundamentals") or []):
                if str(item.get("symbol") or "").upper() == symbol:
                    fundamentals_summary = item.get("facts")
        if new_filings:
            flags.append("new_sec_filings_since_baseline")
            next_actions.append(f"{len(new_filings)} new SEC filing(s) since the baseline — review them against the thesis drivers.")
        feeds["sec_filings_fundamentals"] = {"status": feed_status(sec), "synced_at": _as_utc(sec.created_at).isoformat() if sec else None, "snapshot_id": sec.id if sec else None, "source_credibility": credibility("sec_edgar", official=True), "new_filings_since_baseline": new_filings[:10], "fundamentals": fundamentals_summary}

        macro = feed_snapshot("macro_series")
        macro_deltas = {}
        if macro is not None:
            for series_id, observations in (macro.data_json.get("series") or {}).items():
                usable = [obs for obs in observations if obs.get("value") is not None]
                if not usable:
                    continue
                baseline_obs = None
                for obs in usable:
                    if str(obs.get("date") or "") <= baseline_date:
                        baseline_obs = obs
                latest_obs = usable[-1]
                macro_deltas[series_id] = {
                    "baseline": baseline_obs,
                    "latest": latest_obs,
                    "delta": round(float(latest_obs["value"]) - float(baseline_obs["value"]), 6) if baseline_obs else None,
                }
        feeds["macro_series"] = {"status": feed_status(macro), "synced_at": _as_utc(macro.created_at).isoformat() if macro else None, "snapshot_id": macro.id if macro else None, "source_credibility": credibility("fred_public_csv", official=True), "series_deltas": macro_deltas}

        catalysts = feed_snapshot("catalyst_calendar")
        upcoming = []
        if catalysts is not None:
            for event in (catalysts.data_json.get("events") or []):
                if str(event.get("symbol") or "").upper() == symbol:
                    upcoming.append({"event_type": event.get("event_type"), "date": event.get("date"), "title": event.get("title")})
        if upcoming:
            flags.append("upcoming_catalysts")
        feeds["catalyst_calendar"] = {"status": feed_status(catalysts), "synced_at": _as_utc(catalysts.created_at).isoformat() if catalysts else None, "snapshot_id": catalysts.id if catalysts else None, "source_credibility": credibility("aggregated_public_catalysts", official=False), "upcoming_for_symbol": upcoming[:10]}

        if asset is not None and str(asset.asset_type or "").lower() == "crypto":
            onchain = feed_snapshot("onchain_metrics")
            onchain_deltas = {}
            if onchain is not None:
                baseline_unix = baseline_at.timestamp()
                for metric, payload in (onchain.data_json.get("metrics") or {}).items():
                    points = [point for point in (payload.get("values") or []) if point.get("y") is not None]
                    if not points:
                        continue
                    baseline_point = None
                    for point in points:
                        if float(point.get("x") or 0) <= baseline_unix:
                            baseline_point = point
                    latest_point = points[-1]
                    onchain_deltas[metric] = {
                        "baseline": baseline_point,
                        "latest": latest_point,
                        "delta": round(float(latest_point["y"]) - float(baseline_point["y"]), 6) if baseline_point else None,
                    }
            feeds["onchain_metrics"] = {"status": feed_status(onchain), "synced_at": _as_utc(onchain.created_at).isoformat() if onchain else None, "snapshot_id": onchain.id if onchain else None, "source_credibility": credibility("blockchain_info_public", official=False), "metric_deltas": onchain_deltas}

        snapshots = [item for item in [news, sec, macro, catalysts, locals().get("onchain")] if item is not None]
        evidence_conflicts = detect_evidence_conflicts(snapshots, symbol=symbol)
        evidence_timeline = build_evidence_timeline(
            symbol=symbol,
            news_items=news_items,
            filings=new_filings,
            macro_deltas=macro_deltas,
            catalysts=upcoming,
            onchain_deltas=(feeds.get("onchain_metrics") or {}).get("metric_deltas") or {},
        )
        if evidence_conflicts:
            flags.append("conflicting_evidence")
            next_actions.append(f"Resolve {len(evidence_conflicts)} conflicting evidence field(s) before recording a deterministic thesis verdict.")

        stale_or_missing = sorted(name for name, feed in feeds.items() if feed["status"] != "fresh")
        if stale_or_missing:
            next_actions.append(f"Re-sync stale/missing feeds before concluding: {', '.join(stale_or_missing)}.")
        if not next_actions:
            next_actions.append("Record a thesis checkpoint with your supports/weakens/invalidates verdict on this evidence.")

        report = {
            "thesis_id": thesis.id,
            "asset_id": thesis.asset_id,
            "symbol": symbol or None,
            "thesis_status": thesis.status,
            "entry_reason": thesis.entry_reason,
            "key_drivers": thesis.key_drivers_json,
            "invalidation_conditions": thesis.invalidation_conditions_json,
            "baseline_at": baseline_at.isoformat(),
            "baseline_source": baseline_source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "price_delta": price_delta,
            "feeds": feeds,
            "evidence_timeline": evidence_timeline,
            "evidence_conflicts": evidence_conflicts,
            "conflict_count": len(evidence_conflicts),
            "flags": dedupe_flags(flags),
            "next_actions": next_actions,
            "review_only": True,
            "execution_available": False,
            "checkpoint_required_for_conclusion": True,
        }
        write_audit_log(
            self.db,
            action="research_feed.thesis_delta_generated",
            entity_type="InvestmentThesis",
            entity_id=thesis.id,
            payload_json={"baseline_source": baseline_source, "flags": report["flags"], "stale_or_missing_feeds": stale_or_missing, "conflict_count": len(evidence_conflicts), "execution_available": False},
            actor_id="research-feed-service",
        )
        self.db.commit()
        return report

    def _finish(self, dataset_type: str, source: str, data: dict, row_count: int, errors: list, contract: dict, *, allow_empty: bool = False) -> dict:
        if row_count <= 0 and not allow_empty:
            raise ResearchFeedError(f"{source} returned no usable rows")
        quality_score = (1.0 if not errors else 0.0) if allow_empty and row_count == 0 else row_count / max(row_count + len(errors), 1)
        fetched_at = datetime.now(timezone.utc)
        content_hash = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        snapshot = DataSnapshot(snapshot_type=dataset_type, data_json=data, metadata_json={"provider": source, "row_count": row_count, "content_hash": content_hash, "fetched_at": fetched_at.isoformat(), "read_only": True, "execution_available": False})
        self.db.add(snapshot); self.db.flush()
        quality = DataQualityReport(data_snapshot_id=snapshot.id, source=source, metric_type=f"{dataset_type}_quality", score=quality_score, details_json={"rows_received": row_count, "errors": errors[:25], "content_hash": content_hash, "execution_available": False})
        self.db.add(quality); self.db.flush()
        catalog = DataCatalogEntry(dataset_type=dataset_type, source=source, source_ref=source, data_snapshot_id=snapshot.id, quality_report_id=quality.id, row_count=row_count, quality_status="VALID" if quality_score >= 0.8 else "PARTIAL", usable_for_trading=False, lineage_json={"content_hash": content_hash, "fetched_at": fetched_at.isoformat(), "read_only": True}, contract_json={**contract, "execution_available": False})
        self.db.add(catalog); self.db.flush()
        write_audit_log(self.db, action="research_feed.synced", entity_type="DataSnapshot", entity_id=snapshot.id, payload_json={"dataset_type": dataset_type, "source": source, "row_count": row_count, "errors": len(errors), "execution_available": False}, actor_id="research-feed-service")
        self.db.commit()
        return {"dataset_type": dataset_type, "provider": source, "row_count": row_count, "quality_status": catalog.quality_status, "snapshot_id": snapshot.id, "quality_report_id": quality.id, "catalog_entry_id": catalog.id, "data": data, "execution_available": False}

    def _latest_snapshots(self, snapshot_type: str, *, limit: int) -> list[DataSnapshot]:
        return list(self.db.scalars(select(DataSnapshot).where(DataSnapshot.snapshot_type == snapshot_type).order_by(DataSnapshot.created_at.desc()).limit(limit)).all())

    @staticmethod
    def _fetch_text(url: str, headers: dict[str, str], timeout: float) -> str:
        try:
            with open_readonly_url(Request(url, headers=headers, method="GET"), timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise ResearchFeedError("research feed request failed") from exc


def _as_utc(value: datetime) -> datetime:
    """Normalize naive (sqlite) and aware (postgres) datetimes to aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def dedupe_flags(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def credibility(source: str, *, official: bool) -> dict:
    return {
        "source": source,
        "tier": "primary_official" if official else "public_secondary",
        "score": 1.0 if official else 0.7,
        "human_review_required": not official,
        "method": "source-class policy; not a factual-correctness score",
    }


def detect_evidence_conflicts(snapshots: list[DataSnapshot], *, symbol: str) -> list[dict]:
    claims: list[dict] = []
    for snapshot in snapshots:
        provider = str((snapshot.metadata_json or {}).get("provider") or snapshot.snapshot_type)
        for claim in snapshot.data_json.get("claims") or []:
            entity = str(claim.get("entity") or "").upper()
            if symbol and entity not in {symbol, "GLOBAL", "MACRO", "BITCOIN"}:
                continue
            if claim.get("field") is None or claim.get("value") is None:
                continue
            claims.append({"entity": entity, "field": str(claim["field"]), "as_of": str(claim.get("as_of") or "unknown"), "value": claim["value"], "source": str(claim.get("source") or provider), "snapshot_id": snapshot.id, "source_url": claim.get("source_url")})
        if snapshot.snapshot_type == "sec_filings_fundamentals":
            for item in snapshot.data_json.get("fundamentals") or []:
                if symbol and str(item.get("symbol") or "").upper() != symbol:
                    continue
                for field, fact in (item.get("facts") or {}).items():
                    if not isinstance(fact, dict) or fact.get("value") is None:
                        continue
                    claims.append({"entity": str(item.get("symbol") or symbol).upper(), "field": f"fundamental.{field}", "as_of": str(fact.get("period_end") or fact.get("filed") or "unknown"), "value": fact["value"], "source": provider, "snapshot_id": snapshot.id, "source_url": None})
                    for observation in fact.get("recent_observations") or []:
                        if observation.get("value") is None:
                            continue
                        claims.append({"entity": str(item.get("symbol") or symbol).upper(), "field": f"fundamental.{field}", "as_of": str(observation.get("period_end") or "unknown"), "value": observation["value"], "source": f"{provider}:{observation.get('accession_number') or observation.get('filed')}", "snapshot_id": snapshot.id, "source_url": None})
        elif snapshot.snapshot_type == "macro_series":
            for series, observations in (snapshot.data_json.get("series") or {}).items():
                for observation in observations:
                    if observation.get("value") is not None:
                        claims.append({"entity": "MACRO", "field": str(series), "as_of": str(observation.get("date") or "unknown"), "value": observation["value"], "source": provider, "snapshot_id": snapshot.id, "source_url": None})
        elif snapshot.snapshot_type == "onchain_metrics":
            for metric, payload in (snapshot.data_json.get("metrics") or {}).items():
                for point in payload.get("values") or []:
                    if point.get("y") is not None:
                        claims.append({"entity": "BITCOIN", "field": str(metric), "as_of": str(point.get("x") or "unknown"), "value": point["y"], "source": provider, "snapshot_id": snapshot.id, "source_url": None})
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for claim in claims:
        grouped.setdefault((claim["entity"], claim["field"], claim["as_of"]), []).append(claim)
    conflicts = []
    for (entity, field, as_of), rows in grouped.items():
        distinct = {json.dumps(row["value"], ensure_ascii=False, sort_keys=True) for row in rows}
        if len(distinct) <= 1:
            continue
        conflicts.append({
            "entity": entity,
            "field": field,
            "as_of": as_of,
            "claims": rows,
            "resolution_status": "human_review_required",
            "deterministic_conclusion_allowed": False,
        })
    return sorted(conflicts, key=lambda item: (item["entity"], item["field"], item["as_of"]))[:50]


def build_evidence_timeline(*, symbol: str, news_items: list[dict], filings: list[dict], macro_deltas: dict, catalysts: list[dict], onchain_deltas: dict) -> list[dict]:
    items: list[dict] = []
    for row in news_items:
        items.append({"at": row.get("published_at"), "type": "news", "title": row.get("title"), "source": row.get("publisher"), "url": row.get("url")})
    for row in filings:
        items.append({"at": row.get("filing_date"), "type": "sec_filing", "title": f"{symbol} {row.get('form')}", "source": "SEC EDGAR", "url": row.get("url")})
    for series, delta in macro_deltas.items():
        latest = delta.get("latest") or {}
        items.append({"at": latest.get("date"), "type": "macro", "title": f"{series}: {latest.get('value')}", "source": "FRED", "url": None})
    for row in catalysts:
        items.append({"at": row.get("date"), "type": "catalyst", "title": row.get("title"), "source": "public catalyst calendar", "url": None})
    for metric, delta in onchain_deltas.items():
        latest = delta.get("latest") or {}
        timestamp = latest.get("x")
        at = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat() if timestamp else None
        items.append({"at": at, "type": "onchain", "title": f"{metric}: {latest.get('y')}", "source": "blockchain.info", "url": None})
    return sorted((item for item in items if item.get("at")), key=lambda item: str(item["at"]), reverse=True)[:100]


def normalize_symbols(symbols: list[str]) -> list[str]:
    return list(dict.fromkeys(item.upper().strip() for item in symbols if re.fullmatch(r"[A-Za-z0-9.\-]{1,16}", item.strip())))


def research_dataset_types() -> list[str]:
    return ["news", "sec_filings_fundamentals", "macro_series", "onchain_metrics", "catalyst_calendar"]


def research_dataset_label(dataset_type: str) -> str:
    labels = {
        "news": "新闻证据",
        "sec_filings_fundamentals": "公告与财报",
        "macro_series": "宏观序列",
        "onchain_metrics": "链上指标",
        "catalyst_calendar": "Catalyst Calendar",
    }
    return labels.get(dataset_type, dataset_type)


def research_dataset_action(dataset_type: str) -> str:
    actions = {
        "news": "同步新闻",
        "sec_filings_fundamentals": "同步 SEC 公告与财报",
        "macro_series": "同步宏观序列",
        "onchain_metrics": "同步链上指标",
        "catalyst_calendar": "生成 Catalyst Calendar",
    }
    return actions.get(dataset_type, "同步研究证据")


def research_local_next_steps(items: list[dict]) -> list[dict]:
    by_type = {item["dataset_type"]: item for item in items}
    definitions = [
        ("news", "同步新闻", "先拉取关注资产新闻，给 Thesis 复查提供最新事件。", "同步新闻"),
        ("sec_filings_fundamentals", "同步公告与财报", "SEC filings 和基础财务事实用于验证原始投资理由。", "同步 SEC 公告与财报"),
        ("macro_series", "同步宏观序列", "利率、通胀、就业等宏观序列用于解释组合环境。", "同步宏观序列"),
        ("onchain_metrics", "同步链上指标", "BTC 链上指标用于加密资产风险和叙事复查。", "同步链上指标"),
        ("catalyst_calendar", "生成 Catalyst Calendar", "把财报、股息和事件日期变成可复查日历。", "生成 Catalyst Calendar"),
        ("evidence_packet", "生成研究证据包", "汇总所有研究 feed 的 snapshot 和质量证据，供人工复查。", "下载研究证据包"),
    ]
    all_ready = all((by_type.get(key) or {}).get("status") == "ready" for key in research_dataset_types())
    steps = []
    for key, label, default_detail, action_label in definitions:
        if key == "evidence_packet":
            status = "ready" if all_ready else "blocked"
            detail = default_detail if all_ready else "先补齐新闻、公告/财报、宏观、链上和日历证据，再生成完整证据包。"
        else:
            source = by_type.get(key)
            status = "ready" if source and source.get("status") == "ready" else "action_required"
            detail = source.get("label") + "已同步，可用于报告复查。" if status == "ready" and source else default_detail
        steps.append({
            "key": key,
            "label": label,
            "status": status,
            "detail": detail,
            "action_label": action_label,
            "route": "/?module=investment_logic&tab=ai&research_tab=feeds",
            "execution_available": False,
        })
    return steps


def research_thesis_gate(*, items: list[dict], missing: list[str]) -> dict:
    required_for_report = ["news", "sec_filings_fundamentals", "macro_series", "catalyst_calendar"]
    ready = {item["dataset_type"] for item in items if item["status"] == "ready"}
    missing_required = [key for key in required_for_report if key not in ready]
    onchain_ready = "onchain_metrics" in ready
    return {
        "status": "ready_for_thesis_review" if not missing_required else "blocked",
        "ready_required": [key for key in required_for_report if key in ready],
        "missing_required": missing_required,
        "onchain_context_ready": onchain_ready,
        "can_open_research_report": not missing_required,
        "can_create_thesis_delta": not missing_required,
        "can_create_trade_plan": False,
        "can_unlock_order_approval": False,
        "detail": (
            "研究证据足够进入报告和 Thesis delta 复查；交易计划仍需人工 Thesis、计划和风险审查。"
            if not missing_required
            else "研究证据仍不完整，只能停留在 feed 同步和人工预检。"
        ),
        "next_action": "打开研究报告并复查 Thesis" if not missing_required else "补齐缺失研究证据",
        "execution_available": False,
    }


def nasdaq_headers() -> dict[str, str]:
    return {"Accept": "application/json", "User-Agent": "Mozilla/5.0 ai-trading-os-readonly/0.1"}


def sec_headers(settings: Settings) -> dict[str, str]:
    return {"Accept": "application/json", "User-Agent": settings.sec_user_agent}


def summarize_sec_facts(payload: dict) -> dict:
    us_gaap = ((payload.get("facts") or {}).get("us-gaap") or {})
    candidates = {
        "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
        "net_income": ["NetIncomeLoss"],
        "diluted_eps": ["EarningsPerShareDiluted"],
        "assets": ["Assets"],
        "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    }
    result = {}
    for label, keys in candidates.items():
        fact = next((us_gaap.get(key) for key in keys if us_gaap.get(key)), None)
        if not fact:
            continue
        units = fact.get("units") or {}
        rows = next(iter(units.values()), [])
        valid = [row for row in rows if row.get("val") is not None and row.get("filed")]
        if valid:
            latest = max(valid, key=lambda row: (row.get("filed") or "", row.get("end") or ""))
            recent = sorted(valid, key=lambda row: (row.get("filed") or "", row.get("end") or ""), reverse=True)[:10]
            result[label] = {
                "value": latest.get("val"),
                "unit": next(iter(units.keys()), None),
                "period_end": latest.get("end"),
                "filed": latest.get("filed"),
                "form": latest.get("form"),
                "accession_number": latest.get("accn"),
                "recent_observations": [
                    {"value": row.get("val"), "period_end": row.get("end"), "filed": row.get("filed"), "form": row.get("form"), "accession_number": row.get("accn")}
                    for row in recent
                ],
            }
    return result


def parse_us_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%m/%d/%Y").date()
    except ValueError:
        return None
