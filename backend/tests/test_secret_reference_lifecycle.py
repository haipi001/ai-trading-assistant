def test_secret_reference_verification_failure_invalidates_and_recovery_reactivates(client, monkeypatch) -> None:
    monkeypatch.setenv("ATOS_ROTATION_TEST_SECRET", "version-one")
    reference = "env://ATOS_ROTATION_TEST_SECRET"
    first = client.post("/production/secrets/verify", json={"reference": reference, "purpose": "rotation_acceptance"})
    assert first.status_code == 200
    assert first.json()["resolved"] is True
    assert first.json()["contains_secret"] is False

    monkeypatch.delenv("ATOS_ROTATION_TEST_SECRET")
    invalidated = client.post("/production/secrets/verify", json={"reference": reference, "purpose": "rotation_acceptance"})
    assert invalidated.status_code == 422
    assert invalidated.json()["detail"] == "secret reference verification failed"

    references = client.get("/beta/secrets/references").json()
    stored = next(item for item in references if item["reference_key"] == reference)
    assert stored["status"] == "invalid"
    assert stored["metadata_json"]["last_verification_error_class"] == "SecretResolutionError"
    assert "version-one" not in str(stored)

    monkeypatch.setenv("ATOS_ROTATION_TEST_SECRET", "version-two")
    recovered = client.post("/production/secrets/verify", json={"reference": reference, "purpose": "rotation_acceptance"})
    assert recovered.status_code == 200
    references = client.get("/beta/secrets/references").json()
    stored = next(item for item in references if item["reference_key"] == reference)
    assert stored["status"] == "active"
    assert "version-two" not in str(stored)
