import pytest
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.db.base import Base
from app.models import Account
from app.models import Asset
from app.models import DataSnapshot
from app.models import InvestmentLedgerEntry
from app.models import LocalUserConfig
from app.models import PaperCorporateAction
from app.models import Position
from app.models import Reminder
from app.models import ScheduledJob
from app.services.product_completion import ProductCompletionService
from app.services.complete_product_readiness import CompleteProductReadinessService
from app.services.runtime_scheduler import RuntimeSchedulerService
from datetime import datetime
from datetime import timezone


def owner(user_id: str = "owner-user") -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, role="owner", permissions=ROLE_PERMISSIONS["owner"], auth_required=True, token_configured=True)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def seed_portfolio(db: Session):
    account = Account(name="Main", account_type="brokerage", broker="simulated", base_currency="USD", mode="read_only", live_trading_enabled=False)
    asset = Asset(symbol="NVDA", name="NVIDIA", asset_type="stock", market="US", venue="NASDAQ", currency="USD")
    db.add_all([account, asset])
    db.flush()
    db.add(Position(account_id=account.id, asset_id=asset.id, quantity=10, average_cost=100, market_price=140, market_value=1400))
    db.commit()
    return account, asset


def test_initialize_builds_all_eight_local_product_slices(db):
    service = ProductCompletionService(db)
    result = service.initialize(actor=owner())
    assert result["status"] == "initialized"
    assert len(result["projects"]) == 8
    assert result["summary"]["initialized_projects"] == 8
    assert result["summary"]["local_implementation_pct"] == 100
    assert result["production_execution_allowed"] is False
    assert db.scalar(select(func.count()).select_from(ScheduledJob).where(ScheduledJob.job_type.like("product_%"))) == 4
    assert db.scalar(select(func.count()).select_from(Reminder).where(Reminder.user_id == "owner-user")) == 1
    readiness = CompleteProductReadinessService(db).summary(user_id="owner-user")
    assert readiness["progress_pct"] >= 50
    assert "daily_workflow_scheduling_missing" not in readiness["blockers"]
    tick = service.scheduler_tick(actor=owner(), action="refresh_reminders")
    assert tick["status"] == "completed"
    assert tick["results"][0]["status"] == "scheduled"


def test_ledger_supports_multi_currency_and_normalized_corporate_actions(db):
    account, asset = seed_portfolio(db)
    service = ProductCompletionService(db)
    cash = service.record_cash_ledger_entry(actor=owner(), payload={"currency": "HKD", "amount": 10000, "account_id": account.id, "fx_rate_to_usd": 0.128})
    assert cash["currency"] == "HKD"
    normalized = service.normalize_corporate_action(actor=owner(), payload={"account_id": account.id, "asset_id": asset.id, "action_type": "dividend", "quantity_before": 10, "quantity_after": 10, "cash_effect": 25, "amount_per_share": 2.5})
    assert normalized["ledger_entry_id"]
    assert db.scalar(select(func.count()).select_from(PaperCorporateAction)) == 1
    assert db.scalar(select(func.count()).select_from(InvestmentLedgerEntry)) == 2


def test_snapshot_version_and_replay_are_hash_based_and_read_only(db):
    snapshot = DataSnapshot(snapshot_type="quotes", data_json={"NVDA": {"price": 140}}, metadata_json={"provider": "simulated"})
    db.add(snapshot)
    db.commit()
    service = ProductCompletionService(db)
    versioned = service.version_snapshot(actor=owner(), snapshot_id=snapshot.id)
    assert versioned["dataset_version"].startswith("sha256:")
    replay = service.replay_snapshot(actor=owner(), snapshot_id=snapshot.id)
    assert replay["replay"] is True
    assert replay["execution_available"] is False


def test_risk_report_includes_factor_correlation_liquidity_and_budget(db):
    seed_portfolio(db)
    report = ProductCompletionService(db).portfolio_risk_report(actor=owner())
    assert report["factor_exposure"]["growth"] == 1
    assert report["concentration_hhi"] == 1
    assert report["liquidity"]["max_days"] == 1
    assert report["correlation_proxy"]["growth"]["growth"] == 1


def test_commercial_ops_and_external_interfaces_remain_test_or_simulation_only(db):
    service = ProductCompletionService(db)
    service.initialize_commercial(actor=owner())
    checkout = service.create_test_checkout(actor=owner(), plan="pro")
    assert checkout["mode"] == "test"
    assert checkout["charged"] is False
    assert "configured_llm" in checkout["entitlements"]
    assert service.record_usage(actor=owner(), metric="eval_run", quantity=2)["charged"] is False
    assert service.create_support_ticket(actor=owner(), payload={"title": "Data freshness issue"})["status"] == "closed"
    service.initialize_operations(actor=owner())
    drill = service.incident_drill(actor=owner(), scenario="market_data_stale")
    assert drill["simulation"] is True
    external = service.initialize_external_proof(actor=owner())
    assert external["production_execution_allowed"] is False
    assert external["manifest"]["binance"]["status"] == "awaiting_credentials"


def test_product_completion_api(client):
    initialized = client.post("/production/product-completion/initialize")
    assert initialized.status_code == 200
    assert initialized.json()["summary"]["initialized_projects"] == 8
    status = client.get("/production/product-completion/status")
    assert status.status_code == 200
    assert status.json()["local_implementation_pct"] == 100
    checkout = client.post("/production/product-completion/checkout/test", json={"plan": "private_beta"})
    assert checkout.status_code == 200
    assert checkout.json()["charged"] is False
    incident = client.post("/production/product-completion/incident-drills/database_unavailable")
    assert incident.status_code == 200
    assert incident.json()["degraded_to"] == "read_only"


def test_runtime_scheduler_executes_due_jobs_once_per_window(db):
    ProductCompletionService(db).initialize_daily_loop(actor=owner())
    scheduler = RuntimeSchedulerService(db)
    monday_open = datetime(2026, 6, 22, 0, 0, tzinfo=timezone.utc)  # 08:00 Asia/Shanghai

    first = scheduler.run_due_jobs_once(current_time=monday_open)
    assert first["jobs_run"] == 3
    assert {item["job_type"] for item in first["results"]} == {
        "product_daily_open",
        "product_continuous_reminders",
        "observability_slo_check",
    }

    duplicate = scheduler.run_due_jobs_once(current_time=monday_open)
    assert duplicate["jobs_run"] == 0

    next_interval = scheduler.run_due_jobs_once(current_time=datetime(2026, 6, 22, 0, 15, tzinfo=timezone.utc))
    assert next_interval["jobs_run"] == 2
    assert {item["job_type"] for item in next_interval["results"]} == {
        "product_continuous_reminders",
        "observability_slo_check",
    }


def test_risk_report_labels_proxy_when_no_time_series_exists(db):
    seed_portfolio(db)
    report = ProductCompletionService(db).portfolio_risk_report(actor=owner())
    assert report["methodology"] == "deterministic_proxy_until_time_series_run"
    assert report["time_series"] is None


def test_risk_report_upgrades_to_real_time_series_when_available(db, monkeypatch):
    from app.services import portfolio_time_series_risk as ts_module

    seed_portfolio(db)

    fake_packet = {
        "correlation_matrix": {"NVDA": {"NVDA": 1.0, "SPY": 0.82}, "SPY": {"NVDA": 0.82, "SPY": 1.0}},
        "as_of": "2026-07-07T00:00:00+00:00",
        "observations": 120,
        "annualized_volatility_pct": 24.5,
        "coverage_pct": 100.0,
        "artifact_id": "ts-artifact-1",
    }
    monkeypatch.setattr(ts_module.PortfolioTimeSeriesRiskService, "latest", lambda self, *, user_id: fake_packet)

    report = ProductCompletionService(db).portfolio_risk_report(actor=owner())
    assert report["methodology"] == "time_series_realized_from_stored_candles"
    assert report["correlation_proxy"]["NVDA"]["SPY"] == 0.82
    assert report["time_series"]["observations"] == 120
    assert report["time_series"]["annualized_volatility_pct"] == 24.5
