from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "secret_manager_lifecycle_acceptance.py"
SPEC = spec_from_file_location("secret_manager_lifecycle_acceptance", SCRIPT)
assert SPEC and SPEC.loader
lifecycle = module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle)


class FakeClient:
    def __init__(self):
        self.version = "version-1"
        self.available = True

    def request(self, method, path, payload=None):
        if path == "/production/secrets/verify":
            if not self.available:
                return lifecycle.Response(422, {"detail": "secret reference verification failed"})
            return lifecycle.Response(200, {
                "reference": payload["reference"],
                "backend": "aws_secrets_manager",
                "version": self.version,
                "resolved": True,
                "contains_secret": False,
            })
        if path == "/beta/secrets/references?limit=100":
            return lifecycle.Response(200, [{"reference_key": "aws-sm://disposable/rotation-test", "status": "invalid"}])
        raise AssertionError(path)


def test_cloud_secret_lifecycle_requires_version_change_invalidation_and_recovery() -> None:
    client = FakeClient()
    reference = "aws-sm://disposable/rotation-test"
    state = lifecycle.execute_phase(client, phase="baseline", reference=reference, state={})
    assert state["baseline_verified"] is True
    client.version = "version-2"
    state = lifecycle.execute_phase(client, phase="rotated", reference=reference, state=state)
    assert state["rotated_verified"] is True
    client.available = False
    state = lifecycle.execute_phase(client, phase="invalidated", reference=reference, state=state)
    assert state["invalidation_verified"] is True
    client.available = True
    client.version = "version-3"
    state = lifecycle.execute_phase(client, phase="recovered", reference=reference, state=state)
    assert state["recovered_verified"] is True
    assert "reference" not in state
    assert state["reference_fingerprint"] == lifecycle.reference_fingerprint(reference)


def test_rotation_does_not_pass_when_provider_version_is_unchanged() -> None:
    client = FakeClient()
    reference = "aws-sm://disposable/rotation-test"
    state = lifecycle.execute_phase(client, phase="baseline", reference=reference, state={})
    state = lifecycle.execute_phase(client, phase="rotated", reference=reference, state=state)
    assert state["rotated_verified"] is False


def test_secret_lifecycle_target_rejects_env_and_insecure_api() -> None:
    assert lifecycle.validate_inputs("https://staging.example", "aws-sm://test") == []
    errors = lifecycle.validate_inputs("http://localhost:8000", "env://TEST")
    assert any("HTTPS" in item for item in errors)
    assert any("localhost" in item for item in errors)
    assert any("AWS/GCP/Vault" in item for item in errors)
