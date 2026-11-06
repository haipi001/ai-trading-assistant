from functools import lru_cache
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import with_loader_criteria

from app.core.config import get_settings
from app.core.tenant_context import TenantIsolationError
from app.core.tenant_context import current_tenant_id
from app.db.base import Base


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_read_scope(orm_execute_state) -> None:
    tenant_id = current_tenant_id()
    if not tenant_id or not orm_execute_state.is_select or orm_execute_state.execution_options.get("tenant_scope_bypass"):
        return
    statement = orm_execute_state.statement
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if not hasattr(model, "user_id"):
            continue
        statement = statement.options(
            with_loader_criteria(
                model,
                model.user_id == tenant_id,
                include_aliases=True,
            )
        )
    orm_execute_state.statement = statement


@event.listens_for(Session, "before_flush")
def _enforce_tenant_writes(session: Session, _flush_context, _instances) -> None:
    tenant_id = current_tenant_id()
    if not tenant_id or session.info.get("tenant_scope_bypass"):
        return
    for item in session.new.union(session.dirty).union(session.deleted):
        if not hasattr(type(item), "user_id"):
            continue
        item_user_id = str(getattr(item, "user_id", "") or "").strip()
        if item in session.new and item_user_id in {"", "default-user"}:
            setattr(item, "user_id", tenant_id)
            item_user_id = tenant_id
        if item_user_id != tenant_id:
            raise TenantIsolationError("cross-user database write denied")


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = settings.dependency_check_timeout_seconds
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db() -> Generator[Session]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
