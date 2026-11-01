from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import get_settings
from app.core.observability import ObservabilityUnavailable
from app.core.observability import RedisRequestMetrics


request_logger = logging.getLogger("ai_trading_os.request")


class SafeRequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request logs that never include query, headers, body, or exception text."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        status_code = 500
        outcome = "error"
        error_type: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            outcome = "ok" if status_code < 500 else "error"
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", None) or "unmatched"
            event = {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "route": route_template,
                "status_code": status_code,
                "outcome": outcome,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            if error_type:
                event["error_type"] = error_type
            request_logger.info(json.dumps(event, separators=(",", ":"), sort_keys=True))
            settings = get_settings()
            if settings.observability_metrics_enabled:
                try:
                    RedisRequestMetrics(settings).record(status_code=status_code, duration_ms=event["duration_ms"])
                except ObservabilityUnavailable:
                    request_logger.error(
                        json.dumps(
                            {"event": "request_metrics_unavailable", "request_id": request_id},
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    )
