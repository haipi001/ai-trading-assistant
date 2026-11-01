"""Snapshot diff / regression comparison for data catalog entries.

Comparing two versioned snapshots answers "did this dataset change?" — the
core drift/tamper check when re-importing a source or validating a replay
copy against its origin. Comparison is review-only: it writes only an audit
record and never enables execution.
"""

from datetime import datetime
from datetime import timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.services.data_catalog import DataCatalogNotFoundError
from app.services.data_catalog import DataCatalogService


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


FIXED_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_entry(db: Session, *, data_json: dict, dataset_type: str = "candles", source: str = "test_source"):
    # Pin as_of so two snapshots with identical payloads hash identically;
    # as_of is intentionally part of the content hash (a different as-of time
    # is a genuinely different dataset version).
    snapshot = DataSnapshot(snapshot_type=dataset_type, as_of=FIXED_AS_OF, data_json=data_json, metadata_json={})
    db.add(snapshot)
    db.flush()
    report = DataQualityReport(
        data_snapshot_id=snapshot.id, source="test", metric_type="completeness", score=1.0
    )
    db.add(report)
    db.flush()
    service = DataCatalogService(db)
    entry = service.create_entry(
        dataset_type=dataset_type,
        source=source,
        row_count=len(data_json.get("rows", [])),
        snapshot=snapshot,
        quality_report=report,
    )
    db.commit()
    return service, entry


def test_identical_snapshots_report_identical(db: Session) -> None:
    rows = {"rows": [{"t": 1, "close": 10}, {"t": 2, "close": 11}]}
    service, entry_a = make_entry(db, data_json=rows)
    _, entry_b = make_entry(db, data_json={"rows": list(rows["rows"])})

    result = service.compare_entry_snapshots(entry_a.id, entry_b.id)

    assert result["verdict"] == "identical"
    assert result["content_identical"] is True
    assert result["review_only"] is True
    assert result["execution_available"] is False
    assert result["row_diff"]["added_row_count"] == 0
    assert result["row_diff"]["removed_row_count"] == 0
    assert result["row_diff"]["unchanged_row_count"] == 2


def test_changed_rows_are_detected(db: Session) -> None:
    service, entry_a = make_entry(db, data_json={"rows": [{"t": 1, "close": 10}, {"t": 2, "close": 11}]})
    # One row removed (t=2 close 11), two rows added (t=2 close 12, t=3 close 13).
    _, entry_b = make_entry(
        db, data_json={"rows": [{"t": 1, "close": 10}, {"t": 2, "close": 12}, {"t": 3, "close": 13}]}
    )

    result = service.compare_entry_snapshots(entry_a.id, entry_b.id)

    assert result["verdict"] == "content_changed"
    assert result["content_identical"] is False
    diff = result["row_diff"]
    assert diff["shape"] == "rows"
    assert diff["row_count_base"] == 2
    assert diff["row_count_compared"] == 3
    assert diff["row_count_delta"] == 1
    assert diff["added_row_count"] == 2
    assert diff["removed_row_count"] == 1
    assert diff["unchanged_row_count"] == 1
    assert {"t": 3, "close": 13} in diff["added_sample"]
    assert {"t": 2, "close": 11} in diff["removed_sample"]


def test_field_shaped_payloads_diff_by_key(db: Session) -> None:
    service, entry_a = make_entry(db, data_json={"AAPL": {"price": 200}, "MSFT": {"price": 400}})
    _, entry_b = make_entry(db, data_json={"AAPL": {"price": 210}, "GOOG": {"price": 150}})

    result = service.compare_entry_snapshots(entry_a.id, entry_b.id)

    assert result["verdict"] == "content_changed"
    assert result["row_diff"] is None
    field = result["field_diff"]
    assert field["shape"] == "fields"
    assert field["added_keys"] == ["GOOG"]
    assert field["removed_keys"] == ["MSFT"]
    assert field["changed_keys"] == ["AAPL"]
    changed = {item["key"]: item for item in field["changed"]}
    assert changed["AAPL"]["base"] == {"price": 200}
    assert changed["AAPL"]["compared"] == {"price": 210}


def test_dataset_type_mismatch_is_warned(db: Session) -> None:
    service, entry_a = make_entry(db, data_json={"rows": [{"t": 1}]}, dataset_type="candles")
    _, entry_b = make_entry(db, data_json={"rows": [{"t": 1}]}, dataset_type="quotes")

    result = service.compare_entry_snapshots(entry_a.id, entry_b.id)

    assert "dataset_type_mismatch" in result["warnings"]


def test_missing_entry_raises_not_found(db: Session) -> None:
    service, entry_a = make_entry(db, data_json={"rows": [{"t": 1}]})
    with pytest.raises(DataCatalogNotFoundError):
        service.compare_entry_snapshots(entry_a.id, "does-not-exist")
