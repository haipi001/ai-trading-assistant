from decimal import Decimal
from datetime import datetime
from datetime import timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.mock import MOCK_ASSETS
from app.adapters.mock import MOCK_QUOTES
from app.adapters.mock import MockCryptoExchangeAdapter
from app.adapters.mock import MockOnchainReadAdapter
from app.adapters.mock import MockStockBrokerAdapter
from app.adapters.types import AdapterAccount
from app.adapters.types import AdapterAsset
from app.adapters.types import AdapterBalance
from app.adapters.types import AdapterPosition
from app.adapters.types import AdapterQuote
from app.api.domain import write_audit_log
from app.models import Account
from app.models import Asset
from app.models import Position
from app.models import Quote


def get_or_create_asset(db: Session, adapter_asset: AdapterAsset) -> Asset:
    asset = db.scalar(select(Asset).where(Asset.symbol == adapter_asset.symbol))
    if asset:
        return asset

    asset = Asset(
        symbol=adapter_asset.symbol,
        name=adapter_asset.name,
        asset_type=adapter_asset.asset_type,
        market=adapter_asset.market,
        venue=adapter_asset.venue,
        currency=adapter_asset.currency,
        chain_id=adapter_asset.chain_id,
        contract_address=adapter_asset.contract_address,
        tradable=adapter_asset.tradable,
        manual_enabled=adapter_asset.manual_enabled,
        auto_enabled=adapter_asset.auto_enabled,
        risk_level=adapter_asset.risk_level,
    )
    db.add(asset)
    db.flush()
    write_audit_log(
        db,
        action="mock_asset.imported",
        entity_type="Asset",
        entity_id=asset.id,
        payload_json={"symbol": asset.symbol, "source": "mock"},
        actor_id="phase2-mock-import",
    )
    return asset


def get_or_create_account(db: Session, adapter_account: AdapterAccount) -> Account:
    account = db.scalar(select(Account).where(Account.name == adapter_account.name))
    if account:
        return account

    account = Account(
        name=adapter_account.name,
        account_type=adapter_account.account_type,
        broker=adapter_account.broker,
        base_currency=adapter_account.base_currency,
        mode=adapter_account.mode,
        live_trading_enabled=False,
    )
    db.add(account)
    db.flush()
    write_audit_log(
        db,
        action="mock_account.imported",
        entity_type="Account",
        entity_id=account.id,
        payload_json={"name": account.name, "source": "mock"},
        actor_id="phase2-mock-import",
    )
    return account


def import_mock_accounts(db: Session) -> dict:
    stock = MockStockBrokerAdapter()
    accounts = [
        *stock.get_accounts(),
        AdapterAccount("crypto_paper_account", "crypto", "mock_crypto_exchange", "USD", "mock", False),
        AdapterAccount("onchain_watch_wallet", "onchain_wallet", "mock_onchain", "USD", "watch_only", False),
    ]

    imported = [get_or_create_account(db, account).name for account in accounts]
    db.commit()
    return {"accounts": imported, "count": len(imported)}


def import_mock_positions(db: Session) -> dict:
    import_mock_accounts(db)
    imported_assets = [get_or_create_asset(db, asset) for asset in MOCK_ASSETS.values()]
    asset_by_symbol = {asset.symbol: asset for asset in imported_assets}
    account_by_name = {account.name: account for account in db.scalars(select(Account)).all()}

    stock_positions = MockStockBrokerAdapter().get_positions(account_by_name["stock_paper_account"])
    crypto_balances = MockCryptoExchangeAdapter().get_balances()
    onchain_balances = MockOnchainReadAdapter().get_wallet_balances("0xmockwatchwallet", "ethereum")

    positions = [
        *positions_from_adapter(stock_positions, account_by_name, asset_by_symbol),
        *positions_from_balances(crypto_balances, account_by_name, asset_by_symbol),
        *positions_from_balances(onchain_balances, account_by_name, asset_by_symbol),
    ]

    for position in positions:
        db.add(position)
        db.flush()
        write_audit_log(
            db,
            action="mock_position.imported",
            entity_type="Position",
            entity_id=position.id,
            payload_json={"account_id": position.account_id, "asset_id": position.asset_id, "source": "mock"},
            actor_id="phase2-mock-import",
        )

    db.commit()
    return {"positions": len(positions)}


def update_mock_quotes(db: Session) -> dict:
    for adapter_asset in MOCK_ASSETS.values():
        get_or_create_asset(db, adapter_asset)

    assets = {asset.symbol: asset for asset in db.scalars(select(Asset)).all()}
    quotes = [create_quote(assets[symbol], adapter_quote) for symbol, adapter_quote in MOCK_QUOTES.items()]

    for quote in quotes:
        db.add(quote)
        db.flush()
        write_audit_log(
            db,
            action="mock_quote.updated",
            entity_type="Quote",
            entity_id=quote.id,
            payload_json={"asset_id": quote.asset_id, "price": float(quote.price), "source": quote.source},
            actor_id="phase2-mock-import",
        )

    update_positions_from_quotes(db, {symbol: quote.price for symbol, quote in MOCK_QUOTES.items()})
    db.commit()
    return {"quotes": len(quotes)}


def positions_from_adapter(
    adapter_positions: Iterable[AdapterPosition],
    accounts: dict[str, Account],
    assets: dict[str, Asset],
) -> list[Position]:
    return [
        build_position(
            account=accounts[position.account_name],
            asset=assets[position.symbol],
            quantity=position.quantity,
            average_cost=position.average_cost,
            market_price=position.market_price,
        )
        for position in adapter_positions
    ]


def positions_from_balances(
    balances: Iterable[AdapterBalance],
    accounts: dict[str, Account],
    assets: dict[str, Asset],
) -> list[Position]:
    return [
        build_position(
            account=accounts[balance.account_name],
            asset=assets[balance.symbol],
            quantity=balance.quantity,
            average_cost=balance.market_price,
            market_price=balance.market_price,
        )
        for balance in balances
    ]


def build_position(account: Account, asset: Asset, quantity: float, average_cost: float, market_price: float) -> Position:
    market_value = Decimal(str(quantity)) * Decimal(str(market_price))
    unrealized_pnl = (Decimal(str(market_price)) - Decimal(str(average_cost))) * Decimal(str(quantity))
    return Position(
        account_id=account.id,
        asset_id=asset.id,
        quantity=quantity,
        average_cost=average_cost,
        market_price=market_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=0,
        weight=0,
    )


def create_quote(asset: Asset, adapter_quote: AdapterQuote) -> Quote:
    return Quote(
        asset_id=asset.id,
        price=adapter_quote.price,
        bid=adapter_quote.bid,
        ask=adapter_quote.ask,
        source=adapter_quote.source,
        as_of=adapter_quote.as_of or datetime.now(timezone.utc),
    )


def update_positions_from_quotes(db: Session, prices_by_symbol: dict[str, float]) -> None:
    assets = {asset.id: asset for asset in db.scalars(select(Asset)).all()}
    positions = db.scalars(select(Position)).all()

    for position in positions:
        asset = assets.get(position.asset_id)
        if not asset or asset.symbol not in prices_by_symbol:
            continue

        market_price = Decimal(str(prices_by_symbol[asset.symbol]))
        quantity = Decimal(str(position.quantity))
        average_cost = Decimal(str(position.average_cost))
        position.market_price = market_price
        position.market_value = quantity * market_price
        position.unrealized_pnl = (market_price - average_cost) * quantity
