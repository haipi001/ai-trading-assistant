import csv
import hashlib
import hmac
import json
import os
import ssl
import time
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from io import StringIO
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.parse import quote
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen

from app.adapters.mock import build_mock_candles
from app.adapters.mock import MOCK_QUOTES
from app.adapters.types import AdapterCandle
from app.adapters.types import AdapterQuote

try:
    import certifi
except ImportError:  # pragma: no cover - runtime fallback when certifi is unavailable
    certifi = None


@dataclass(frozen=True)
class AdapterHealth:
    provider: str
    status: str
    checked_at: datetime
    latency_ms: float | None
    message: str
    details: dict[str, Any]


@dataclass(frozen=True)
class ReadOnlyAccountSnapshot:
    provider: str
    account: dict[str, Any]
    balances: list[dict[str, Any]]
    positions: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    as_of: datetime
    warnings: list[str]


class ReadOnlyMarketDataAdapter(ABC):
    provider: str
    capabilities: list[str]

    @abstractmethod
    def health_check(self) -> AdapterHealth:
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, symbol: str) -> AdapterQuote:
        raise NotImplementedError

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        raise NotImplementedError


def open_readonly_url(request: Request, *, timeout: float):
    context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    return urlopen(request, timeout=timeout, context=context)


class MockReadOnlyMarketDataAdapter(ReadOnlyMarketDataAdapter):
    provider = "mock_market_data"
    capabilities = ["quotes", "symbols", "offline_tests"]

    def health_check(self) -> AdapterHealth:
        return AdapterHealth(
            provider=self.provider,
            status="ok",
            checked_at=datetime.now(timezone.utc),
            latency_ms=0,
            message="Deterministic read-only mock market data is available.",
            details={"symbols": sorted(MOCK_QUOTES.keys()), "read_only": True},
        )

    def get_quote(self, symbol: str) -> AdapterQuote:
        normalized = symbol.upper()
        if normalized not in MOCK_QUOTES:
            raise ValueError(f"mock quote unavailable for symbol: {normalized}")
        quote = MOCK_QUOTES[normalized]
        return AdapterQuote(
            symbol=normalized,
            price=quote.price,
            bid=quote.bid,
            ask=quote.ask,
            source=self.provider,
            as_of=datetime.now(timezone.utc),
        )

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        normalized = symbol.upper()
        if normalized not in MOCK_QUOTES:
            raise ValueError(f"mock candles unavailable for symbol: {normalized}")
        if limit <= 0:
            raise ValueError("candle limit must be positive")
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if timeframe == "1d":
            end = end.replace(hour=0)
            start = end - timedelta(days=limit - 1)
        elif timeframe == "1h":
            start = end - timedelta(hours=limit - 1)
        else:
            raise ValueError(f"unsupported timeframe for mock_market_data: {timeframe}")
        return build_mock_candles(normalized, timeframe, MOCK_QUOTES[normalized].price, start, end)[:limit]


class StooqPublicMarketDataAdapter(ReadOnlyMarketDataAdapter):
    provider = "stooq_public_eod"
    capabilities = ["quotes", "delayed_public_market_data", "no_credentials"]
    quote_endpoint = "https://stooq.com/q/l/"
    candles_endpoint = "https://stooq.com/q/d/l/"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def health_check(self) -> AdapterHealth:
        started_at = time.perf_counter()
        checked_at = datetime.now(timezone.utc)
        try:
            quote = self.get_quote(str(self.config.get("health_symbol", "AAPL")))
        except Exception as exc:
            return AdapterHealth(
                provider=self.provider,
                status="unavailable",
                checked_at=checked_at,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                message=f"Stooq public quote endpoint is unavailable: {exc}",
                details={"read_only": True, "network_required": True},
            )

        return AdapterHealth(
            provider=self.provider,
            status="ok",
            checked_at=checked_at,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            message=f"Stooq public quote endpoint returned {quote.symbol} at {quote.price}.",
            details={"read_only": True, "network_required": True, "sample_symbol": quote.symbol},
        )

    def get_quote(self, symbol: str) -> AdapterQuote:
        normalized = symbol.upper()
        provider_symbol = self._provider_symbol(normalized)
        query = urlencode({"s": provider_symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"})
        url = f"{self.quote_endpoint}?{query}"
        timeout = float(self.config.get("timeout_seconds", 5))
        request = Request(url, headers={"User-Agent": "ai-trading-os-readonly/0.1"})

        try:
            with open_readonly_url(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except URLError as exc:
            raise ValueError(f"network error while fetching {normalized}") from exc

        rows = list(csv.DictReader(StringIO(body)))
        if not rows:
            raise ValueError(f"empty Stooq response for {normalized}")

        row = rows[0]
        close_value = row.get("Close") or row.get("Last")
        if not close_value or close_value.upper() == "N/D":
            raise ValueError(f"Stooq quote unavailable for {normalized}")

        as_of = self._parse_as_of(row.get("Date"), row.get("Time"))
        return AdapterQuote(
            symbol=normalized,
            price=float(close_value),
            source=self.provider,
            as_of=as_of,
        )

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        if timeframe != "1d":
            raise ValueError("stooq_public_eod supports daily candles only")
        if limit <= 0:
            raise ValueError("candle limit must be positive")

        normalized = symbol.upper()
        provider_symbol = self._provider_symbol(normalized)
        query = urlencode({"s": provider_symbol, "i": "d"})
        url = f"{self.candles_endpoint}?{query}"
        timeout = float(self.config.get("timeout_seconds", 5))
        request = Request(url, headers={"User-Agent": "ai-trading-os-readonly/0.1"})

        try:
            with open_readonly_url(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except URLError as exc:
            raise ValueError(f"network error while fetching candles for {normalized}") from exc

        rows = list(csv.DictReader(StringIO(body)))
        if not rows:
            raise ValueError(f"empty Stooq candle response for {normalized}")

        candles: list[AdapterCandle] = []
        for row in rows[-limit:]:
            close_value = row.get("Close")
            open_value = row.get("Open")
            high_value = row.get("High")
            low_value = row.get("Low")
            volume_value = row.get("Volume")
            date_value = row.get("Date")
            if not date_value or not close_value or close_value.upper() == "N/D":
                continue
            try:
                timestamp = datetime.fromisoformat(date_value).replace(tzinfo=timezone.utc)
                candles.append(
                    AdapterCandle(
                        symbol=normalized,
                        timeframe=timeframe,
                        timestamp=timestamp,
                        open=float(open_value or close_value),
                        high=float(high_value or close_value),
                        low=float(low_value or close_value),
                        close=float(close_value),
                        volume=float(volume_value or 0),
                        source=self.provider,
                    )
                )
            except ValueError:
                continue

        if not candles:
            raise ValueError(f"Stooq candles unavailable for {normalized}")
        return candles

    def _provider_symbol(self, symbol: str) -> str:
        symbol_map = self.config.get("symbol_map", {})
        if isinstance(symbol_map, dict) and symbol in symbol_map:
            return str(symbol_map[symbol]).lower()
        if "." in symbol:
            return symbol.lower()
        suffix = str(self.config.get("default_suffix", ".us"))
        return f"{symbol}{suffix}".lower()

    def _parse_as_of(self, date_value: str | None, time_value: str | None) -> datetime:
        if not date_value:
            return datetime.now(timezone.utc)
        try:
            if time_value:
                return datetime.fromisoformat(f"{date_value}T{time_value}").replace(tzinfo=timezone.utc)
            return datetime.fromisoformat(date_value).replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)


class YahooFinancePublicMarketDataAdapter(ReadOnlyMarketDataAdapter):
    provider = "yfinance_public"
    capabilities = ["quotes", "candles", "hourly_intraday", "no_credentials"]
    chart_endpoints = (
        "https://query1.finance.yahoo.com/v8/finance/chart/",
        "https://query2.finance.yahoo.com/v8/finance/chart/",
    )

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def health_check(self) -> AdapterHealth:
        started_at = time.perf_counter()
        checked_at = datetime.now(timezone.utc)
        sample_symbol = str(self.config.get("health_symbol", "AAPL"))
        try:
            quote = self.get_quote(sample_symbol)
        except Exception as exc:
            return AdapterHealth(
                provider=self.provider,
                status="unavailable",
                checked_at=checked_at,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                message=f"Yahoo Finance public chart endpoint is unavailable: {exc}",
                details={"read_only": True, "network_required": True},
            )

        return AdapterHealth(
            provider=self.provider,
            status="ok",
            checked_at=checked_at,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            message=f"Yahoo Finance public chart endpoint returned {quote.symbol} at {quote.price}.",
            details={"read_only": True, "network_required": True, "sample_symbol": quote.symbol},
        )

    def get_quote(self, symbol: str) -> AdapterQuote:
        normalized = symbol.upper()
        payload = self._fetch_chart_payload(normalized, timeframe="1d", limit=5)
        result = self._first_result(payload, normalized)
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        if price in (None, ""):
            candles = self._extract_candles(result, normalized, "1d")
            if not candles:
                raise ValueError(f"Yahoo Finance quote unavailable for {normalized}")
            latest = candles[-1]
            price = latest.close

        market_time = meta.get("regularMarketTime")
        as_of = self._parse_epoch(market_time) if market_time else None
        if as_of is None:
            candles = self._extract_candles(result, normalized, "1d")
            as_of = candles[-1].timestamp if candles else datetime.now(timezone.utc)

        return AdapterQuote(
            symbol=normalized,
            price=float(price),
            bid=float(meta["bid"]) if meta.get("bid") is not None else None,
            ask=float(meta["ask"]) if meta.get("ask") is not None else None,
            source=self.provider,
            as_of=as_of,
            currency=meta.get("currency"),
        )

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        if timeframe not in {"1d", "1h"}:
            raise ValueError("yfinance_public supports 1d and 1h candles only")
        if limit <= 0:
            raise ValueError("candle limit must be positive")

        normalized = symbol.upper()
        payload = self._fetch_chart_payload(normalized, timeframe=timeframe, limit=limit)
        result = self._first_result(payload, normalized)
        candles = self._extract_candles(result, normalized, timeframe)
        if not candles:
            raise ValueError(f"Yahoo Finance candles unavailable for {normalized}")
        return candles[-limit:]

    def _fetch_chart_payload(self, symbol: str, *, timeframe: str, limit: int) -> dict[str, Any]:
        interval = "1d" if timeframe == "1d" else "1h"
        end = datetime.now(timezone.utc)
        if timeframe == "1d":
            start = end - timedelta(days=max(limit * 2, 10))
        else:
            start = end - timedelta(hours=max(limit * 2, 48))

        query = urlencode(
            {
                "interval": interval,
                "includePrePost": "false",
                "events": "div,splits",
                "period1": int(start.timestamp()),
                "period2": int(end.timestamp()),
            }
        )
        timeout = float(self.config.get("timeout_seconds", 12))
        provider_symbol = self._provider_symbol(symbol)
        last_error: Exception | None = None
        for endpoint in self.chart_endpoints:
            url = f"{endpoint}{provider_symbol}?{query}"
            request = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AITradingAssistant/1.0)",
                    "Accept": "application/json",
                },
            )
            try:
                with open_readonly_url(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8", errors="replace"))
            except (URLError, json.JSONDecodeError) as exc:
                last_error = exc

        raise ValueError(f"network error while fetching Yahoo Finance data for {symbol}") from last_error

    def _provider_symbol(self, symbol: str) -> str:
        symbol_map = self.config.get("symbol_map", {})
        if isinstance(symbol_map, dict) and symbol in symbol_map:
            return str(symbol_map[symbol])
        return symbol

    def _first_result(self, payload: dict[str, Any], symbol: str) -> dict[str, Any]:
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            raise ValueError(f"invalid Yahoo Finance response for {symbol}")

        error = chart.get("error")
        if error:
            description = error.get("description") if isinstance(error, dict) else str(error)
            raise ValueError(f"Yahoo Finance error for {symbol}: {description}")

        results = chart.get("result")
        if not isinstance(results, list) or not results:
            raise ValueError(f"empty Yahoo Finance response for {symbol}")
        if not isinstance(results[0], dict):
            raise ValueError(f"invalid Yahoo Finance result for {symbol}")
        return results[0]

    def _extract_candles(self, result: dict[str, Any], symbol: str, timeframe: str) -> list[AdapterCandle]:
        timestamps = result.get("timestamp")
        indicators = result.get("indicators")
        if not isinstance(timestamps, list) or not isinstance(indicators, dict):
            return []

        quote_rows = indicators.get("quote")
        if not isinstance(quote_rows, list) or not quote_rows or not isinstance(quote_rows[0], dict):
            return []

        quote_row = quote_rows[0]
        opens = quote_row.get("open", [])
        highs = quote_row.get("high", [])
        lows = quote_row.get("low", [])
        closes = quote_row.get("close", [])
        volumes = quote_row.get("volume", [])

        candles: list[AdapterCandle] = []
        for index, timestamp_value in enumerate(timestamps):
            timestamp = self._parse_epoch(timestamp_value)
            close = self._read_series_value(closes, index)
            if timestamp is None or close is None:
                continue

            open_value = self._read_series_value(opens, index)
            high_value = self._read_series_value(highs, index)
            low_value = self._read_series_value(lows, index)
            volume_value = self._read_series_value(volumes, index, default=0)
            candles.append(
                AdapterCandle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    open=float(open_value if open_value is not None else close),
                    high=float(high_value if high_value is not None else close),
                    low=float(low_value if low_value is not None else close),
                    close=float(close),
                    volume=float(volume_value or 0),
                    source=self.provider,
                    currency=(result.get("meta") or {}).get("currency"),
                )
            )
        return candles

    def _read_series_value(self, values: Any, index: int, default: float | None = None) -> float | None:
        if not isinstance(values, list) or index >= len(values):
            return default
        value = values[index]
        if value in (None, ""):
            return default
        return float(value)

    def _parse_epoch(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            return datetime.fromtimestamp(float(value), timezone.utc)
        except (TypeError, ValueError, OSError):
            return None


class CustomHttpReadOnlyMarketDataAdapter(ReadOnlyMarketDataAdapter):
    provider = "custom_http_readonly"
    capabilities = ["quotes", "custom_http_json", "credentials_ref_ready"]

    def __init__(self, config: dict[str, Any] | None = None, base_url: str | None = None):
        self.config = config or {}
        self.base_url = base_url

    def health_check(self) -> AdapterHealth:
        configured = bool(self._quote_url_template() and self.config.get("price_path"))
        return AdapterHealth(
            provider=self.provider,
            status="ok" if configured else "unconfigured",
            checked_at=datetime.now(timezone.utc),
            latency_ms=None,
            message=(
                "Custom HTTP read-only quote mapping is configured."
                if configured
                else "Custom HTTP adapter is registered but quote_url_template and price_path are not configured."
            ),
            details={
                "required_config": ["quote_url_template", "price_path"],
                "optional_config": ["bid_path", "ask_path", "as_of_path", "headers"],
                "read_only": True,
                "uses_credentials_ref_only": True,
            },
        )

    def get_quote(self, symbol: str) -> AdapterQuote:
        template = self._quote_url_template()
        price_path = self.config.get("price_path")
        if not template or not price_path:
            raise ValueError("custom_http_readonly is unconfigured")

        normalized = symbol.upper()
        url = template.format(symbol=normalized, symbol_lower=normalized.lower())
        timeout = float(self.config.get("timeout_seconds", 5))
        headers = {"User-Agent": "ai-trading-os-readonly/0.1", **self._safe_headers()}
        request = Request(url, headers=headers)

        try:
            with open_readonly_url(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except (URLError, json.JSONDecodeError) as exc:
            raise ValueError(f"custom HTTP quote fetch failed for {normalized}") from exc

        price = self._extract(payload, str(price_path))
        bid = self._extract(payload, str(self.config.get("bid_path"))) if self.config.get("bid_path") else None
        ask = self._extract(payload, str(self.config.get("ask_path"))) if self.config.get("ask_path") else None
        as_of_value = self._extract(payload, str(self.config.get("as_of_path"))) if self.config.get("as_of_path") else None

        return AdapterQuote(
            symbol=normalized,
            price=float(price),
            bid=float(bid) if bid is not None else None,
            ask=float(ask) if ask is not None else None,
            source=str(self.config.get("source", self.provider)),
            as_of=self._parse_as_of(as_of_value),
        )

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        raise ValueError("custom_http_readonly candle ingestion is not configured")

    def _quote_url_template(self) -> str | None:
        return self.config.get("quote_url_template") or self.base_url

    def _safe_headers(self) -> dict[str, str]:
        headers = self.config.get("headers", {})
        if not isinstance(headers, dict):
            return {}
        return {str(key): str(value) for key, value in headers.items()}

    def _extract(self, payload: Any, path: str) -> Any:
        current = payload
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            if isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
                continue
            raise ValueError(f"path not found in custom quote payload: {path}")
        return current

    def _parse_as_of(self, value: Any) -> datetime | None:
        if not value:
            return datetime.now(timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class PlaceholderReadOnlyAccountAdapter(ReadOnlyMarketDataAdapter):
    capabilities = ["account_sync_placeholder", "positions_placeholder", "balances_placeholder", "credentials_ref_required"]

    def __init__(
        self,
        provider: str,
        display_name: str,
        *,
        config: dict[str, Any] | None = None,
        credentials_ref: str | None = None,
        sample_payload: dict[str, Any] | None = None,
    ):
        self.provider = provider
        self.display_name = display_name
        self.config = config or {}
        self.credentials_ref = credentials_ref
        self.sample_payload = sample_payload

    def health_check(self) -> AdapterHealth:
        has_sample_payload = bool(self._sample_payload())
        status = "ok" if has_sample_payload else "unconfigured"
        return AdapterHealth(
            provider=self.provider,
            status=status,
            checked_at=datetime.now(timezone.utc),
            latency_ms=None,
            message=(
                f"{self.display_name} read-only sample snapshot is available for account sync."
                if has_sample_payload
                else f"{self.display_name} read-only adapter is registered but not configured. Provide a sample_snapshot for dry-run sync or credentials_ref later; live execution remains unavailable."
            ),
            details={
                "read_only": True,
                "requires_credentials_ref": True,
                "has_credentials_ref": bool(self.credentials_ref),
                "has_sample_snapshot": has_sample_payload,
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "secrets_in_config_allowed": False,
            },
        )

    def get_account_snapshot(self) -> ReadOnlyAccountSnapshot:
        payload = self._sample_payload()
        if not payload:
            raise ValueError(f"{self.provider} read-only adapter is not configured for account sync")

        account = self._dict_value(payload.get("account"), default={})
        balances = self._list_of_dicts(payload.get("balances"))
        positions = self._list_of_dicts(payload.get("positions"))
        orders = self._list_of_dicts(payload.get("orders") or payload.get("order_history"))
        warnings: list[str] = []

        if not account:
            warnings.append("account metadata is missing")
        if not balances:
            warnings.append("balances are missing")
        if not positions:
            warnings.append("positions are missing")

        account.setdefault("label", self.display_name)
        account.setdefault("account_type", self._account_type())
        account.setdefault("base_currency", self._base_currency(balances, positions))

        return ReadOnlyAccountSnapshot(
            provider=self.provider,
            account=account,
            balances=balances,
            positions=positions,
            orders=orders,
            as_of=self._parse_as_of(payload.get("as_of")),
            warnings=warnings,
        )

    def get_quote(self, symbol: str) -> AdapterQuote:
        raise ValueError(f"{self.provider} read-only adapter is not configured for quote import")

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        raise ValueError(f"{self.provider} read-only adapter is not configured for candle import")

    def _sample_payload(self) -> dict[str, Any] | None:
        payload = self.sample_payload or self.config.get("sample_snapshot")
        return payload if isinstance(payload, dict) and payload else None

    def _account_type(self) -> str:
        if self.provider == "cex_readonly":
            return "exchange_account"
        if self.provider == "wallet_readonly":
            return "wallet_account"
        return "broker_account"

    def _base_currency(self, balances: list[dict[str, Any]], positions: list[dict[str, Any]]) -> str:
        for row in [*balances, *positions]:
            currency = row.get("currency") or row.get("quote_currency")
            if currency:
                return str(currency).upper()
        return "USD"

    def _dict_value(self, value: Any, *, default: dict[str, Any]) -> dict[str, Any]:
        return value if isinstance(value, dict) else default.copy()

    def _list_of_dicts(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _parse_as_of(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), timezone.utc)
            except (ValueError, OSError):
                return datetime.now(timezone.utc)
        if isinstance(value, str) and value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)


class IbkrClientPortalReadOnlyAccountAdapter(ReadOnlyMarketDataAdapter):
    provider = "ibkr_readonly"
    capabilities = [
        "authenticated_account_snapshot",
        "portfolio_accounts_read",
        "positions_read",
        "cash_balances_read",
        "gateway_session_required",
        "order_routing_forbidden",
    ]

    def __init__(self, *, config: dict[str, Any] | None = None, credentials_ref: str | None = None):
        self.config = config or {}
        self.credentials_ref = credentials_ref
        self.timeout = float(self.config.get("timeout_seconds") or 8)
        host = str(self.config.get("gateway_host") or "127.0.0.1").strip()
        port = int(self.config.get("gateway_port") or 5000)
        configured_base_url = str(self.config.get("base_url") or "").strip()
        self.base_url = (configured_base_url or f"https://{host}:{port}/v1/api").rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https":
            raise ValueError("ibkr_readonly gateway must use https")
        self.gateway_host = parsed.hostname or ""
        self.local_gateway = self.gateway_host in {"127.0.0.1", "localhost", "::1"}
        if not self.local_gateway and self.config.get("allow_insecure_localhost") is True:
            raise ValueError("ibkr_readonly insecure TLS is allowed only for a loopback gateway")
        self._accounts_payload: list[dict[str, Any]] | None = None

    def health_check(self) -> AdapterHealth:
        configured = bool(self.credentials_ref and self.gateway_host)
        if configured:
            started_at = time.perf_counter()
            try:
                payload = self._get_json("/portfolio/accounts")
                if not isinstance(payload, list) or not any(isinstance(item, dict) for item in payload):
                    raise ValueError("ibkr_readonly portfolio accounts response is empty or invalid")
                self._accounts_payload = [item for item in payload if isinstance(item, dict)]
                latency_ms = round((time.perf_counter() - started_at) * 1000, 3)
            except Exception:
                return AdapterHealth(
                    provider=self.provider,
                    status="unavailable",
                    checked_at=datetime.now(timezone.utc),
                    latency_ms=round((time.perf_counter() - started_at) * 1000, 3),
                    message="IBKR Client Portal Gateway session is unavailable or rejected the read-only account probe.",
                    details={
                        "read_only": True,
                        "authenticated": False,
                        "gateway_host": self.gateway_host,
                        "local_gateway": self.local_gateway,
                        "probe_endpoint": "/portfolio/accounts",
                        "provider_error_redacted": True,
                        "http_methods_allowed": ["GET"],
                        "execution_available": False,
                        "order_routing_available": False,
                    },
                )
        else:
            latency_ms = None
        return AdapterHealth(
            provider=self.provider,
            status="ok" if configured else "unconfigured",
            checked_at=datetime.now(timezone.utc),
            latency_ms=latency_ms,
            message=(
                "IBKR Client Portal Gateway metadata and session reference are configured for read-only sync."
                if configured
                else "IBKR Client Portal Gateway requires a credentials_ref plus gateway host/port metadata."
            ),
            details={
                "read_only": True,
                "authenticated": configured,
                "gateway_host": self.gateway_host,
                "local_gateway": self.local_gateway,
                "requires_active_gateway_session": True,
                "probe_endpoint": "/portfolio/accounts",
                "has_credentials_ref": bool(self.credentials_ref),
                "http_methods_allowed": ["GET"],
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
            },
        )

    def get_account_snapshot(self) -> ReadOnlyAccountSnapshot:
        accounts_payload = self._accounts_payload if self._accounts_payload is not None else self._get_json("/portfolio/accounts")
        if not isinstance(accounts_payload, list) or not accounts_payload:
            raise ValueError("ibkr_readonly portfolio accounts response is empty or invalid")
        accounts = [item for item in accounts_payload if isinstance(item, dict)]
        requested_account_id = str(self.config.get("account_id") or "").strip()
        account_row = next(
            (
                item for item in accounts
                if str(item.get("accountId") or item.get("id") or "") == requested_account_id
            ),
            None,
        ) if requested_account_id else accounts[0]
        if account_row is None:
            raise ValueError("ibkr_readonly configured account is not available to the active gateway session")
        account_id = str(account_row.get("accountId") or account_row.get("id") or "").strip()
        if not account_id:
            raise ValueError("ibkr_readonly account id is missing")

        positions_payload: list[dict[str, Any]] = []
        max_pages = max(1, min(int(self.config.get("max_position_pages") or 20), 100))
        for page_id in range(max_pages):
            page = self._get_json(f"/portfolio/{quote(account_id, safe='')}/positions/{page_id}")
            if not isinstance(page, list):
                raise ValueError("ibkr_readonly positions response must be a list")
            rows = [item for item in page if isinstance(item, dict)]
            positions_payload.extend(rows)
            if len(rows) < 100:
                break
        else:
            raise ValueError("ibkr_readonly positions pagination exceeded configured safety limit")

        ledger_payload = self._get_json(f"/portfolio/{quote(account_id, safe='')}/ledger")
        if not isinstance(ledger_payload, dict):
            raise ValueError("ibkr_readonly ledger response must be an object")

        balances = self._map_ledger(ledger_payload)
        positions = [self._map_position(row, account_id=account_id) for row in positions_payload]
        positions = [row for row in positions if row is not None]
        base_currency = str(account_row.get("currency") or self.config.get("base_currency") or "USD").upper()
        account = {
            "account_id": account_id,
            "label": str(account_row.get("displayName") or account_row.get("accountAlias") or self.config.get("account_label") or account_id),
            "account_type": "broker_account",
            "base_currency": base_currency,
            "provider_account_status": account_row.get("accountStatus"),
            "provider_brokerage_access": bool(account_row.get("brokerageAccess", False)),
            "gateway_session_authenticated": True,
            "provider_can_trade": False,
            "provider_can_withdraw": False,
        }
        warnings: list[str] = ["orders_not_requested_readonly_scope"]
        if not balances:
            warnings.append("balances_missing_or_invalid")
        if not positions:
            warnings.append("positions_missing_or_empty")
        as_of = self._latest_timestamp(accounts, ledger_payload) or datetime.now(timezone.utc)
        return ReadOnlyAccountSnapshot(
            provider=self.provider,
            account=account,
            balances=balances,
            positions=positions,
            orders=[],
            as_of=as_of,
            warnings=warnings,
        )

    def get_quote(self, symbol: str) -> AdapterQuote:
        raise ValueError("ibkr_readonly account adapter does not expose market-data or order endpoints")

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        raise ValueError("ibkr_readonly account adapter does not expose market-data or order endpoints")

    def _get_json(self, path: str) -> Any:
        request = Request(
            f"{self.base_url}{path}",
            headers={"User-Agent": "ai-trading-os-ibkr-readonly/1.0", "Accept": "application/json"},
            method="GET",
        )
        context = None
        if self.local_gateway and self.config.get("allow_insecure_localhost", True):
            context = ssl._create_unverified_context()
        elif certifi:
            context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=self.timeout, context=context) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        if isinstance(payload, dict) and payload.get("error"):
            raise ValueError("ibkr_readonly gateway rejected a read-only request")
        return payload

    @staticmethod
    def _map_position(row: dict[str, Any], *, account_id: str) -> dict[str, Any] | None:
        symbol = str(row.get("contractDesc") or row.get("ticker") or row.get("symbol") or "").strip()
        if not symbol:
            return None
        asset_class = str(row.get("assetClass") or row.get("secType") or "stock").lower()
        asset_type = "stock" if asset_class in {"stk", "stock"} else "etf" if asset_class == "etf" else asset_class
        return {
            "symbol": symbol,
            "name": str(row.get("name") or symbol),
            "asset_type": asset_type,
            "market": str(row.get("listingExchange") or row.get("exchange") or "US"),
            "venue": str(row.get("listingExchange") or row.get("exchange") or "IBKR"),
            "currency": str(row.get("currency") or "USD").upper(),
            "quantity": row.get("position") or 0,
            "average_cost": row.get("avgCost") or 0,
            "market_price": row.get("mktPrice") or 0,
            "market_value": row.get("mktValue") or 0,
            "unrealized_pnl": row.get("unrealizedPnl") or 0,
            "realized_pnl": row.get("realizedPnl") or 0,
            "provider_contract_id": row.get("conid"),
            "provider_account_id": account_id,
        }

    @staticmethod
    def _map_ledger(payload: dict[str, Any]) -> list[dict[str, Any]]:
        balances: list[dict[str, Any]] = []
        for currency_key, value in payload.items():
            if not isinstance(value, dict):
                continue
            currency = "BASE" if str(currency_key).upper() == "BASE" else str(currency_key).upper()
            cash = value.get("cashbalance")
            if cash is None:
                cash = value.get("cashBalance")
            if cash is None:
                continue
            balances.append({
                "currency": str(value.get("currency") or currency).upper(),
                "cash_value": cash,
                "settled_cash": value.get("settledcash") or value.get("settledCash"),
                "net_liquidation_value": value.get("netliquidationvalue") or value.get("netLiquidationValue"),
                "exchange_rate": value.get("exchangerate") or value.get("exchangeRate"),
            })
        return balances

    @staticmethod
    def _latest_timestamp(accounts: list[dict[str, Any]], ledger: dict[str, Any]) -> datetime | None:
        candidates: list[float] = []
        for value in [*accounts, *[item for item in ledger.values() if isinstance(item, dict)]]:
            timestamp = value.get("timestamp") or value.get("accountStatus")
            if isinstance(timestamp, (int, float)) and timestamp > 0:
                candidates.append(float(timestamp))
        if not candidates:
            return None
        latest = max(candidates)
        if latest > 10_000_000_000:
            latest /= 1000
        return datetime.fromtimestamp(latest, timezone.utc)


class BinanceSpotReadOnlyAccountAdapter(ReadOnlyMarketDataAdapter):
    provider = "binance_spot_readonly"
    capabilities = [
        "authenticated_account_snapshot",
        "balances_read",
        "positions_from_balances",
        "credentials_ref_required",
        "withdrawals_forbidden",
        "order_routing_forbidden",
    ]

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        credentials_ref: str | None = None,
    ):
        self.config = config or {}
        self.credentials_ref = credentials_ref
        self.timeout = float(self.config.get("timeout_seconds") or 8)
        self.base_url = str(self.config.get("base_url") or "https://api.binance.com").rstrip("/")

    def health_check(self) -> AdapterHealth:
        credentials = self._credentials()
        configured = credentials is not None
        return AdapterHealth(
            provider=self.provider,
            status="ok" if configured else "unconfigured",
            checked_at=datetime.now(timezone.utc),
            latency_ms=None,
            message=(
                "Binance Spot read-only credentials are available for authenticated account sync."
                if configured
                else "Binance Spot read-only adapter requires credentials_ref=env:... containing API key and API secret JSON."
            ),
            details={
                "read_only": True,
                "authenticated": configured,
                "requires_credentials_ref": True,
                "has_credentials_ref": bool(self.credentials_ref),
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
                "supported_credentials_ref": "env:<JSON_WITH_api_key_AND_api_secret>",
            },
        )

    def get_account_snapshot(self) -> ReadOnlyAccountSnapshot:
        payload = self._signed_get_account()
        balances, positions, warnings = self._balances_and_positions(payload.get("balances"))
        account_label = str(self.config.get("account_label") or "binance-spot")
        account_uid = payload.get("uid") or payload.get("accountType") or account_label
        account = {
            "account_id": f"binance-spot:{account_uid}",
            "label": account_label,
            "account_type": "exchange_account",
            "base_currency": str(self.config.get("base_currency") or "USD").upper(),
            "provider_account_type": payload.get("accountType"),
            "provider_permissions": payload.get("permissions") or [],
            "provider_can_trade": bool(payload.get("canTrade", False)),
            "provider_can_withdraw": bool(payload.get("canWithdraw", False)),
        }
        if account["provider_can_trade"]:
            raise ValueError("binance read-only verification failed: provider reports trading enabled")
        if account["provider_can_withdraw"]:
            raise ValueError("binance read-only verification failed: provider reports withdrawals enabled")

        update_time = payload.get("updateTime")
        as_of = datetime.now(timezone.utc)
        if isinstance(update_time, (int, float)) and update_time > 0:
            as_of = datetime.fromtimestamp(float(update_time) / 1000, timezone.utc)

        return ReadOnlyAccountSnapshot(
            provider=self.provider,
            account=account,
            balances=balances,
            positions=positions,
            orders=[],
            as_of=as_of,
            warnings=warnings,
        )

    def get_quote(self, symbol: str) -> AdapterQuote:
        raise ValueError("binance_spot_readonly only exposes authenticated account snapshots in this adapter")

    def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[AdapterCandle]:
        raise ValueError("binance_spot_readonly only exposes authenticated account snapshots in this adapter")

    def _signed_get_account(self) -> dict[str, Any]:
        credentials = self._credentials()
        if credentials is None:
            raise ValueError("binance_spot_readonly credentials are not configured")
        timestamp_ms = int(time.time() * 1000)
        params = {
            "timestamp": str(timestamp_ms),
            "recvWindow": str(int(self.config.get("recv_window_ms") or 5000)),
            "omitZeroBalances": "true" if self.config.get("omit_zero_balances", True) else "false",
        }
        query = urlencode(params)
        signature = hmac.new(credentials["api_secret"].encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        url = f"{self.base_url}/api/v3/account?{query}&signature={signature}"
        request = Request(url, headers={"X-MBX-APIKEY": credentials["api_key"], "User-Agent": "ai-trading-os-readonly"}, method="GET")
        with open_readonly_url(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("binance_spot_readonly account response must be an object")
        return payload

    def _credentials(self) -> dict[str, str] | None:
        ref = (self.credentials_ref or "").strip()
        if not ref.startswith("env:"):
            return None
        env_name = ref.removeprefix("env:").strip()
        if not env_name:
            return None
        raw = os.environ.get(env_name)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        api_key = str(payload.get("api_key") or payload.get("key") or "").strip()
        api_secret = str(payload.get("api_secret") or payload.get("secret") or "").strip()
        if not api_key or not api_secret:
            return None
        return {"api_key": api_key, "api_secret": api_secret}

    def _balances_and_positions(self, value: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        if not isinstance(value, list):
            return [], [], ["balances_missing_or_invalid"]
        balances: list[dict[str, Any]] = []
        positions: list[dict[str, Any]] = []
        warnings: list[str] = []
        for row in value:
            if not isinstance(row, dict):
                continue
            asset = str(row.get("asset") or "").strip().upper()
            if not asset:
                continue
            free = self._float(row.get("free"))
            locked = self._float(row.get("locked"))
            total = free + locked
            if total == 0:
                continue
            balances.append(
                {
                    "currency": asset,
                    "free": free,
                    "locked": locked,
                    "cash_value": total if asset in {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD"} else 0,
                    "provider_asset": asset,
                }
            )
            positions.append(
                {
                    "symbol": asset,
                    "name": asset,
                    "asset_type": "crypto",
                    "market": "CRYPTO",
                    "venue": "binance_spot",
                    "currency": str(self.config.get("base_currency") or "USD").upper(),
                    "quantity": total,
                    "market_price": 1 if asset in {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD"} else 0,
                    "market_value": total if asset in {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD"} else 0,
                    "free": free,
                    "locked": locked,
                }
            )
            if asset not in {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD"}:
                warnings.append(f"market_value_unpriced:{asset}")
        return balances, positions, warnings

    def _float(self, value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
