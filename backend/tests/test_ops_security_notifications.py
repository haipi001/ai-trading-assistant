from app.core.observability import RedisRequestMetrics


def test_notification_channels_default_to_local_only_and_block_external(client) -> None:
    status = client.get("/ops/notification-channels")
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "local_ready"
    assert payload["external_delivery_status"] == "not_configured"
    assert payload["external_message_sent"] is False
    in_app = next(item for item in payload["channels"] if item["channel"] == "in_app")
    email = next(item for item in payload["channels"] if item["channel"] == "email")
    assert in_app["status"] == "ready"
    assert email["status"] == "not_configured"
    assert email["can_send_external"] is False

    dry_run = client.post("/ops/notification-channels/dry-run", json={"channel": "email", "subject": "Do not send"})
    assert dry_run.status_code == 201
    dry_payload = dry_run.json()
    assert dry_payload["blocked"] is True
    assert dry_payload["external_message_sent"] is False
    assert dry_payload["execution_available"] is False


def test_notification_dry_run_uses_secret_reference_without_sending(client) -> None:
    config = client.put(
        "/daily-use/local-config/notification_preferences",
        json={
            "user_id": "default-user",
            "value_json": {"external_channels": {"email": "env:EMAIL_PROVIDER_TOKEN"}},
            "description": "test notification prefs",
        },
    )
    assert config.status_code == 200
    secret = client.post(
        "/beta/secrets/references",
        json={
            "user_id": "default-user",
            "reference_key": "env:EMAIL_PROVIDER_TOKEN",
            "provider": "resend",
            "scope": "notification_send",
            "status": "active",
            "metadata_json": {"purpose": "dry_run_only"},
        },
    )
    assert secret.status_code == 201

    status = client.get("/ops/notification-channels").json()
    email = next(item for item in status["channels"] if item["channel"] == "email")
    assert email["status"] == "preflight_ready"
    assert email["secret_reference"] == "env:EMAIL_PROVIDER_TOKEN"
    assert email["can_send_external"] is False

    dry_run = client.post("/ops/notification-channels/dry-run", json={"channel": "email", "subject": "Safe test"})
    assert dry_run.status_code == 201
    payload = dry_run.json()
    assert payload["status"] == "dry_run_recorded"
    assert payload["external_message_sent"] is False
    assert payload["outbox"]["secret_reference"] == "env:EMAIL_PROVIDER_TOKEN"
    assert payload["outbox"]["external_message_sent"] is False


def test_security_control_plane_creates_threat_model_and_rate_limits(client) -> None:
    response = client.get("/ops/security-control-plane")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["execution_available"] is False
    assert payload["threat_model"]["version"] == "local-safe-v1"
    assert any(item["key"] == "approval_bypass" for item in payload["threat_model"]["top_threats"])
    assert payload["rate_limit_policy"]["default_action"] == "fail_closed_for_execution_paths"
    notification_rule = next(item for item in payload["rate_limit_policy"]["rules"] if item["scope"] == "notification_dry_run")
    assert notification_rule["mode"] == "fail_closed_local"
    assert any(item["scope"] == "llm_calls" for item in payload["rate_limit_policy"]["rules"])
    notification_status = next(item for item in payload["rate_limit_statuses"] if item["scope"] == "notification_dry_run")
    assert notification_status["remaining"] == 10
    assert notification_status["allowed"] is True


def test_notification_dry_run_is_rate_limited_locally(client) -> None:
    for _ in range(10):
        response = client.post("/ops/notification-channels/dry-run", json={"channel": "in_app", "subject": "Local quota"})
        assert response.status_code == 201
        assert response.json()["blocked"] is False

    limited = client.post("/ops/notification-channels/dry-run", json={"channel": "in_app", "subject": "Local quota"})
    assert limited.status_code == 201
    payload = limited.json()
    assert payload["blocked"] is True
    assert payload["status"] == "blocked"
    assert payload["outbox"]["reason"] == "rate_limited"
    assert payload["rate_limit"]["allowed"] is False
    assert payload["external_message_sent"] is False
    assert payload["execution_available"] is False


def test_slo_breach_alert_is_deduplicated_and_resolves_on_recovery(client, monkeypatch) -> None:
    breached = {
        "status": "breached",
        "window_hours": 24,
        "requests": 100,
        "errors": 5,
        "availability": 0.95,
        "error_rate": 0.05,
        "average_latency_ms": 1200,
        "targets": {"availability": 0.995, "error_rate": 0.01, "average_latency_ms": 1000},
        "sample_sufficient": True,
        "real_request_metrics": True,
    }
    monkeypatch.setattr(RedisRequestMetrics, "snapshot", lambda self, window_hours=24: breached)

    first = client.post("/ops/observability/evaluate")
    second = client.post("/ops/observability/evaluate")

    assert first.status_code == 201
    assert first.json()["alert_created"] is True
    assert first.json()["notification"]["in_app_event_recorded"] is True
    assert first.json()["notification"]["external_notification_delivered"] is False
    assert second.status_code == 201
    assert second.json()["alert_created"] is False
    assert second.json()["open_alerts"] == 1

    recovered = {
        **breached,
        "status": "ok",
        "errors": 0,
        "availability": 1.0,
        "error_rate": 0.0,
        "average_latency_ms": 100,
    }
    monkeypatch.setattr(RedisRequestMetrics, "snapshot", lambda self, window_hours=24: recovered)
    resolved = client.post("/ops/observability/evaluate")

    assert resolved.status_code == 201
    assert resolved.json()["alerts_resolved"] == 1
    assert resolved.json()["open_alerts"] == 0
