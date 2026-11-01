from abc import ABC
from abc import abstractmethod
from datetime import datetime

from app.adapters.types import AdapterAccount
from app.adapters.types import AdapterAllowance
from app.adapters.types import AdapterBalance
from app.adapters.types import AdapterCandle
from app.adapters.types import AdapterOrder
from app.adapters.types import AdapterPosition
from app.adapters.types import AdapterQuote


class MarketDataAdapter(ABC):
    @abstractmethod
    def get_quote(self, asset) -> AdapterQuote:
        raise NotImplementedError

    @abstractmethod
    def get_candles(self, asset, timeframe: str, start: datetime, end: datetime) -> list[AdapterCandle]:
        raise NotImplementedError


class BrokerAdapter(ABC):
    @abstractmethod
    def get_accounts(self) -> list[AdapterAccount]:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self, account) -> list[AdapterPosition]:
        raise NotImplementedError

    @abstractmethod
    def get_orders(self, account) -> list[AdapterOrder]:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order_draft):
        raise NotImplementedError("Mock adapters do not implement order placement in Phase 2.")


class CryptoExchangeAdapter(ABC):
    @abstractmethod
    def get_balances(self) -> list[AdapterBalance]:
        raise NotImplementedError

    @abstractmethod
    def get_ticker(self, symbol: str) -> AdapterQuote:
        raise NotImplementedError

    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str) -> list[AdapterCandle]:
        raise NotImplementedError


class OnchainReadAdapter(ABC):
    @abstractmethod
    def get_wallet_balances(self, address: str, chain: str) -> list[AdapterBalance]:
        raise NotImplementedError

    @abstractmethod
    def get_token_transfers(self, address: str, chain: str) -> list:
        raise NotImplementedError

    @abstractmethod
    def get_allowances(self, address: str, chain: str) -> list[AdapterAllowance]:
        raise NotImplementedError
