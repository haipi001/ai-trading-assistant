from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.db.session import get_session_factory
from app.models import ScheduledJob
from app.models import OperationalEvent
from app.services.data_sources import DataSourceService
from app.services.product_completion import ProductCompletionService
from app.services.ops_readiness import OpsReadinessService


PRODUCT_JOB_ACTIONS = {
    "product_daily_open": "daily_open",
    "product_continuous_reminders": "refresh_reminders",
    "product_daily_close": "daily_close",
    "product_research_eval": "research_eval",
}
ACCOUNT_SYNC_JOB_TYPE = "account_readonly_sync"
OBSERVABILITY_JOB_TYPE = "observability_slo_check"


class RuntimeSchedulerService:
    def __init__(self, db: Session):
        self.db = db

    def run_due_jobs_once(self, *, current_time: datetime | None = None) -> dict:
        observed_at = current_time or datetime.now(timezone.utc)
        jobs = list(
            self.db.scalars(
                select(ScheduledJob)
                .where(
                    ScheduledJob.status == "active",
                    ScheduledJob.job_type.in_([*PRODUCT_JOB_ACTIONS, ACCOUNT_SYNC_JOB_TYPE, OBSERVABILITY_JOB_TYPE]),
                )
                .order_by(ScheduledJob.created_at.asc(), ScheduledJob.id.asc())
            ).all()
        )
        results = []
        for job in jobs:
            if job.job_type == ACCOUNT_SYNC_JOB_TYPE:
                if not account_sync_is_due(job, observed_at):
                    continue
                results.append(self._run_account_sync_job(job=job, observed_at=observed_at))
                continue
            timezone_name = str((job.schedule_json or {}).get("timezone") or "Asia/Shanghai")
            local_time = observed_at.astimezone(ZoneInfo(timezone_name))
            cron = str((job.schedule_json or {}).get("cron") or "")
            if not cron_is_due(cron, local_time) or ran_in_same_schedule_window(job.last_run_at, observed_at, cron, timezone_name):
                continue
            if job.job_type == OBSERVABILITY_JOB_TYPE:
                results.append(self._run_observability_job(job=job, observed_at=observed_at))
                continue
            actor = AuthenticatedUser(
                user_id=str((job.target_json or {}).get("user_id") or "default-user"),
                role="owner",
                permissions=ROLE_PERMISSIONS["owner"],
                auth_required=False,
                token_configured=False,
            )
            try:
                packet = ProductCompletionService(self.db).scheduler_tick(
                    actor=actor,
                    action=PRODUCT_JOB_ACTIONS[job.job_type],
                )
                job.last_run_status = "succeeded"
                job.last_run_summary = packet
            except Exception as exc:
                self.db.rollback()
                job = self.db.get(ScheduledJob, job.id)
                if job is None:
                    continue
                job.last_run_status = "failed"
                job.last_run_summary = {"error": str(exc), "execution_available": False}
            job.last_run_at = observed_at
            self.db.add(job)
            self.db.commit()
            results.append({"job_id": job.id, "job_type": job.job_type, "status": job.last_run_status})
        return {"observed_at": observed_at, "jobs_scanned": len(jobs), "jobs_run": len(results), "results": results, "execution_available": False}

    def _run_observability_job(self, *, job: ScheduledJob, observed_at: datetime) -> dict:
        user_id = str((job.target_json or {}).get("user_id") or "default-user")
        try:
            result = OpsReadinessService(self.db).evaluate_observability_alert(user_id=user_id)
            job.last_run_status = "succeeded"
            job.last_run_summary = {
                "evaluated_at": observed_at.isoformat(),
                "slo_status": result["status"],
                "alert_created": result["alert_created"],
                "alerts_resolved": result["alerts_resolved"],
                "external_notification_delivered": result["notification"]["external_notification_delivered"],
                "external_delivery_status": result["notification"]["external_delivery"]["status"],
                "execution_available": False,
            }
        except Exception as exc:
            self.db.rollback()
            job = self.db.get(ScheduledJob, job.id)
            if job is None:
                return {"job_id": None, "job_type": OBSERVABILITY_JOB_TYPE, "status": "missing"}
            job.last_run_status = "failed"
            job.last_run_summary = {
                "evaluated_at": observed_at.isoformat(),
                "error_code": type(exc).__name__,
                "error_message": "Observability evaluation failed closed.",
                "execution_available": False,
            }
        job.last_run_at = observed_at
        self.db.add(job)
        self.db.commit()
        return {"job_id": job.id, "job_type": job.job_type, "status": job.last_run_status}

    def _run_account_sync_job(self, *, job: ScheduledJob, observed_at: datetime) -> dict:
        target = dict(job.target_json or {})
        policy = dict((job.schedule_json or {}).get("retry_policy") or {})
        user_id = str(target.get("user_id") or "default-user")
        connection_id = str(target.get("connection_id") or "")
        previous = dict(job.last_run_summary or {})
        prior_failures = int(previous.get("consecutive_failures") or 0)
        try:
            result = DataSourceService(self.db).sync_account_snapshot(connection_id, user_id=user_id, trigger="scheduler")
            job = self.db.get(ScheduledJob, job.id) or job
            job.last_run_at = observed_at
            job.last_run_status = "succeeded"
            job.last_run_summary = {
                "attempted_at": observed_at.isoformat(),
                "consecutive_failures": 0,
                "next_retry_at": None,
                "connection_id": connection_id,
                "snapshot_id": result.snapshot.id,
                "quality_report_id": result.quality_report.id,
                "catalog_entry_id": result.catalog_entry.id,
                "reconciliation_run_id": result.reconciliation["run_id"],
                "reconciliation_status": result.reconciliation["status"],
                "execution_available": False,
            }
            self.db.add(job)
            self.db.add(OperationalEvent(
                user_id=user_id,
                event_type="data_source.account_sync_succeeded",
                severity="info",
                source="runtime-scheduler",
                message="Read-only account refresh completed.",
                status="resolved",
                payload_json={
                    "job_id": job.id,
                    "connection_id": connection_id,
                    "attempted_at": observed_at.isoformat(),
                    "snapshot_id": result.snapshot.id,
                    "quality_report_id": result.quality_report.id,
                    "catalog_entry_id": result.catalog_entry.id,
                    "reconciliation_run_id": result.reconciliation["run_id"],
                    "execution_available": False,
                },
            ))
            self.db.commit()
            return {"job_id": job.id, "job_type": job.job_type, "status": "succeeded"}
        except Exception as exc:
            self.db.rollback()
            job = self.db.get(ScheduledJob, job.id)
            if job is None:
                return {"job_id": None, "job_type": ACCOUNT_SYNC_JOB_TYPE, "status": "missing"}
            failures = prior_failures + 1
            base_seconds = max(5, int(policy.get("base_seconds") or 30))
            max_seconds = max(base_seconds, int(policy.get("max_seconds") or 1800))
            delay_seconds = min(max_seconds, base_seconds * (2 ** min(16, max(0, failures - 1))))
            next_retry_at = observed_at.timestamp() + delay_seconds
            next_retry = datetime.fromtimestamp(next_retry_at, tz=timezone.utc)
            job.last_run_at = observed_at
            job.last_run_status = "retry_scheduled"
            job.last_run_summary = {
                "attempted_at": observed_at.isoformat(),
                "consecutive_failures": failures,
                "retry_delay_seconds": delay_seconds,
                "next_retry_at": next_retry.isoformat(),
                "connection_id": connection_id,
                "error_code": type(exc).__name__,
                "error_message": "Read-only provider unavailable or rejected the sync.",
                "execution_available": False,
            }
            self.db.add(job)
            self.db.add(OperationalEvent(
                user_id=user_id,
                event_type="data_source.account_sync_failed",
                severity="warning",
                source="runtime-scheduler",
                message="Read-only account refresh failed; a bounded retry was scheduled.",
                status="open",
                payload_json={
                    "job_id": job.id,
                    "connection_id": connection_id,
                    "attempted_at": observed_at.isoformat(),
                    "consecutive_failures": failures,
                    "retry_delay_seconds": delay_seconds,
                    "next_retry_at": next_retry.isoformat(),
                    "error_code": type(exc).__name__,
                    "execution_available": False,
                },
            ))
            self.db.commit()
            return {"job_id": job.id, "job_type": job.job_type, "status": "retry_scheduled", "next_retry_at": next_retry.isoformat()}


def cron_is_due(cron: str, local_time: datetime) -> bool:
    fields = cron.split()
    if len(fields) != 5:
        return False
    minute, hour, _day, _month, weekday = fields
    return (
        cron_field_matches(minute, local_time.minute)
        and cron_field_matches(hour, local_time.hour)
        and weekday_matches(weekday, local_time.weekday())
    )


def cron_field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    if field.startswith("*/"):
        try:
            return value % int(field[2:]) == 0
        except (ValueError, ZeroDivisionError):
            return False
    try:
        return value == int(field)
    except ValueError:
        return False


def weekday_matches(field: str, python_weekday: int) -> bool:
    if field == "*":
        return True
    cron_weekday = (python_weekday + 1) % 7
    if "-" in field:
        try:
            start, end = (int(item) for item in field.split("-", 1))
            return start <= cron_weekday <= end
        except ValueError:
            return False
    try:
        return cron_weekday == int(field) % 7
    except ValueError:
        return False


def ran_in_same_schedule_window(last_run_at: datetime | None, observed_at: datetime, cron: str, timezone_name: str) -> bool:
    if last_run_at is None:
        return False
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)
    previous = last_run_at.astimezone(ZoneInfo(timezone_name))
    current = observed_at.astimezone(ZoneInfo(timezone_name))
    if cron.startswith("*/"):
        interval = int(cron.split()[0][2:])
        return previous.date() == current.date() and previous.hour == current.hour and previous.minute // interval == current.minute // interval
    return previous.year == current.year and previous.month == current.month and previous.day == current.day and previous.hour == current.hour and previous.minute == current.minute


def account_sync_is_due(job: ScheduledJob, observed_at: datetime) -> bool:
    schedule = dict(job.schedule_json or {})
    summary = dict(job.last_run_summary or {})
    minimum_interval_seconds = max(5, int(schedule.get("minimum_interval_seconds") or 60))
    if job.last_run_at is not None:
        last_run_at = job.last_run_at
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
        if (observed_at - last_run_at).total_seconds() < minimum_interval_seconds:
            return False
    next_retry_raw = summary.get("next_retry_at")
    if next_retry_raw:
        try:
            next_retry_at = datetime.fromisoformat(str(next_retry_raw))
            if next_retry_at.tzinfo is None:
                next_retry_at = next_retry_at.replace(tzinfo=timezone.utc)
            return observed_at >= next_retry_at
        except ValueError:
            return False
    interval_minutes = max(5, int(schedule.get("interval_minutes") or 15))
    if job.last_run_at is None:
        return True
    last_run_at = job.last_run_at
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)
    if schedule.get("mode") == "interval":
        return (observed_at - last_run_at).total_seconds() >= interval_minutes * 60
    timezone_name = str(schedule.get("timezone") or "Asia/Shanghai")
    cron = str(schedule.get("cron") or "*/15 * * * *")
    local_time = observed_at.astimezone(ZoneInfo(timezone_name))
    return cron_is_due(cron, local_time) and not ran_in_same_schedule_window(job.last_run_at, observed_at, cron, timezone_name)


async def run_runtime_scheduler(stop_event: asyncio.Event, *, poll_seconds: int) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(5, poll_seconds))
            continue
        except TimeoutError:
            pass
        db = get_session_factory()()
        try:
            RuntimeSchedulerService(db).run_due_jobs_once()
        finally:
            db.close()
