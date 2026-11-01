"""Evidence-driven data catalog promotion: raw → reviewed → trusted.

Promotion is gated by real quality and reconciliation evidence, advances at
most one stage per call, is idempotent and fail-closed, and binds
usable_for_trading to the 'trusted' stage only.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import ReconciliationBreak
from app.models import ReconciliationRun
from app.services.data_catalog import DataCatalogService
from app.services.data_catalog import DataTrustGateError


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def make_entry(db: Session, *, score: float):
    snapshot = DataSnapshot(snapshot_type="quotes", data_json={"AAPL": {"price": 200}}, metadata_json={})
    db.add(snapshot)
    db.flush()
    report = DataQualityReport(data_snapshot_id=snapshot.id, source="test", metric_type="completeness", score=score)
    db.add(report)
    db.flush()
    service = DataCatalogService(db)
    entry = service.create_entry(
        dataset_type="quotes",
        source="test_source",
        row_count=1,
        snapshot=snapshot,
        quality_report=report,
    )
    db.commit()
    return service, entry


def add_critical_break(db: Session) -> None:
    run = ReconciliationRun(user_id="default-user", status="break")
    db.add(run)
    db.flush()
    db.add(
        ReconciliationBreak(
            reconciliation_run_id=run.id,
            break_type="quantity_mismatch",
            severity="critical",
            detail="Position quantity does not match statement.",
        )
    )
    db.commit()


def test_low_quality_entry_stays_raw(db: Session) -> None:
    service, entry = make_entry(db, score=0.5)  # INCOMPLETE
    result = service.promote_entry(entry.id)
    assert result["current_stage"] == "raw"
    assert result["usable_for_trading"] is False
    assert "quality_not_valid" in result["trusted_blockers"]


def test_valid_quality_promotes_one_stage_at_a_time_to_trusted(db: Session) -> None:
    service, entry = make_entry(db, score=1.0)  # VALID, no breaks → eligible trusted

    first = service.promote_entry(entry.id)
    assert first["current_stage"] == "reviewed"  # never jumps raw→trusted in one call
    assert first["usable_for_trading"] is False

    second = service.promote_entry(entry.id)
    assert second["current_stage"] == "trusted"
    assert second["usable_for_trading"] is True
    assert second["trusted_blockers"] == []

    # Idempotent: promoting again holds at trusted.
    third = service.promote_entry(entry.id)
    assert third["current_stage"] == "trusted"
    assert third["usable_for_trading"] is True

    history_stages = [(h["from"], h["to"]) for h in third["promotion_history"]]
    assert history_stages == [("raw", "reviewed"), ("reviewed", "trusted")]


def test_exact_snapshot_downstream_gate_requires_explicit_trusted_stage(db: Session) -> None:
    service, entry = make_entry(db, score=1.0)

    blocked = service.snapshot_decision_gate(entry.data_snapshot_id, decision_scope="research_report")
    assert blocked["status"] == "blocked"
    assert "promotion_stage_not_trusted" in blocked["blockers"]

    service.promote_entry(entry.id)
    service.promote_entry(entry.id)
    trusted = service.require_trusted_snapshot(entry.data_snapshot_id, decision_scope="research_report")
    assert trusted["status"] == "trusted"
    assert trusted["entry_id"] == entry.id


def test_exact_snapshot_downstream_gate_fails_closed_for_unknown_snapshot(db: Session) -> None:
    service = DataCatalogService(db)

    with pytest.raises(DataTrustGateError) as exc_info:
        service.require_trusted_snapshot("missing-snapshot", decision_scope="research_committee")

    assert exc_info.value.gate["status"] == "blocked"
    assert exc_info.value.gate["blockers"] == ["snapshot_not_found", "snapshot_not_catalogued"]


def test_open_critical_break_caps_promotion_at_reviewed(db: Session) -> None:
    service, entry = make_entry(db, score=1.0)
    add_critical_break(db)

    first = service.promote_entry(entry.id)
    assert first["current_stage"] == "reviewed"
    second = service.promote_entry(entry.id)
    # Cannot reach trusted while a critical reconciliation break is open.
    assert second["current_stage"] == "reviewed"
    assert second["usable_for_trading"] is False
    assert "open_critical_reconciliation_breaks" in second["trusted_blockers"]


def test_promotion_status_is_read_only_and_reports_eligibility(db: Session) -> None:
    service, entry = make_entry(db, score=1.0)
    status = service.promotion_status(entry.id)
    assert status["current_stage"] == "raw"
    assert status["eligible_stage"] == "trusted"
    assert status["can_advance"] is True
    assert status["execution_available"] is False
    # Reading status must not mutate the entry.
    assert service.promotion_status(entry.id)["current_stage"] == "raw"
