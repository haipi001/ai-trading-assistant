from datetime import datetime
from datetime import timezone

import pytest

from app.core.config import Settings
from app.core.observability import RedisRequestMetrics


class FakePipeline:
    def __init__(self, store):
        self.store = store
        self.operations = []

    def hincrby(self, key, field, amount):
        self.operations.append(("hincrby", key, field, amount))
        return self

    def hincrbyfloat(self, key, field, amount):
        self.operations.append(("hincrbyfloat", key, field, amount))
        return self

    def expire(self, key, seconds):
        self.operations.append(("expire", key, seconds))
        return self

    def hgetall(self, key):
        self.operations.append(("hgetall", key))
        return self

    def execute(self):
        results = []
        for operation in self.operations:
            if operation[0] in {"hincrby", "hincrbyfloat"}:
                _, key, field, amount = operation
                row = self.store.setdefault(key, {})
                row[field] = float(row.get(field, 0)) + float(amount)
                results.append(row[field])
            elif operation[0] == "expire":
                results.append(True)
            else:
                _, key = operation
                results.append(dict(self.store.get(key, {})))
        return results


class FakeRedis:
    def __init__(self):
        self.store = {}

    def pipeline(self, transaction=True):
        return FakePipeline(self.store)


def settings(**updates) -> Settings:
    return Settings(
        observability_metrics_enabled=True,
        observability_minimum_requests=3,
        slo_availability_target=0.99,
        slo_error_rate_target=0.01,
        slo_average_latency_ms_target=250,
        **updates,
    )


def test_real_request_metrics_report_insufficient_data_without_samples() -> None:
    report = RedisRequestMetrics(settings(), client=FakeRedis()).snapshot(
        window_hours=1,
        now=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert report["status"] == "insufficient_data"
    assert report["availability"] is None
    assert report["real_request_metrics"] is True
    assert report["sample_sufficient"] is False


def test_request_metrics_use_http_traffic_and_detect_slo_breach() -> None:
    client = FakeRedis()
    metrics = RedisRequestMetrics(settings(), client=client)
    observed_at = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    metrics.record(status_code=200, duration_ms=100, observed_at=observed_at)
    metrics.record(status_code=201, duration_ms=200, observed_at=observed_at)
    metrics.record(status_code=503, duration_ms=300, observed_at=observed_at)

    report = metrics.snapshot(window_hours=1, now=observed_at)

    assert report["status"] == "breached"
    assert report["requests"] == 3
    assert report["errors"] == 1
    assert report["availability"] == pytest.approx(2 / 3)
    assert report["average_latency_ms"] == 200
    assert report["status_counts"]["status_2xx"] == 2
    assert report["status_counts"]["status_5xx"] == 1


def test_request_metrics_can_prove_slo_when_sample_is_sufficient() -> None:
    client = FakeRedis()
    metrics = RedisRequestMetrics(settings(), client=client)
    observed_at = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    for duration in (80, 100, 120):
        metrics.record(status_code=200, duration_ms=duration, observed_at=observed_at)

    report = metrics.snapshot(window_hours=1, now=observed_at)

    assert report["status"] == "ok"
    assert report["sample_sufficient"] is True
    assert report["availability"] == 1
    assert report["error_rate"] == 0


def test_prometheus_export_contains_no_request_dimensions_or_customer_data() -> None:
    metrics = RedisRequestMetrics(settings(), client=FakeRedis())
    payload = metrics.prometheus(
        {
            "requests": 4,
            "errors": 1,
            "availability": 0.75,
            "average_latency_ms": 125.0,
        }
    )

    assert "ai_trading_os_http_requests_total 4" in payload
    assert "ai_trading_os_http_errors_total 1" in payload
    assert "user_id" not in payload
    assert "path=" not in payload
