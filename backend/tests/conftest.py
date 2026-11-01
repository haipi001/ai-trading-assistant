from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot


@pytest.fixture()
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def trusted_snapshot_factory(client: TestClient):
    """Create exact trusted snapshot evidence for downstream-gate API tests."""
    sessions: list[Generator[Session]] = []

    def create(snapshot_id: str, *, dataset_type: str = "market_candles") -> str:
        session_gen = app.dependency_overrides[get_db]()
        sessions.append(session_gen)
        db = next(session_gen)
        snapshot = DataSnapshot(
            id=snapshot_id,
            snapshot_type=dataset_type,
            data_json={"test_fixture": True},
            metadata_json={"execution_available": False},
        )
        db.add(snapshot)
        db.flush()
        quality = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source="test_trusted_fixture",
            metric_type="completeness",
            score=1.0,
            details_json={"test_fixture": True},
        )
        db.add(quality)
        db.flush()
        db.add(
            DataCatalogEntry(
                dataset_type=dataset_type,
                source="test_trusted_fixture",
                data_snapshot_id=snapshot.id,
                quality_report_id=quality.id,
                row_count=1,
                quality_status="VALID",
                usable_for_trading=True,
                lineage_json={"promotion_stage": "trusted"},
                contract_json={"execution_available": False},
            )
        )
        db.commit()
        return snapshot.id

    yield create
    for session_gen in sessions:
        session_gen.close()
