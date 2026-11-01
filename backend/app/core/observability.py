from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from redis import Redis
from redis.exceptions import RedisError


class ObservabilityUnavailable(RuntimeError):
    pass


class RedisRequestMetrics:
    def __init__(self, settings, client: Any | None = None):
        self.settings = settings
        self.client = client or Redis.from_url(
            str(settings.redis_url),
            decode_responses=True,
            socket_connect_timeout=settings.dependency_check_timeout_seconds,
            socket_timeout=settings.dependency_check_timeout_seconds,
        )

    def record(self, *, status_code: int, duration_ms: float, observed_at: datetime | None = None) -> None:
        if not self.settings.observability_metrics_enabled:
            return
        observed_at = observed_at or datetime.now(timezone.utc)
        bucket = int(observed_at.timestamp() // 60)
        key = self._key(bucket)
        status_class = f"status_{max(1, min(5, status_code // 100))}xx"
        try:
            pipeline = self.client.pipeline(transaction=True)
            pipeline.hincrby(key, "requests", 1)
            pipeline.hincrby(key, status_class, 1)
            pipeline.hincrby(key, "errors", 1 if status_code >= 500 else 0)
            pipeline.hincrbyfloat(key, "duration_ms_total", max(0.0, float(duration_ms)))
            pipeline.expire(key, 60 * 60 * 48)
            pipeline.execute()
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise ObservabilityUnavailable("request metrics store unavailable") from exc

    def snapshot(self, *, window_hours: int = 24, now: datetime | None = None) -> dict[str, Any]:
        if not self.settings.observability_metrics_enabled:
            return self._unavailable(window_hours, "metrics_disabled")
        safe_hours = max(1, min(48, int(window_hours)))
        now = now or datetime.now(timezone.utc)
        current_bucket = int(now.timestamp() // 60)
        bucket_count = safe_hours * 60
        keys = [self._key(current_bucket - offset) for offset in range(bucket_count)]
        try:
            pipeline = self.client.pipeline(transaction=False)
            for key in keys:
                pipeline.hgetall(key)
            rows = pipeline.execute()
        except (RedisError, OSError, ValueError, TypeError) as exc:
            raise ObservabilityUnavailable("request metrics store unavailable") from exc

        totals: dict[str, float] = {
            "requests": 0,
            "errors": 0,
            "duration_ms_total": 0.0,
            "status_1xx": 0,
            "status_2xx": 0,
            "status_3xx": 0,
            "status_4xx": 0,
            "status_5xx": 0,
        }
        populated_buckets = 0
        for row in rows:
            if not row:
                continue
            populated_buckets += 1
            for field in totals:
                totals[field] += float(row.get(field) or 0)
        requests = int(totals["requests"])
        errors = int(totals["errors"])
        error_rate = errors / requests if requests else None
        availability = 1 - error_rate if error_rate is not None else None
        avg_latency_ms = totals["duration_ms_total"] / requests if requests else None
        sufficient = requests >= max(1, int(self.settings.observability_minimum_requests))
        targets_met = bool(
            sufficient
            and availability is not None
            and error_rate is not None
            and avg_latency_ms is not None
            and availability >= self.settings.slo_availability_target
            and error_rate <= self.settings.slo_error_rate_target
            and avg_latency_ms <= self.settings.slo_average_latency_ms_target
        )
        return {
            "status": "ok" if targets_met else "breached" if sufficient else "insufficient_data",
            "window_hours": safe_hours,
            "window_started_at": now - timedelta(hours=safe_hours),
            "generated_at": now,
            "requests": requests,
            "errors": errors,
            "error_rate": error_rate,
            "availability": availability,
            "average_latency_ms": round(avg_latency_ms, 3) if avg_latency_ms is not None else None,
            "status_counts": {key: int(value) for key, value in totals.items() if key.startswith("status_")},
            "populated_minute_buckets": populated_buckets,
            "minimum_requests": int(self.settings.observability_minimum_requests),
            "sample_sufficient": sufficient,
            "targets": {
                "availability": self.settings.slo_availability_target,
                "error_rate": self.settings.slo_error_rate_target,
                "average_latency_ms": self.settings.slo_average_latency_ms_target,
            },
            "source": "redis_http_request_metrics",
            "real_request_metrics": True,
        }

    def prometheus(self, snapshot: dict[str, Any]) -> str:
        def number(value: Any) -> str:
            return "NaN" if value is None else str(value)

        lines = [
            "# HELP ai_trading_os_http_requests_total Requests observed in the configured SLO window.",
            "# TYPE ai_trading_os_http_requests_total gauge",
            f"ai_trading_os_http_requests_total {snapshot.get('requests', 0)}",
            "# HELP ai_trading_os_http_errors_total HTTP 5xx responses observed in the SLO window.",
            "# TYPE ai_trading_os_http_errors_total gauge",
            f"ai_trading_os_http_errors_total {snapshot.get('errors', 0)}",
            "# HELP ai_trading_os_http_availability_ratio Successful response ratio in the SLO window.",
            "# TYPE ai_trading_os_http_availability_ratio gauge",
            f"ai_trading_os_http_availability_ratio {number(snapshot.get('availability'))}",
            "# HELP ai_trading_os_http_average_latency_ms Average request latency in milliseconds.",
            "# TYPE ai_trading_os_http_average_latency_ms gauge",
            f"ai_trading_os_http_average_latency_ms {number(snapshot.get('average_latency_ms'))}",
        ]
        return "\n".join(lines) + "\n"

    def _key(self, bucket: int) -> str:
        return f"atos:observability:http:{self.settings.service_name}:{bucket}"

    @staticmethod
    def _unavailable(window_hours: int, reason: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "window_hours": window_hours,
            "reason": reason,
            "requests": 0,
            "errors": 0,
            "error_rate": None,
            "availability": None,
            "average_latency_ms": None,
            "sample_sufficient": False,
            "real_request_metrics": False,
        }
