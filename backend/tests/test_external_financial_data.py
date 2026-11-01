import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.models import DataCatalogEntry
from app.models import DataSnapshot
from app.models import ExportArtifact
from app.models import InvestmentLedgerEntry
from app.services.external_financial_data import ExternalFinancialDataError
from app.services.external_financial_data import ExternalFinancialDataService


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_ecb_fx_sync_normalizes_rates_and_persists_evidence(db):
    csv_body = "CURRENCY,TIME_PERIOD,OBS_VALUE,OBS_STATUS\nUSD,2026-06-19,1.1500,A\nCNY,2026-06-19,8.0000,A\nHKD,2026-06-19,9.0000,A\n"
    service = ExternalFinancialDataService(db, fetch_text=lambda url, headers, timeout: csv_body)

    result = service.sync_ecb_fx(currencies=["USD", "CNY", "HKD"])

    assert result["provider"] == "European Central Bank"
    assert result["rates"]["USD"]["to_usd"] == 1
    assert result["rates"]["CNY"]["to_usd"] == pytest.approx(1.15 / 8)
    assert result["execution_available"] is False
    assert db.scalar(select(func.count()).select_from(DataSnapshot).where(DataSnapshot.snapshot_type == "fx_rates")) == 1
    assert db.scalar(select(func.count()).select_from(DataCatalogEntry).where(DataCatalogEntry.dataset_type == "fx_rates")) == 1


def test_nasdaq_dividend_sync_persists_review_only_events(db):
    payload = {"data": {"dividends": {"rows": [{"exOrEffDate": "05/11/2026", "type": "Cash", "amount": "$0.27", "declarationDate": "04/30/2026", "recordDate": "05/11/2026", "paymentDate": "05/14/2026", "currency": "USD"}]}}}
    service = ExternalFinancialDataService(db, fetch_text=lambda url, headers, timeout: json.dumps(payload))

    result = service.sync_nasdaq_dividends(symbols=["AAPL"])

    assert result["events"][0]["symbol"] == "AAPL"
    assert result["events"][0]["amount_per_share"] == 0.27
    catalog = db.scalar(select(DataCatalogEntry).where(DataCatalogEntry.dataset_type == "corporate_actions"))
    assert catalog is not None
    assert catalog.usable_for_trading is False


def test_statement_download_requires_allowlist_and_uses_secret_reference(db, monkeypatch):
    captured = {}

    def fake_fetch(url, headers, timeout):
        captured.update(headers)
        return "date,type,symbol,quantity,price,currency,account\n2026-06-01,BUY,AAPL,1,190,USD,Main\n"

    monkeypatch.setenv("STATEMENT_AUTH", json.dumps({"headers": {"Authorization": "Bearer test-token"}}))
    settings = Settings(statement_download_allowed_hosts_raw="statements.example.com")
    service = ExternalFinancialDataService(db, settings=settings, fetch_text=fake_fetch)
    result = service.download_statement(
        user_id="user-1",
        url="https://statements.example.com/export.csv?period=latest",
        provider="example_broker",
        account_label="Main",
        statement_type="broker_statement",
        default_currency="USD",
        credentials_ref="env://STATEMENT_AUTH",
    )

    assert captured["Authorization"] == "Bearer test-token"
    assert result["batch"].imported_count == 1
    assert result["download"]["credentials_ref"] == "redacted"
    assert result["download"]["path"] == "/export.csv"
    assert db.scalar(select(func.count()).select_from(InvestmentLedgerEntry)) == 1


def test_statement_download_blocks_unlisted_or_non_https_hosts(db):
    settings = Settings(statement_download_allowed_hosts_raw="statements.example.com")
    service = ExternalFinancialDataService(db, settings=settings, fetch_text=lambda *_: "")
    with pytest.raises(ExternalFinancialDataError, match="HTTPS"):
        service.download_statement(user_id="u", url="http://statements.example.com/file.csv", provider="p", account_label=None, statement_type="broker_statement", default_currency="USD")
    with pytest.raises(ExternalFinancialDataError, match="not in"):
        service.download_statement(user_id="u", url="https://localhost/file.csv", provider="p", account_label=None, statement_type="broker_statement", default_currency="USD")


def test_statement_download_preflight_explains_allowlist_and_secret_reference(db):
    settings = Settings(statement_download_allowed_hosts_raw="statements.example.com")
    service = ExternalFinancialDataService(db, settings=settings, fetch_text=lambda *_: "")

    ready = service.statement_download_preflight(
        url="https://statements.example.com/export.csv?token=redacted",
        credentials_ref="env://STATEMENT_AUTH",
    )
    assert ready["status"] == "ready"
    assert ready["host"] == "statements.example.com"
    assert ready["path"] == "/export.csv"
    assert ready["allowlisted"] is True
    assert ready["credentials_ref"] == "redacted"
    assert ready["execution_available"] is False
    assert ready["download_will_not_execute"] is True

    blocked = service.statement_download_preflight(
        url="http://evil.example.com/export.csv",
        credentials_ref="Bearer pasted-token",
    )
    assert blocked["status"] == "blocked"
    assert "statement_url_must_use_https" in blocked["blockers"]
    assert "statement_host_not_allowlisted" in blocked["blockers"]
    assert "credentials_ref_looks_like_inline_secret" in blocked["blockers"]


def test_auxiliary_data_status_explains_missing_readonly_evidence(db):
    service = ExternalFinancialDataService(db, settings=Settings(statement_download_allowed_hosts_raw=""))

    status = service.auxiliary_data_status(user_id="user-1")

    assert status["status"] == "action_required"
    assert status["ready_count"] == 0
    assert status["execution_available"] is False
    assert status["production_capability"] is False
    assert "fx_rates" in status["missing"]
    assert "corporate_actions" in status["missing"]
    assert "statement_download_policy" in status["missing"]
    assert "statement_import_evidence" in status["missing"]
    assert status["statement_download_policy"]["inline_credentials_allowed"] is False
    assert [step["key"] for step in status["local_next_steps"]] == ["fx_rates", "corporate_actions", "statement_import_evidence", "evidence_packet"]
    assert status["promotion_gate"]["status"] == "blocked"
    assert status["promotion_gate"]["can_unlock_order_approval"] is False
    assert status["promotion_gate"]["can_review_ledger"] is False


def test_auxiliary_data_evidence_packet_persists_redacted_readonly_status(db, monkeypatch):
    csv_body = "CURRENCY,TIME_PERIOD,OBS_VALUE,OBS_STATUS\nUSD,2026-06-19,1.1500,A\nCNY,2026-06-19,8.0000,A\n"
    dividend_body = json.dumps({"data": {"dividends": {"rows": [{"exOrEffDate": "05/11/2026", "amount": "$0.27", "declarationDate": "04/30/2026", "recordDate": "05/11/2026", "paymentDate": "05/14/2026", "currency": "USD"}]}}})
    statement_body = "date,type,symbol,quantity,price,currency,account\n2026-06-01,BUY,AAPL,1,190,USD,Main\n"

    def fake_fetch(url, headers, timeout):
        if "data-api.ecb.europa.eu" in url:
            return csv_body
        if "api.nasdaq.com" in url:
            return dividend_body
        return statement_body

    monkeypatch.setenv("STATEMENT_AUTH", json.dumps({"headers": {"Authorization": "Bearer test-token"}}))
    settings = Settings(statement_download_allowed_hosts_raw="statements.example.com")
    service = ExternalFinancialDataService(db, settings=settings, fetch_text=fake_fetch)
    service.sync_ecb_fx(currencies=["USD", "CNY"])
    service.sync_nasdaq_dividends(symbols=["AAPL"])
    service.download_statement(
        user_id="user-1",
        url="https://statements.example.com/export.csv",
        provider="example_broker",
        account_label="Main",
        statement_type="broker_statement",
        default_currency="USD",
        credentials_ref="env://STATEMENT_AUTH",
    )

    status = service.auxiliary_data_status(user_id="user-1")
    assert status["status"] == "ready_for_local_review"
    assert status["ready_count"] == status["total_count"]
    assert {item["key"] for item in status["items"]} == {"fx_rates", "corporate_actions", "statement_download_policy", "statement_import_evidence"}
    assert all(item["status"] == "ready" for item in status["items"])
    assert status["promotion_gate"]["status"] == "ready_for_review"
    assert status["promotion_gate"]["can_review_ledger"] is True
    assert status["promotion_gate"]["can_use_for_thesis_context"] is True
    assert status["promotion_gate"]["can_unlock_order_approval"] is False
    assert status["local_next_steps"][-1]["status"] == "ready"

    packet = service.auxiliary_data_evidence_packet(user_id="user-1")
    serialized = json.dumps(packet)
    assert packet["packet_type"] == "market_auxiliary_data_evidence_packet"
    assert packet["contains_secrets"] is False
    assert packet["production_capability"] is False
    assert packet["execution_available"] is False
    assert "test-token" not in serialized
    artifact = db.get(ExportArtifact, packet["artifact_id"])
    assert artifact is not None
    assert artifact.export_type == "market_auxiliary_data_evidence_packet"
