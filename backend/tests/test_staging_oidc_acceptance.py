from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "staging_oidc_isolation_acceptance.py"
SPEC = spec_from_file_location("staging_oidc_acceptance", SCRIPT)
assert SPEC and SPEC.loader
acceptance = module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class FakeApiClient:
    def __init__(self):
        self.logins = 0
        self.revoked = False

    def request(self, method, path, *, bearer=None, payload=None, headers=None):
        Response = acceptance.Response
        if path == "/production/auth/login":
            self.logins += 1
            identity = "a" if self.logins == 1 else "b"
            return Response(200, {
                "session_token": f"session-{identity}",
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat(),
                "user": {"user_id": f"oidc-subject-{identity}", "role": "viewer"},
            })
        if path == "/beta/whoami" and bearer is None:
            return Response(401, {})
        if path == "/beta/whoami" and bearer == "session-a":
            return Response(401 if self.revoked else 200, {} if self.revoked else {"user_id": "oidc-subject-a", "role": "viewer"})
        if path == "/beta/whoami" and bearer == "session-b":
            return Response(200, {"user_id": "oidc-subject-b", "role": "viewer"})
        if path == "/accounts" and method == "POST":
            return Response(201, {"id": "account-a" if bearer == "session-a" else "account-b"})
        if path == "/accounts" and method == "GET":
            return Response(200, [{"id": "account-a" if bearer == "session-a" else "account-b"}])
        if path == "/daily-use/exports" and method == "POST" and payload.get("user_id") == "oidc-subject-a" and bearer == "session-b":
            return Response(403, {})
        if path == "/daily-use/exports" and method == "POST":
            return Response(201, {"id": "export-a"})
        if path == "/daily-use/exports/export-a":
            return Response(404, {})
        if path.startswith("/daily-use/exports?user_id="):
            return Response(403, {})
        if path == "/beta/users":
            return Response(403, {})
        if path == "/production/auth/logout":
            self.revoked = True
            return Response(200, {"status": "revoked"})
        raise AssertionError(f"unexpected request: {method} {path}")


def test_real_target_validation_requires_remote_https_and_explicit_production_override() -> None:
    assert acceptance.validate_target("https://staging.example/api", "staging", False) == []
    assert acceptance.validate_target("http://localhost:8000", "staging", False)
    assert any("allow-production" in item for item in acceptance.validate_target("https://api.example", "production", False))


def test_two_identity_acceptance_matrix_passes_only_when_every_boundary_holds() -> None:
    result = acceptance.run_acceptance(
        FakeApiClient(),
        access_token_a="access-a",
        access_token_b="access-b",
        maximum_session_seconds=3700,
    )
    assert result["passed"] is True
    assert len(result["checks"]) >= 14
    assert all(item["status"] == "passed" for item in result["checks"])
    assert result["contains_tokens"] is False
    serialized = str(result)
    assert "access-a" not in serialized
    assert "session-a" not in serialized
    assert "oidc-subject-a" not in serialized


def test_subject_fingerprint_is_stable_and_non_reversible_in_evidence() -> None:
    fingerprint = acceptance.subject_fingerprint("sensitive-oidc-subject")
    assert fingerprint == acceptance.subject_fingerprint("sensitive-oidc-subject")
    assert len(fingerprint) == 16
    assert "sensitive" not in fingerprint
