from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "private_verify_ibkr.py"
SPEC = importlib.util.spec_from_file_location("private_verify_ibkr", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def verified_response(**updates):
    payload = {
        "status": "verified_private_readonly",
        "provider": "ibkr_readonly",
        "connection_id": "connection-sensitive",
        "sync_result": {
            "account_id": "DU-SENSITIVE",
            "snapshot_id": "snapshot-sensitive",
            "quality_report_id": "quality-sensitive",
            "quality_score": 1.0,
            "catalog_entry_id": "catalog-sensitive",
            "positions_synced": 2,
            "balances_synced": 1,
            "orders_seen": 0,
            "ledger_sync": {"entries_created": 2},
            "reconciliation": {"run_id": "reconcile-sensitive", "status": "ok", "breaks_count": 0},
        },
        "proof_checks": {
            "gateway_session_proof_recorded": True,
            "read_only_boundary_proof_recorded": True,
            "snapshot_recorded": True,
            "quality_report_passed": True,
            "catalog_lineage_recorded": True,
            "ledger_sync_recorded": True,
            "reconciliation_passed": True,
            "orders_endpoint_not_used": True,
        },
        "read_endpoints": [
            "/portfolio/accounts",
            "/portfolio/{accountId}/positions/{pageId}",
            "/portfolio/{accountId}/ledger",
        ],
        "forbidden": ["order_endpoint", "order_placement", "withdrawal", "production_trading"],
        "audit_packet_artifact_id": "audit-sensitive",
        "execution_available": False,
        "production_capability": False,
    }
    payload.update(updates)
    return module.Response(200, payload)


def test_target_allows_loopback_http_or_https_only():
    assert module.validate_target("http://127.0.0.1:8000") == []
    assert module.validate_target("https://private.example") == []
    assert module.validate_target("http://private.example")
    assert module.validate_target("https://user:pass@private.example")
    assert module.validate_target("https://private.example?token=x")


def test_proof_requires_regular_supported_bounded_file(tmp_path):
    proof = tmp_path / "proof.png"
    proof.write_bytes(b"x" * 64)
    assert len(module.proof_fingerprint(proof)) == 64
    invalid = tmp_path / "proof.txt"
    invalid.write_bytes(b"x" * 64)
    with pytest.raises(module.VerificationError):
        module.proof_fingerprint(invalid)
    link = tmp_path / "link.png"
    link.symlink_to(proof)
    with pytest.raises(module.VerificationError):
        module.proof_fingerprint(link)


def test_verified_packet_requires_full_real_readonly_evidence_chain():
    evidence = module.sanitize_verified_packet(
        verified_response(),
        user_id="real-user-sub",
        proof_hashes={"gateway_session": "a" * 64, "read_only_boundary": "b" * 64},
    )
    assert evidence["status"] == "passed"
    assert evidence["real_ibkr_gateway_calls_performed"] is True
    assert evidence["orders_seen"] == 0
    assert evidence["reconciliation_status"] == "ok"


def test_raw_account_and_resource_ids_are_replaced_by_fingerprints():
    evidence = module.sanitize_verified_packet(
        verified_response(),
        user_id="real-user-sub",
        proof_hashes={"gateway_session": "a" * 64, "read_only_boundary": "b" * 64},
    )
    serialized = json.dumps(evidence)
    for secret_value in ("DU-SENSITIVE", "connection-sensitive", "snapshot-sensitive", "reconcile-sensitive", "audit-sensitive", "real-user-sub"):
        assert secret_value not in serialized
    assert evidence["contains_account_id"] is False
    assert evidence["contains_session_token"] is False


def test_missing_reconciliation_or_order_boundary_fails_closed():
    response = verified_response()
    response.payload["sync_result"]["reconciliation"]["status"] = "needs_review"
    response.payload["sync_result"]["orders_seen"] = 1
    evidence = module.sanitize_verified_packet(response, user_id="user", proof_hashes={})
    assert evidence["status"] == "failed"
    failed = {item["key"] for item in evidence["checks"] if item["status"] == "failed"}
    assert {"ledger_reconciliation_passed", "orders_endpoint_not_used"}.issubset(failed)


def test_unverified_provider_response_cannot_be_promoted():
    evidence = module.sanitize_verified_packet(
        module.Response(422, {"status": "verification_blocked", "provider": "ibkr_readonly"}),
        user_id="user",
        proof_hashes={},
    )
    assert evidence["status"] == "failed"
    assert evidence["real_ibkr_gateway_calls_performed"] is False


def test_saved_evidence_is_private(tmp_path):
    path = module.save_evidence(tmp_path / "evidence", {"status": "passed", "contains_credentials": False})
    assert path.stat().st_mode & 0o077 == 0
    assert path.parent.stat().st_mode & 0o077 == 0
