from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AdapterAsset:
    symbol: str
    name: str
    asset_type: str
    market: str
    venue: str
    currency: str
    chain_id: str | None = None
    contract_address: str | None = None
    tradable: bool = False
    manual_enabled: bool = False
    auto_enabled: bool = False
    risk_level: str = "medium"


@dataclass(frozen=True)
class AdapterAccount:
    name: str
    account_type: str
    broker: str
    base_currency: str
    mode: str = "mock"
    live_trading_enabled: bool = False


@dataclass(frozen=True)
class AdapterPosition:
    account_name: str
    symbol: str
    quantity: float
    average_cost: float
    market_price: float


@dataclass(frozen=True)
class AdapterQuote:
    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    source: str = "mock"
    as_of: datetime | None = None


@dataclass(frozen=True)
class AdapterCandle:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "mock"


@dataclass(frozen=True)
class AdapterOrder:
    id: str
    status: str
    symbol: str
    side: str
    quantity: float


@dataclass(frozen=True)
class AdapterBalance:
    account_name: str
    symbol: str
    quantity: float
    market_price: float


@dataclass(frozen=True)
class AdapterTransfer:
    tx_hash: str
    symbol: str
    quantity: float
    direction: str
    timestamp: datetime


@dataclass(frozen=True)
class AdapterAllowance:
    symbol: str
    spender: str
    allowance: float
