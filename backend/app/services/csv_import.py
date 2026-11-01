from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import Account
from app.models import Asset
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import PortfolioSnapshot
from app.models import Position
from app.schemas.core import SECRET_CONFIG_KEY_FRAGMENTS
from app.services.data_catalog import DataCatalogService


class CsvImportError(ValueError):
    pass


@dataclass(frozen=True)
class CsvImportResult:
    import_type: str
    rows_received: int
    rows_imported: int
    rows_skipped: int
    accounts_created: int
    assets_created: int
    positions_upserted: int
    snapshot: DataSnapshot
    quality_report: DataQualityReport
    catalog_entry: DataCatalogEntry
    skipped: list[dict[str, Any]]


POSITION_IMPORT_TYPES = {"holdings", "crypto_holdings", "wallet_balances"}
TRADE_IMPORT_TYPES = {"trades"}
REQUIRED_COLUMNS = {
    "holdings": {"asset_symbol", "quantity"},
    "crypto_holdings": {"asset_symbol", "quantity"},
    "wallet_balances": {"asset_symbol", "quantity"},
    "trades": {"asset_symbol", "action", "quantity"},
}


class CsvImportService:
    def __init__(self, db: Session):
        self.db = db

    def import_csv(
        self,
        *,
        import_type: str,
        csv_text: str,
        source_name: str = "manual_csv",
        source_ref: str | None = None,
        default_account_name: str = "CSV Import Account",
        default_account_type: str = "manual",
        default_currency: str = "USD",
        persist_positions: bool = True,
        can_be_used_for_trading: bool = False,
    ) -> CsvImportResult:
        if import_type not in POSITION_IMPORT_TYPES | TRADE_IMPORT_TYPES:
            raise CsvImportError(f"unsupported CSV import type: {import_type}")

        rows, columns = self._parse_csv(csv_text)
        self._validate_columns(import_type, columns)
        if len(rows) > 1000:
            raise CsvImportError("CSV import is limited to 1000 rows per request")

        imported_rows: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        accounts_created = 0
        assets_created = 0
        positions_upserted = 0
        imported_account_ids: set[str] = set()

        for index, row in enumerate(rows, start=2):
            try:
                normalized = self._normalize_row(row, default_currency=default_currency)
                account, account_created = self._get_or_create_account(
                    name=normalized.get("account_name") or default_account_name,
                    account_type=normalized.get("account_type") or default_account_type,
                    broker=source_name,
                    base_currency=normalized.get("currency") or default_currency,
                )
                accounts_created += 1 if account_created else 0
                imported_account_ids.add(account.id)
                asset, asset_created = self._get_or_create_asset(normalized, source_name=source_name)
                assets_created += 1 if asset_created else 0

                normalized["account_id"] = account.id
                normalized["asset_id"] = asset.id

                if import_type in POSITION_IMPORT_TYPES and persist_positions:
                    if normalized["asset_type"] != "cash":
                        self._upsert_position(account, asset, normalized)
                        positions_upserted += 1

                imported_rows.append(normalized)
            except Exception as exc:
                skipped.append({"row": index, "error": str(exc), "raw": row})

        if not imported_rows:
            raise CsvImportError(f"no CSV rows imported: {skipped[0]['error'] if skipped else 'empty file'}")

        portfolio_snapshot = None
        if import_type in POSITION_IMPORT_TYPES and persist_positions:
            portfolio_snapshot = self._create_portfolio_snapshot(imported_account_ids, imported_rows, default_currency)

        snapshot = DataSnapshot(
            snapshot_type=f"csv_{import_type}",
            as_of=datetime.now(timezone.utc),
            data_json={
                "import_type": import_type,
                "source": source_name,
                "source_ref": source_ref,
                "rows": imported_rows,
                "skipped": skipped,
            },
            metadata_json={
                "mode": "read_only",
                "source_type": "csv_import",
                "columns": columns,
                "rows_received": len(rows),
                "rows_imported": len(imported_rows),
                "rows_skipped": len(skipped),
                "persist_positions": persist_positions,
                "portfolio_snapshot_id": portfolio_snapshot.id if portfolio_snapshot else None,
                "execution_available": False,
            },
        )
        self.db.add(snapshot)
        self.db.flush()

        score = len(imported_rows) / max(len(rows), 1)
        quality_report = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source=source_name,
            metric_type=f"{import_type}_csv_import_completeness",
            score=score,
            details_json={
                "requested": len(rows),
                "imported": len(imported_rows),
                "skipped": skipped,
                "required_columns": sorted(REQUIRED_COLUMNS[import_type]),
                "read_only": True,
                "can_be_used_for_trading_requested": can_be_used_for_trading,
            },
        )
        self.db.add(quality_report)
        self.db.flush()

        catalog_entry = DataCatalogService(self.db).create_entry(
            dataset_type=f"csv_{import_type}",
            source=source_name,
            source_ref=source_ref,
            row_count=len(imported_rows),
            snapshot=snapshot,
            quality_report=quality_report,
            usable_for_trading=can_be_used_for_trading,
            lineage_json={
                "ingestion": "manual_csv",
                "persisted_positions": import_type in POSITION_IMPORT_TYPES and persist_positions,
                "portfolio_snapshot_id": portfolio_snapshot.id if portfolio_snapshot else None,
            },
            contract_json={
                "required_columns": sorted(REQUIRED_COLUMNS[import_type]),
                "accepted_columns": columns,
                "execution_available": False,
                "default_quality_policy": "fail_closed_if_not_valid_or_not_trading_usable",
            },
        )

        write_audit_log(
            self.db,
            action="csv_import.completed",
            entity_type="DataSnapshot",
            entity_id=snapshot.id,
            payload_json={
                "import_type": import_type,
                "source": source_name,
                "rows_imported": len(imported_rows),
                "rows_skipped": len(skipped),
                "catalog_entry_id": catalog_entry.id,
                "execution_available": False,
            },
            actor_id="v4-csv-import-service",
        )
        self.db.commit()
        for item in (snapshot, quality_report, catalog_entry):
            self.db.refresh(item)

        return CsvImportResult(
            import_type=import_type,
            rows_received=len(rows),
            rows_imported=len(imported_rows),
            rows_skipped=len(skipped),
            accounts_created=accounts_created,
            assets_created=assets_created,
            positions_upserted=positions_upserted,
            snapshot=snapshot,
            quality_report=quality_report,
            catalog_entry=catalog_entry,
            skipped=skipped,
        )

    def _parse_csv(self, csv_text: str) -> tuple[list[dict[str, str]], list[str]]:
        reader = csv.DictReader(StringIO(csv_text.strip()))
        if not reader.fieldnames:
            raise CsvImportError("CSV header row is required")
        columns = [self._normalize_column(column) for column in reader.fieldnames]
        for column in columns:
            if any(fragment in column for fragment in SECRET_CONFIG_KEY_FRAGMENTS):
                raise CsvImportError("CSV columns must not contain secret-like fields")
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            rows.append(
                {
                    self._normalize_column(key): (value or "").strip()
                    for key, value in raw_row.items()
                    if key is not None
                }
            )
        if not rows:
            raise CsvImportError("CSV must include at least one data row")
        return rows, columns

    def _validate_columns(self, import_type: str, columns: list[str]) -> None:
        missing = REQUIRED_COLUMNS[import_type] - set(columns)
        if missing:
            raise CsvImportError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

    def _normalize_row(self, row: dict[str, str], *, default_currency: str) -> dict[str, Any]:
        symbol = (row.get("asset_symbol") or row.get("symbol") or "").upper()
        if not symbol:
            raise CsvImportError("asset_symbol is required")
        quantity = self._number(row.get("quantity"), field="quantity")
        price = self._optional_number(row.get("current_price") or row.get("price"))
        average_cost = self._optional_number(row.get("average_cost"))
        market_value = self._optional_number(row.get("market_value"))
        if price is None and market_value is not None and quantity:
            price = market_value / quantity
        if market_value is None:
            market_value = quantity * (price or 0)
        return {
            "account_name": row.get("account_name") or "",
            "account_type": row.get("account_type") or "",
            "asset_symbol": symbol,
            "asset_name": row.get("asset_name") or row.get("name") or symbol,
            "asset_type": (row.get("asset_type") or "stock").lower(),
            "market": row.get("market") or "US",
            "venue": row.get("exchange") or row.get("venue") or row.get("provider") or "csv_import",
            "currency": row.get("currency") or default_currency,
            "quantity": quantity,
            "average_cost": average_cost or 0,
            "current_price": price or 0,
            "market_value": market_value,
            "transaction_date": row.get("transaction_date") or row.get("timestamp") or "",
            "action": (row.get("action") or row.get("transaction_type") or "").upper(),
            "notes": row.get("notes") or "",
        }

    def _get_or_create_account(
        self,
        *,
        name: str,
        account_type: str,
        broker: str,
        base_currency: str,
    ) -> tuple[Account, bool]:
        account = self.db.scalar(select(Account).where(Account.name == name).limit(1))
        if account:
            return account, False
        account = Account(
            name=name,
            account_type=account_type,
            broker=broker,
            base_currency=base_currency,
            mode="read_only",
            live_trading_enabled=False,
        )
        self.db.add(account)
        self.db.flush()
        write_audit_log(
            self.db,
            action="csv_import.account_created_read_only",
            entity_type="Account",
            entity_id=account.id,
            payload_json={"name": name, "broker": broker, "read_only": True},
            actor_id="v4-csv-import-service",
        )
        return account, True

    def _get_or_create_asset(self, row: dict[str, Any], *, source_name: str) -> tuple[Asset, bool]:
        asset = self.db.scalar(select(Asset).where(Asset.symbol == row["asset_symbol"]).limit(1))
        if asset:
            return asset, False
        asset = Asset(
            symbol=row["asset_symbol"],
            name=row["asset_name"],
            asset_type=row["asset_type"],
            market=row["market"],
            venue=row["venue"],
            currency=row["currency"],
            tradable=False,
            manual_enabled=False,
            auto_enabled=False,
            risk_level="medium",
        )
        self.db.add(asset)
        self.db.flush()
        write_audit_log(
            self.db,
            action="csv_import.asset_created_read_only",
            entity_type="Asset",
            entity_id=asset.id,
            payload_json={"symbol": asset.symbol, "source": source_name, "read_only": True},
            actor_id="v4-csv-import-service",
        )
        return asset, True

    def _upsert_position(self, account: Account, asset: Asset, row: dict[str, Any]) -> Position:
        position = self.db.scalar(
            select(Position).where(Position.account_id == account.id, Position.asset_id == asset.id).limit(1)
        )
        market_value = row["market_value"]
        unrealized_pnl = market_value - (row["quantity"] * row["average_cost"])
        if position is None:
            position = Position(
                account_id=account.id,
                asset_id=asset.id,
                quantity=row["quantity"],
                average_cost=row["average_cost"],
                market_price=row["current_price"],
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=0,
                weight=0,
            )
            self.db.add(position)
        else:
            position.quantity = row["quantity"]
            position.average_cost = row["average_cost"]
            position.market_price = row["current_price"]
            position.market_value = market_value
            position.unrealized_pnl = unrealized_pnl
        self.db.flush()
        write_audit_log(
            self.db,
            action="csv_import.position_upserted_read_only",
            entity_type="Position",
            entity_id=position.id,
            payload_json={"account_id": account.id, "asset_id": asset.id, "symbol": asset.symbol, "read_only": True},
            actor_id="v4-csv-import-service",
        )
        return position

    def _create_portfolio_snapshot(
        self,
        account_ids: set[str],
        rows: list[dict[str, Any]],
        default_currency: str,
    ) -> PortfolioSnapshot:
        cash_value = sum(row["market_value"] for row in rows if row["asset_type"] == "cash")
        positions_value = sum(row["market_value"] for row in rows if row["asset_type"] != "cash")
        total_value = cash_value + positions_value
        snapshot = PortfolioSnapshot(
            account_id=next(iter(account_ids)) if len(account_ids) == 1 else None,
            total_value=total_value,
            cash_value=cash_value,
            positions_value=positions_value,
            currency=rows[0].get("currency") or default_currency,
            snapshot_json={
                "source": "csv_import",
                "account_ids": sorted(account_ids),
                "position_count": len([row for row in rows if row["asset_type"] != "cash"]),
                "cash_rows": len([row for row in rows if row["asset_type"] == "cash"]),
            },
        )
        self.db.add(snapshot)
        self.db.flush()
        write_audit_log(
            self.db,
            action="csv_import.portfolio_snapshot_created",
            entity_type="PortfolioSnapshot",
            entity_id=snapshot.id,
            payload_json={"total_value": total_value, "read_only": True},
            actor_id="v4-csv-import-service",
        )
        return snapshot

    def _normalize_column(self, column: str) -> str:
        return column.strip().lower().replace(" ", "_").replace("-", "_")

    def _number(self, value: str | None, *, field: str) -> float:
        if value is None or value == "":
            raise CsvImportError(f"{field} is required")
        try:
            return float(str(value).replace(",", ""))
        except ValueError as exc:
            raise CsvImportError(f"{field} must be numeric") from exc

    def _optional_number(self, value: str | None) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace(",", ""))
        except ValueError as exc:
            raise CsvImportError("numeric column contains an invalid value") from exc
