"""MCP read-only server (Phase 29): tools cannot bypass the control system.

The server may only observe. These tests pin that guarantee three ways:
tool names free of execution vocabulary, module source free of execution
service imports, and functional results carrying the review-only markers.
"""

import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.mcp_readonly import server as mcp_server


@pytest.fixture()
def sqlite_sessions(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(mcp_server, "_session_factory", factory)
    yield factory
    Base.metadata.drop_all(engine)


def registered_tool_names() -> list[str]:
    return [tool.name for tool in mcp_server.mcp._tool_manager.list_tools()]


def test_tool_names_contain_no_execution_vocabulary() -> None:
    names = registered_tool_names()
    assert len(names) >= 8
    for name in names:
        tokens = set(name.lower().split("_"))
        forbidden = tokens & set(mcp_server.FORBIDDEN_TOOL_NAME_TERMS)
        assert not forbidden, f"tool {name!r} contains forbidden term(s) {forbidden}"


def test_server_module_imports_no_execution_services() -> None:
    source = inspect.getsource(mcp_server)
    for forbidden_module in [
        "live_execution",
        "paper_execution",
        "controlled_auto",
        "services.approvals",
        "services.orders",
        "order_intents",
    ]:
        assert forbidden_module not in source, f"server source references {forbidden_module}"
    # The only expected write anywhere below the tools is the thesis-delta audit record.
    for forbidden_call in [".create_run(", ".start_run(", ".promote_entry(", ".replay_entry_snapshot("]:
        assert forbidden_call not in source


def test_tools_return_review_only_markers_on_empty_db(sqlite_sessions) -> None:
    # FastMCP wraps functions; call the underlying implementations directly.
    fn = mcp_server.mcp._tool_manager._tools["list_theses"].fn
    result = fn()
    assert result["execution_available"] is False
    assert result["review_only"] is True
    assert result["count"] == 0

    pipeline = mcp_server.mcp._tool_manager._tools["plan_pipeline_status"].fn()
    assert pipeline["execution_available"] is False
    assert pipeline["count"] == 0

    backtests = mcp_server.mcp._tool_manager._tools["list_backtest_results"].fn()
    assert backtests["execution_available"] is False
    assert backtests["count"] == 0

    risk = mcp_server.mcp._tool_manager._tools["portfolio_risk_latest"].fn()
    assert risk["execution_available"] is False
    assert risk["status"] == "not_run"


def test_every_tool_description_is_present() -> None:
    for tool in mcp_server.mcp._tool_manager.list_tools():
        assert tool.description and len(tool.description) > 20, f"tool {tool.name} lacks a real description"
