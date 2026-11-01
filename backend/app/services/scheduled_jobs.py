from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import Asset
from app.models import ScheduledJob
from app.services.data_sources import DataSourceError
from app.services.data_sources import DataSourceService
from app.services.signals import SignalEngineService


class ScheduledJobError(ValueError):
    pass


class ScheduledJobService:
    def __init__(self, db: Session):
        self.db = db

    def list_jobs(self, *, job_type: str | None = None, limit: int = 100) -> list[ScheduledJob]:
        query = select(ScheduledJob).order_by(ScheduledJob.created_at.desc(), ScheduledJob.id.desc()).limit(limit)
        if job_type:
            query = (
                select(ScheduledJob)
                .where(ScheduledJob.job_type == job_type)
                .order_by(ScheduledJob.created_at.desc(), ScheduledJob.id.desc())
                .limit(limit)
            )
        return list(self.db.scalars(query).all())

    def create_job(
        self,
        *,
        name: str,
        job_type: str,
        status: str,
        schedule_json: dict[str, Any],
        target_json: dict[str, Any],
    ) -> ScheduledJob:
        if job_type not in {"quote_import", "candle_import", "signal_generate"}:
            raise ScheduledJobError("only quote_import, candle_import, and signal_generate scheduled jobs are supported in this safe slice")
        self._validate_target(job_type, target_json)

        job = ScheduledJob(
            name=name,
            job_type=job_type,
            status=status,
            schedule_json=schedule_json or {"mode": "manual"},
            target_json=target_json,
            last_run_summary={},
        )
        self.db.add(job)
        self.db.flush()
        write_audit_log(
            self.db,
            action="scheduled_job.created",
            entity_type="ScheduledJob",
            entity_id=job.id,
            payload_json={"job_type": job.job_type, "status": job.status, "execution_available": False},
            actor_id="p2-scheduled-job-service",
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_job(self, job_id: str) -> tuple[ScheduledJob, dict[str, Any]]:
        job = self.db.get(ScheduledJob, job_id)
        if not job:
            raise ScheduledJobError("scheduled job not found")
        if job.job_type not in {"quote_import", "candle_import", "signal_generate"}:
            raise ScheduledJobError("unsupported scheduled job type")

        target = job.target_json
        try:
            summary = self._run_target(job.job_type, target)
            job.last_run_status = "succeeded"
        except (DataSourceError, KeyError, TypeError, ValueError) as exc:
            summary = {"error": str(exc), "execution_available": False}
            job.last_run_status = "failed"

        job.last_run_at = datetime.now(timezone.utc)
        job.last_run_summary = summary
        self.db.add(job)
        self.db.flush()
        write_audit_log(
            self.db,
            action="scheduled_job.run",
            entity_type="ScheduledJob",
            entity_id=job.id,
            payload_json={"job_type": job.job_type, "status": job.last_run_status, "summary": summary},
            actor_id="p2-scheduled-job-service",
        )
        self.db.commit()
        self.db.refresh(job)
        return job, summary

    def _validate_target(self, job_type: str, target_json: dict[str, Any]) -> None:
        symbols = target_json.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            raise ScheduledJobError(f"{job_type} jobs require non-empty target_json.symbols")
        if job_type in {"quote_import", "candle_import"}:
            connection_id = target_json.get("connection_id")
            if not connection_id:
                raise ScheduledJobError(f"{job_type} jobs require target_json.connection_id")
        if job_type == "candle_import":
            timeframe = target_json.get("timeframe", "1d")
            limit = target_json.get("limit", 30)
            if timeframe not in {"1d", "1h"}:
                raise ScheduledJobError("candle_import jobs require target_json.timeframe to be 1d or 1h")
            if not isinstance(limit, int) or limit < 1 or limit > 365:
                raise ScheduledJobError("candle_import jobs require target_json.limit between 1 and 365")
        if job_type == "signal_generate":
            signal_types = target_json.get("signal_types")
            horizon = target_json.get("horizon", "swing")
            if not isinstance(symbols, list) or not symbols:
                raise ScheduledJobError("signal_generate jobs require non-empty target_json.symbols")
            if not isinstance(signal_types, list) or not signal_types:
                raise ScheduledJobError("signal_generate jobs require non-empty target_json.signal_types")
            if horizon not in {"intraday", "swing", "long_term"}:
                raise ScheduledJobError("signal_generate jobs require target_json.horizon to be intraday, swing, or long_term")

    def _run_target(self, job_type: str, target: dict[str, Any]) -> dict[str, Any]:
        data_sources = DataSourceService(self.db)
        if job_type == "quote_import":
            result = data_sources.import_quotes(
                str(target["connection_id"]),
                symbols=[str(symbol) for symbol in target["symbols"]],
                asset_type=str(target.get("asset_type", "stock")),
                market=str(target.get("market", "US")),
                venue=target.get("venue"),
                currency=str(target.get("currency", "USD")),
            )
            return {
                "quotes_imported": result.quotes_imported,
                "symbols": result.symbols,
                "skipped": result.skipped,
                "snapshot_id": result.snapshot.id,
                "quality_report_id": result.quality_report.id,
                "execution_available": False,
            }

        if job_type == "signal_generate":
            symbols = [str(symbol).upper() for symbol in target["symbols"]]
            signal_types = [str(signal_type) for signal_type in target["signal_types"]]
            horizon = str(target.get("horizon", "swing"))
            market_facts = target.get("market_facts")
            onchain_facts = target.get("onchain_facts")

            signals_generated = 0
            generated_assets: list[str] = []
            skipped: list[dict[str, str]] = []
            generated_signal_ids: list[str] = []
            signal_engine = SignalEngineService(self.db)

            for symbol in symbols:
                asset = self.db.scalar(select(Asset).where(Asset.symbol == symbol).limit(1))
                if asset is None:
                    skipped.append({"symbol": symbol, "error": "asset_not_found"})
                    continue

                signals = signal_engine.generate(
                    asset_id=asset.id,
                    candles=[],
                    signal_types=signal_types,
                    horizon=horizon,
                    market_facts=market_facts if isinstance(market_facts, dict) else {},
                    onchain_facts=onchain_facts if isinstance(onchain_facts, dict) else {},
                )
                signals_generated += len(signals)
                generated_assets.append(symbol)
                generated_signal_ids.extend(signal.id for signal in signals)

            if signals_generated == 0:
                raise ScheduledJobError("signal_generate produced no signals")

            return {
                "signals_generated": signals_generated,
                "symbols": generated_assets,
                "signal_types": signal_types,
                "horizon": horizon,
                "signal_ids": generated_signal_ids,
                "skipped": skipped,
                "execution_available": False,
            }

        result = data_sources.import_candles(
            str(target["connection_id"]),
            symbols=[str(symbol) for symbol in target["symbols"]],
            timeframe=str(target.get("timeframe", "1d")),
            limit=int(target.get("limit", 30)),
            asset_type=str(target.get("asset_type", "stock")),
            market=str(target.get("market", "US")),
            venue=target.get("venue"),
            currency=str(target.get("currency", "USD")),
        )
        return {
            "candles_imported": result.candles_imported,
            "symbols": result.symbols,
            "timeframe": result.timeframe,
            "skipped": result.skipped,
            "snapshot_id": result.snapshot.id,
            "quality_report_id": result.quality_report.id,
            "execution_available": False,
        }
