from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app.adapters.interfaces import BrokerAdapter
from app.adapters.interfaces import CryptoExchangeAdapter
from app.adapters.interfaces import MarketDataAdapter
from app.adapters.interfaces import OnchainReadAdapter
from app.adapters.types import AdapterAccount
from app.adapters.types import AdapterAllowance
from app.adapters.types import AdapterAsset
from app.adapters.types import AdapterBalance
from app.adapters.types import AdapterCandle
from app.adapters.types import AdapterOrder
from app.adapters.types import AdapterPosition
from app.adapters.types import AdapterQuote
from app.adapters.types import AdapterTransfer


MOCK_ASSETS: dict[str, AdapterAsset] = {
    "AAPL": AdapterAsset("AAPL", "Apple Inc.", "stock", "US", "NASDAQ", "USD", tradable=True, manual_enabled=True),
    "NVDA": AdapterAsset("NVDA", "NVIDIA Corporation", "stock", "US", "NASDAQ", "USD", tradable=True, manual_enabled=True),
    "SPY": AdapterAsset("SPY", "SPDR S&P 500 ETF Trust", "etf", "US", "NYSEARCA", "USD", tradable=True, manual_enabled=True),
    "BTC": AdapterAsset("BTC", "Bitcoin", "crypto", "GLOBAL", "CEX", "USD", tradable=True, manual_enabled=True),
    "ETH": AdapterAsset("ETH", "Ether", "crypto", "GLOBAL", "CEX", "USD", tradable=True, manual_enabled=True),
    "SOL": AdapterAsset("SOL", "Solana", "crypto", "GLOBAL", "CEX", "USD", tradable=True, manual_enabled=True),
    "USDC": AdapterAsset(
        "USDC",
        "USD Coin",
        "stablecoin",
        "GLOBAL",
        "ONCHAIN",
        "USD",
        chain_id="1",
        contract_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        tradable=True,
        manual_enabled=True,
        risk_level="low",
    ),
}

MOCK_QUOTES: dict[str, AdapterQuote] = {
    "AAPL": AdapterQuote("AAPL", 225.12, 225.1, 225.14),
    "NVDA": AdapterQuote("NVDA", 182.75, 182.7, 182.8),
    "SPY": AdapterQuote("SPY", 625.4, 625.38, 625.42),
    "BTC": AdapterQuote("BTC", 105250.0, 105200.0, 105300.0),
    "ETH": AdapterQuote("ETH", 3650.0, 3648.0, 3652.0),
    "SOL": AdapterQuote("SOL", 178.25, 178.1, 178.4),
    "USDC": AdapterQuote("USDC", 1.0, 0.9999, 1.0001),
}


class MockStockBrokerAdapter(MarketDataAdapter, BrokerAdapter):
    def get_accounts(self) -> list[AdapterAccount]:
        return [
            AdapterAccount(
                name="stock_paper_account",
                account_type="stock",
                broker="mock_stock",
                base_currency="USD",
                mode="mock",
            )
        ]

    def get_positions(self, account) -> list[AdapterPosition]:
        return [
            AdapterPosition("stock_paper_account", "AAPL", 12, 190.0, MOCK_QUOTES["AAPL"].price),
            AdapterPosition("stock_paper_account", "NVDA", 8, 145.0, MOCK_QUOTES["NVDA"].price),
            AdapterPosition("stock_paper_account", "SPY", 5, 510.0, MOCK_QUOTES["SPY"].price),
        ]

    def get_orders(self, account) -> list[AdapterOrder]:
        return []

    def place_order(self, order_draft):
        raise NotImplementedError("MockStockBrokerAdapter does not place orders in Phase 2.")

    def get_quote(self, asset) -> AdapterQuote:
        symbol = asset.symbol if hasattr(asset, "symbol") else str(asset)
        return MOCK_QUOTES[symbol]

    def get_candles(self, asset, timeframe: str, start: datetime, end: datetime) -> list[AdapterCandle]:
        symbol = asset.symbol if hasattr(asset, "symbol") else str(asset)
        quote = MOCK_QUOTES[symbol]
        return build_mock_candles(symbol, timeframe, quote.price, start, end)


class MockCryptoExchangeAdapter(CryptoExchangeAdapter):
    def get_balances(self) -> list[AdapterBalance]:
        return [
            AdapterBalance("crypto_paper_account", "BTC", 0.15, MOCK_QUOTES["BTC"].price),
            AdapterBalance("crypto_paper_account", "ETH", 2.5, MOCK_QUOTES["ETH"].price),
            AdapterBalance("crypto_paper_account", "SOL", 40, MOCK_QUOTES["SOL"].price),
            AdapterBalance("crypto_paper_account", "USDC", 2500, MOCK_QUOTES["USDC"].price),
        ]

    def get_ticker(self, symbol: str) -> AdapterQuote:
        return MOCK_QUOTES[symbol]

    def get_ohlcv(self, symbol: str, timeframe: str) -> list[AdapterCandle]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=5)
        return build_mock_candles(symbol, timeframe, MOCK_QUOTES[symbol].price, start, end)


class MockOnchainReadAdapter(OnchainReadAdapter):
    def get_wallet_balances(self, address: str, chain: str) -> list[AdapterBalance]:
        return [
            AdapterBalance("onchain_watch_wallet", "ETH", 1.25, MOCK_QUOTES["ETH"].price),
            AdapterBalance("onchain_watch_wallet", "USDC", 1250, MOCK_QUOTES["USDC"].price),
        ]

    def get_token_transfers(self, address: str, chain: str) -> list[AdapterTransfer]:
        now = datetime.now(timezone.utc)
        return [
            AdapterTransfer("0xmocktransfer1", "USDC", 250, "in", now - timedelta(days=1)),
            AdapterTransfer("0xmocktransfer2", "ETH", 0.1, "out", now - timedelta(days=2)),
        ]

    def get_allowances(self, address: str, chain: str) -> list[AdapterAllowance]:
        return [
            AdapterAllowance("USDC", "0xmockspender000000000000000000000000000000000", 0),
            AdapterAllowance("ETH", "0xmockspender000000000000000000000000000000001", 0),
        ]


def build_mock_candles(symbol: str, timeframe: str, base_price: float, start: datetime, end: datetime) -> list[AdapterCandle]:
    candles: list[AdapterCandle] = []
    current = start
    step = timedelta(days=1) if timeframe in {"1d", "day"} else timedelta(hours=1)
    index = 0

    while current <= end and len(candles) < 100:
        close = base_price * (1 + (index % 5 - 2) * 0.002)
        candles.append(
            AdapterCandle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=current,
                open=close * 0.995,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=1000 + index * 10,
            )
        )
        current += step
        index += 1

    return candles
