import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import TenantIsolationError
from app.core.tenant_context import bind_tenant
from app.core.tenant_context import reset_tenant
from app.db.base import Base
from app.models import Account
from app.models import DataSnapshot
from app.models import LocalUserConfig


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_scope_bypass"] = True
        session.add_all(
            [
                LocalUserConfig(user_id="tenant-a", config_key="theme", value_json={"value": "a"}),
                LocalUserConfig(user_id="tenant-b", config_key="theme", value_json={"value": "b"}),
            ]
        )
        session.commit()
        session.info.pop("tenant_scope_bypass")
        yield session
    Base.metadata.drop_all(engine)


def test_tenant_context_filters_selects_and_session_get(db: Session) -> None:
    tenant_b_id = db.scalar(
        select(LocalUserConfig.id)
        .where(LocalUserConfig.user_id == "tenant-b")
        .execution_options(tenant_scope_bypass=True)
    )
    token = bind_tenant("tenant-a")
    try:
        rows = list(db.scalars(select(LocalUserConfig).order_by(LocalUserConfig.user_id)).all())
        hidden = db.get(LocalUserConfig, tenant_b_id)
    finally:
        reset_tenant(token)

    assert [row.user_id for row in rows] == ["tenant-a"]
    assert hidden is None


def test_tenant_context_denies_cross_user_insert(db: Session) -> None:
    token = bind_tenant("tenant-a")
    try:
        db.add(LocalUserConfig(user_id="tenant-b", config_key="forbidden", value_json={}))
        with pytest.raises(TenantIsolationError, match="cross-user database write denied"):
            db.flush()
        db.rollback()
    finally:
        reset_tenant(token)


def test_tenant_context_denies_cross_user_mutation_of_preloaded_record(db: Session) -> None:
    item = db.scalar(
        select(LocalUserConfig)
        .where(LocalUserConfig.user_id == "tenant-b")
        .execution_options(tenant_scope_bypass=True)
    )
    token = bind_tenant("tenant-a")
    try:
        item.description = "forbidden mutation"
        with pytest.raises(TenantIsolationError, match="cross-user database write denied"):
            db.flush()
        db.rollback()
    finally:
        reset_tenant(token)


def test_only_explicit_global_reference_models_lack_tenant_column() -> None:
    models_without_tenant = {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if not hasattr(mapper.class_, "user_id")
    }

    assert models_without_tenant == {"Asset", "Candle", "Chain", "Quote"}


def test_new_legacy_resource_is_owned_by_current_tenant(db: Session) -> None:
    token = bind_tenant("tenant-a")
    try:
        account = Account(
            name="Tenant A account",
            account_type="brokerage",
            broker="manual",
            base_currency="USD",
        )
        snapshot = DataSnapshot(snapshot_type="tenant-proof", data_json={}, metadata_json={})
        db.add_all([account, snapshot])
        db.flush()
        assert account.user_id == "tenant-a"
        assert snapshot.user_id == "tenant-a"
        db.rollback()
    finally:
        reset_tenant(token)


def test_resource_id_lookup_cannot_cross_tenants(db: Session) -> None:
    db.info["tenant_scope_bypass"] = True
    account_a = Account(
        user_id="tenant-a",
        name="A",
        account_type="brokerage",
        broker="manual",
        base_currency="USD",
    )
    account_b = Account(
        user_id="tenant-b",
        name="B",
        account_type="brokerage",
        broker="manual",
        base_currency="USD",
    )
    db.add_all([account_a, account_b])
    db.commit()
    account_a_id, account_b_id = account_a.id, account_b.id
    db.expunge_all()
    db.info.pop("tenant_scope_bypass")

    token = bind_tenant("tenant-a")
    try:
        assert db.get(Account, account_a_id) is not None
        assert db.get(Account, account_b_id) is None
    finally:
        reset_tenant(token)
