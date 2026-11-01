from dataclasses import dataclass
from decimal import Decimal
from decimal import ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import Account
from app.models import Asset
from app.models import PortfolioSnapshot
from app.models import Position


ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class PositionView:
    id: str
    account_id: str
    account_name: str
    asset_id: str
    symbol: str
    asset_type: str
    quantity: Decimal
    average_cost: Decimal
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    weight: Decimal
    daily_pnl: Decimal


class PositionValuationService:
    def __init__(self, db: Session):
        self.db = db

    def get_current_positions(self, account_id: str | None = None) -> list[PositionView]:
        statement = select(Position)
        if account_id:
            statement = statement.where(Position.account_id == account_id)
        positions = list(self.db.scalars(statement).all())
        assets = {asset.id: asset for asset in self.db.scalars(select(Asset)).all()}
        accounts = {account.id: account for account in self.db.scalars(select(Account)).all()}
        total_value = sum((to_decimal(position.market_value) for position in positions), ZERO)

        views: list[PositionView] = []
        for position in positions:
            asset = assets[position.asset_id]
            account = accounts[position.account_id]
            market_value = to_decimal(position.market_value)
            market_price = to_decimal(position.market_price)
            quantity = to_decimal(position.quantity)
            average_cost = to_decimal(position.average_cost)
            unrealized_pnl = (market_price - average_cost) * quantity
            weight = safe_divide(market_value, total_value)

            position.market_value = market_value
            position.unrealized_pnl = unrealized_pnl
            position.weight = weight

            views.append(
                PositionView(
                    id=position.id,
                    account_id=position.account_id,
                    account_name=account.name,
                    asset_id=position.asset_id,
                    symbol=asset.symbol,
                    asset_type=asset.asset_type,
                    quantity=quantity,
                    average_cost=average_cost,
                    market_price=market_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=to_decimal(position.realized_pnl),
                    weight=weight,
                    daily_pnl=ZERO,
                )
            )

        return views


class PortfolioSummaryService:
    def __init__(self, db: Session):
        self.db = db
        self.valuation = PositionValuationService(db)

    def resolve_account_id(self, account_id: str | None) -> str | None:
        if account_id != "default":
            return account_id
        demo_account = self.db.scalar(
            select(Account.id).where(Account.name == "demo_primary_paper_account").limit(1)
        )
        return demo_account

    def build_current(self, account_id: str | None = None) -> dict:
        resolved_account_id = self.resolve_account_id(account_id)
        positions = self.valuation.get_current_positions(resolved_account_id)
        total_equity = sum((position.market_value for position in positions), ZERO)
        cash = sum((position.market_value for position in positions if is_cash_like(position.asset_type)), ZERO)
        allocation_values = self._allocation_values(positions)

        return {
            "total_equity": money(total_equity),
            "cash": money(cash),
            "allocation": ratio_map(allocation_values, total_equity),
            "positions": [position_to_dict(position) for position in positions],
        }

    def build_daily_summary(self, account_id: str | None = None) -> dict:
        resolved_account_id = self.resolve_account_id(account_id)
        current = self.build_current(resolved_account_id)
        positions = [position for position in self.valuation.get_current_positions(resolved_account_id)]
        top_winners = sorted(positions, key=lambda position: position.unrealized_pnl, reverse=True)[:3]
        top_losers = sorted(positions, key=lambda position: position.unrealized_pnl)[:3]
        concentration_risks = self._concentration_risks(positions)
        suggested_attention = self._suggested_attention(positions, concentration_risks)

        return {
            "total_equity": current["total_equity"],
            "cash": current["cash"],
            "allocation": {
                "stocks": current["allocation"].get("stocks", 0),
                "crypto": current["allocation"].get("crypto", 0),
                "stablecoin": current["allocation"].get("stablecoin", 0),
                "cash": current["allocation"].get("cash", 0),
            },
            "daily_pnl": 0,
            "top_winners": [summary_position(position) for position in top_winners if position.unrealized_pnl > 0],
            "top_losers": [summary_position(position) for position in top_losers if position.unrealized_pnl < 0],
            "concentration_risks": concentration_risks,
            "suggested_attention": suggested_attention,
        }

    def _allocation_values(self, positions: list[PositionView]) -> dict[str, Decimal]:
        allocation = {"stocks": ZERO, "crypto": ZERO, "stablecoin": ZERO, "cash": ZERO}
        for position in positions:
            category = allocation_category(position.asset_type)
            allocation[category] += position.market_value
        return allocation

    def _concentration_risks(self, positions: list[PositionView]) -> list[dict]:
        risks: list[dict] = []
        for position in sorted(positions, key=lambda item: item.weight, reverse=True):
            if position.weight >= Decimal("0.25"):
                risks.append(
                    {
                        "type": "position_concentration",
                        "symbol": position.symbol,
                        "weight": ratio(position.weight),
                        "message": f"{position.symbol} is {ratio(position.weight)} of total equity.",
                    }
                )
        return risks

    def _suggested_attention(self, positions: list[PositionView], risks: list[dict]) -> list[str]:
        attention: list[str] = []
        if risks:
            attention.append("Review concentrated positions before adding exposure.")
        if any(position.unrealized_pnl < 0 for position in positions):
            attention.append("Review unrealized losers for thesis drift.")
        if not positions:
            attention.append("Import positions before generating portfolio conclusions.")
        return attention


class PortfolioSnapshotService:
    def __init__(self, db: Session):
        self.db = db
        self.summary = PortfolioSummaryService(db)

    def create_snapshot(self) -> PortfolioSnapshot:
        current = self.summary.build_current()
        snapshot = PortfolioSnapshot(
            account_id=None,
            total_value=current["total_equity"],
            cash_value=current["cash"],
            positions_value=current["total_equity"] - current["cash"],
            currency="USD",
            snapshot_json=current,
        )
        self.db.add(snapshot)
        self.db.flush()
        write_audit_log(
            self.db,
            action="portfolio_snapshot.created_from_current",
            entity_type="PortfolioSnapshot",
            entity_id=snapshot.id,
            payload_json={"source": "portfolio_memory", "total_equity": current["total_equity"]},
            actor_id="phase3-portfolio-memory",
        )
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot


def allocation_category(asset_type: str) -> str:
    normalized = asset_type.lower()
    if normalized in {"stock", "etf"}:
        return "stocks"
    if normalized == "stablecoin":
        return "stablecoin"
    if normalized in {"crypto", "token"}:
        return "crypto"
    if normalized == "cash":
        return "cash"
    return "crypto"


def is_cash_like(asset_type: str) -> bool:
    return asset_type.lower() in {"cash", "stablecoin"}


def to_decimal(value) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def safe_divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == ZERO:
        return ZERO
    return numerator / denominator


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def ratio(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def ratio_map(values: dict[str, Decimal], total: Decimal) -> dict[str, float]:
    return {key: ratio(safe_divide(value, total)) for key, value in values.items()}


def position_to_dict(position: PositionView) -> dict:
    return {
        "id": position.id,
        "account_id": position.account_id,
        "account_name": position.account_name,
        "asset_id": position.asset_id,
        "symbol": position.symbol,
        "asset_type": position.asset_type,
        "quantity": money(position.quantity),
        "average_cost": money(position.average_cost),
        "market_price": money(position.market_price),
        "market_value": money(position.market_value),
        "unrealized_pnl": money(position.unrealized_pnl),
        "realized_pnl": money(position.realized_pnl),
        "weight": ratio(position.weight),
        "daily_pnl": money(position.daily_pnl),
    }


def summary_position(position: PositionView) -> dict:
    return {
        "symbol": position.symbol,
        "asset_type": position.asset_type,
        "market_value": money(position.market_value),
        "unrealized_pnl": money(position.unrealized_pnl),
        "weight": ratio(position.weight),
    }
