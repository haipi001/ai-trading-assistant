import json
import logging

from fastapi import FastAPI
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.safe_logging import SafeRequestLoggingMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SafeRequestLoggingMiddleware)

    @app.post("/safe")
    async def safe(request: Request):
        await request.body()
        return {"ok": True}

    @app.get("/failure")
    def failure():
        raise RuntimeError("provider failed with secret-value-that-must-not-log")

    return app


def _request_events(caplog) -> list[dict]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "ai_trading_os.request"
    ]


def test_safe_request_log_excludes_query_headers_and_body(caplog) -> None:
    caplog.set_level(logging.INFO, logger="ai_trading_os.request")
    response = TestClient(_app()).post(
        "/safe?token=query-secret-value",
        headers={"Authorization": "Bearer header-secret-value"},
        json={"api_key": "body-secret-value"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    events = _request_events(caplog)
    assert len(events) == 1
    event = events[0]
    assert event["route"] == "/safe"
    assert event["method"] == "POST"
    assert event["status_code"] == 200
    serialized = json.dumps(event)
    assert "query-secret-value" not in serialized
    assert "header-secret-value" not in serialized
    assert "body-secret-value" not in serialized


def test_safe_request_log_records_only_exception_type(caplog) -> None:
    caplog.set_level(logging.INFO, logger="ai_trading_os.request")
    response = TestClient(_app(), raise_server_exceptions=False).get("/failure?password=do-not-log")

    assert response.status_code == 500
    events = _request_events(caplog)
    assert len(events) == 1
    event = events[0]
    assert event["error_type"] == "RuntimeError"
    serialized = json.dumps(event)
    assert "provider failed" not in serialized
    assert "secret-value-that-must-not-log" not in serialized
    assert "do-not-log" not in serialized
