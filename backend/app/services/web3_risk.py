from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from typing import Callable
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.evm_rpc_readonly import EvmRpcError
from app.adapters.evm_rpc_readonly import EvmRpcReadOnlyAdapter
from app.models import AuditLog
from app.models import ExchangeExposure
from app.models import OnchainRiskAlert
from app.models import ProtocolPosition
from app.models import StablecoinExposure
from app.models import TokenAllowance
from app.models import TokenBalance
from app.models import Wallet
from app.models import WalletTransfer
from app.models import DataSnapshot
from app.models import DataQualityReport
from app.services.data_catalog import DataCatalogService
from app.models.core import utc_now
from app.schemas import WalletCreate
from app.schemas import Web3RiskScanRequest


STABLECOIN_SYMBOLS = {"USDC", "USDT", "DAI", "FDUSD", "PYUSD", "TUSD", "USDE", "USDS"}


class Web3ReadOnlySafetyError(ValueError):
    pass


# A price provider maps a token symbol to a USD spot price, or None when no
# trustworthy price is available. None is honest: valuation stays 0 rather than
# inventing a number.
PriceProvider = Callable[[str], float | None]


def default_onchain_price_provider(symbol: str) -> float | None:
    """Fail-closed USD price for an on-chain token via the public Yahoo Finance
    read-only quote adapter (symbol-USD pair, no credentials). Stablecoins are
    pinned to 1.0. Any lookup failure returns None so nothing is invented."""
    ticker = str(symbol or "").strip().upper()
    if not ticker:
        return None
    if ticker in STABLECOIN_SYMBOLS:
        return 1.0
    try:
        from app.adapters.market_data_readonly import YahooFinancePublicMarketDataAdapter

        quote = YahooFinancePublicMarketDataAdapter().get_quote(f"{ticker}-USD")
        price = float(quote.price)
        return price if price > 0 else None
    except Exception:
        return None


@dataclass(frozen=True)
class Web3RiskScanResult:
    wallet_id: str | None
    alerts: list[OnchainRiskAlert]
    balances: list[TokenBalance]
    allowances: list[TokenAllowance]
    transfers: list[WalletTransfer]
    protocol_positions: list[ProtocolPosition]
    exchange_exposures: list[ExchangeExposure]
    stablecoin_exposures: list[StablecoinExposure]


class Web3RiskReadOnlyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register_wallet(self, payload: WalletCreate) -> Wallet:
        self._validate_public_address(payload.address)
        existing = self.db.scalar(
            select(Wallet).where(
                Wallet.user_id == payload.user_id,
                Wallet.address == payload.address,
                Wallet.chain == payload.chain,
            )
        )
        if existing:
            return existing

        wallet = Wallet(**payload.model_dump(), is_active=True)
        self.db.add(wallet)
        self.db.flush()
        self._write_audit_log(
            action="web3.wallet.registered",
            entity_type="Wallet",
            entity_id=wallet.id,
            payload_json={"user_id": wallet.user_id, "address": wallet.address, "chain": wallet.chain},
        )
        self.db.commit()
        self.db.refresh(wallet)
        return wallet

    def rpc_refresh_wallet(
        self,
        wallet: Wallet,
        *,
        rpc_url: str | None = None,
        erc20_tokens: list[dict[str, Any]] | None = None,
        allowances: list[dict[str, Any]] | None = None,
        protocol_positions: list[dict[str, Any]] | None = None,
        adapter: EvmRpcReadOnlyAdapter | None = None,
        price_provider: PriceProvider | None = None,
    ) -> list[TokenBalance]:
        """Real on-chain read: native + optional ERC-20 balances via public
        JSON-RPC. Read-only by construction — the adapter has no signing or
        transaction capability. When a price_provider is supplied, each balance
        is valued in USD from that read-only source; symbols it cannot price
        keep usd_price=0 so nothing is invented."""

        def _value(symbol: str, amount: float) -> tuple[float, float, bool]:
            if price_provider is None:
                return 0.0, 0.0, False
            price = price_provider(symbol)
            if price is None or price <= 0:
                return 0.0, 0.0, False
            return float(price), float(amount) * float(price), True
        # Resolve the read-only node for the wallet's chain (Base/Arbitrum/etc.)
        # from the registry unless the caller supplied an adapter or explicit
        # rpc_url. Then fail-closed verify the node serves the expected chain so
        # we never read a Base wallet against a mainnet node.
        if adapter is not None:
            rpc = adapter
        elif rpc_url:
            parsed_rpc = urlparse(str(rpc_url))
            if parsed_rpc.username or parsed_rpc.password or parsed_rpc.query or parsed_rpc.fragment:
                raise Web3ReadOnlySafetyError("custom rpc_url must be a credential-free public HTTPS endpoint")
            try:
                rpc = EvmRpcReadOnlyAdapter.for_chain(wallet.chain, rpc_url=rpc_url)
            except EvmRpcError as exc:
                raise Web3ReadOnlySafetyError(f"unsupported chain for custom on-chain read: {exc}") from exc
        else:
            try:
                rpc = EvmRpcReadOnlyAdapter.for_chain(wallet.chain)
            except EvmRpcError as exc:
                raise Web3ReadOnlySafetyError(f"unsupported chain for on-chain read: {exc}") from exc
        try:
            rpc.verify_chain()
        except EvmRpcError as exc:
            raise Web3ReadOnlySafetyError(f"chain verification failed: {exc}") from exc
        balances: list[TokenBalance] = []
        priced_count = 0
        native_balance = rpc.get_native_balance(wallet.address)
        native_symbol = rpc.native_symbol
        native_price, native_value, native_priced = _value(native_symbol, native_balance)
        priced_count += 1 if native_priced else 0
        balances.append(
            TokenBalance(
                wallet_id=wallet.id,
                chain=wallet.chain,
                token=native_symbol,
                symbol=native_symbol,
                token_address=None,
                balance=native_balance,
                usd_price=native_price,
                usd_value=native_value,
                source="evm_rpc_readonly",
                as_of=utc_now(),
            )
        )
        for token in erc20_tokens or []:
            token_address = str(token.get("address") or "")
            symbol = str(token.get("symbol") or "TOKEN").upper()[:32]
            decimals = int(token.get("decimals") or 18)
            try:
                amount = rpc.get_erc20_balance(token_address, wallet.address, decimals=decimals)
            except EvmRpcError as exc:
                raise Web3ReadOnlySafetyError(f"erc20 read failed for {symbol}: {exc}") from exc
            token_price, token_value, token_priced = _value(symbol, amount)
            priced_count += 1 if token_priced else 0
            balances.append(
                TokenBalance(
                    wallet_id=wallet.id,
                    chain=wallet.chain,
                    token=symbol,
                    symbol=symbol,
                    token_address=token_address,
                    balance=amount,
                    usd_price=token_price,
                    usd_value=token_value,
                    source="evm_rpc_readonly",
                    as_of=utc_now(),
                )
            )
        allowance_rows: list[TokenAllowance] = []
        protocol_rows: list[ProtocolPosition] = []
        alerts_created = 0
        for spec in allowances or []:
            token_address = str(spec.get("token_address") or spec.get("address") or "")
            spender = str(spec.get("spender") or "")
            symbol = str(spec.get("symbol") or "TOKEN").upper()[:32]
            decimals = int(spec.get("decimals") or 18)
            try:
                amount, is_unlimited = rpc.get_erc20_allowance(token_address, wallet.address, spender, decimals=decimals)
            except EvmRpcError as exc:
                raise Web3ReadOnlySafetyError(f"allowance read failed for {symbol}: {exc}") from exc
            allowance_price, allowance_value, allowance_priced = _value(symbol, amount)
            priced_count += 1 if allowance_priced else 0
            allowance_rows.append(
                TokenAllowance(
                    wallet_id=wallet.id,
                    chain=wallet.chain,
                    token=symbol,
                    symbol=symbol,
                    token_address=token_address,
                    spender=spender,
                    amount=min(amount, 1e18),
                    usd_value=min(allowance_value, 1e18),
                    risk_level="high" if is_unlimited or allowance_value >= 10_000 else "low",
                    source="evm_rpc_readonly",
                    as_of=utc_now(),
                )
            )
            if is_unlimited:
                self.db.add(
                    self._alert(
                        user_id=wallet.user_id,
                        wallet_id=wallet.id,
                        alert_type="UNLIMITED_TOKEN_ALLOWANCE",
                        severity="high",
                        description=f"On-chain read found an unlimited {symbol} approval to {spender}. Review and revoke it from your own wallet if unexpected.",
                        evidence={"token_address": token_address, "spender": spender, "source": "evm_rpc_readonly", "read_only": True},
                    )
                )
                alerts_created += 1
        for spec in protocol_positions or []:
            protocol_name = str(spec.get("protocol_name") or "").strip()[:128]
            position_type = str(spec.get("position_type") or "exposure").strip()[:64]
            token_address = str(spec.get("token_address") or spec.get("address") or "")
            symbol = str(spec.get("symbol") or "TOKEN").upper()[:32]
            decimals = int(spec.get("decimals") or 18)
            if not protocol_name:
                raise Web3ReadOnlySafetyError("protocol_name is required for protocol exposure")
            try:
                amount = rpc.get_erc20_balance(token_address, wallet.address, decimals=decimals)
            except EvmRpcError as exc:
                raise Web3ReadOnlySafetyError(f"protocol exposure read failed for {protocol_name}/{symbol}: {exc}") from exc
            token_price, usd_value, token_priced = _value(symbol, amount)
            priced_count += 1 if token_priced else 0
            protocol_rows.append(
                ProtocolPosition(
                    wallet_id=wallet.id,
                    chain=wallet.chain,
                    protocol_name=protocol_name,
                    position_type=position_type,
                    asset_symbol=symbol,
                    usd_value=usd_value,
                    risk_json={
                        "token_address": token_address,
                        "token_balance": amount,
                        "usd_price": token_price,
                        "priced": token_priced,
                        "source": "evm_rpc_readonly",
                        "read_only": True,
                    },
                    as_of=utc_now(),
                )
            )
        self.db.add_all([*balances, *allowance_rows, *protocol_rows])
        self.db.flush()
        as_of = max((item.as_of for item in balances), default=utc_now())
        snapshot = DataSnapshot(
            snapshot_type="evm_wallet_readonly",
            as_of=as_of,
            data_json={
                "wallet_id": wallet.id,
                "public_address": wallet.address,
                "chain": wallet.chain,
                "chain_id": rpc.expected_chain_id,
                "balances": [
                    {"symbol": item.symbol, "token_address": item.token_address, "balance": float(item.balance), "usd_price": float(item.usd_price), "usd_value": float(item.usd_value)}
                    for item in balances
                ],
                "allowances": [
                    {"symbol": item.symbol, "token_address": item.token_address, "spender": item.spender, "amount": float(item.amount), "usd_value": float(item.usd_value), "risk_level": item.risk_level}
                    for item in allowance_rows
                ],
                "protocol_exposures": [
                    {"protocol_name": item.protocol_name, "position_type": item.position_type, "asset_symbol": item.asset_symbol, "usd_value": float(item.usd_value), "risk": item.risk_json}
                    for item in protocol_rows
                ],
            },
            metadata_json={
                "provider": "evm_rpc_readonly",
                "read_only": True,
                "signing_available": False,
                "transaction_building": False,
                "execution_available": False,
            },
        )
        self.db.add(snapshot)
        self.db.flush()
        expected_prices = len(balances) + len(allowance_rows) + len(protocol_rows)
        quality = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source="evm_rpc_readonly",
            metric_type="evm_wallet_read_completeness",
            score=1.0 if expected_prices == 0 or priced_count >= expected_prices else priced_count / expected_prices,
            details_json={
                "balances_read": len(balances),
                "allowances_read": len(allowance_rows),
                "protocol_exposures_read": len(protocol_rows),
                "priced_records": priced_count,
                "expected_priced_records": expected_prices,
                "unpriced_values_are_zero": True,
            },
        )
        self.db.add(quality)
        self.db.flush()
        catalog_entry = DataCatalogService(self.db).create_entry(
            dataset_type="evm_wallet_readonly",
            source="evm_rpc_readonly",
            source_ref=f"wallet:{wallet.id}:{wallet.chain}",
            row_count=len(balances) + len(allowance_rows) + len(protocol_rows),
            snapshot=snapshot,
            quality_report=quality,
            lineage_json={
                "wallet_id": wallet.id,
                "chain": wallet.chain,
                "chain_id": rpc.expected_chain_id,
                "data_origin": "authenticated_public_chain",
            },
            contract_json={
                "execution_available": False,
                "signing_available": False,
                "transaction_building": False,
                "rpc_method_allowlist": sorted(["eth_chainId", "eth_getBalance", "eth_call"]),
            },
        )
        self._write_audit_log(
            action="web3.wallet.rpc_refreshed",
            entity_type="Wallet",
            entity_id=wallet.id,
            payload_json={
                "chain": wallet.chain,
                "rpc_endpoint_host": urlparse(rpc.rpc_url).hostname,
                "balances_read": len(balances),
                "balances_priced": priced_count,
                "price_source": "yfinance_public" if price_provider is not None else None,
                "allowances_read": len(allowance_rows),
                "protocol_exposures_read": len(protocol_rows),
                "snapshot_id": snapshot.id,
                "quality_report_id": quality.id,
                "catalog_entry_id": catalog_entry.id,
                "alerts_created": alerts_created,
                "read_only": True,
                "signing_available": False,
            },
        )
        self.db.commit()
        for balance in balances:
            self.db.refresh(balance)
        return balances

    def refresh_wallet(self, wallet: Wallet) -> Web3RiskScanResult:
        mock_scan = Web3RiskScanRequest(
            user_id=wallet.user_id,
            wallet_id=wallet.id,
            balances=[
                {
                    "token": wallet.chain.upper(),
                    "symbol": "ETH" if wallet.chain.lower() in {"ethereum", "base", "arbitrum"} else "NATIVE",
                    "balance": 1.25,
                    "usd_price": 3000,
                    "usd_value": 3750,
                },
                {
                    "token": "USD Coin",
                    "symbol": "USDC",
                    "balance": 2500,
                    "usd_price": 1,
                    "usd_value": 2500,
                    "reference_price": 1,
                },
            ],
            allowances=[],
            transfers=[],
        )
        return self.scan(mock_scan)

    def scan(self, payload: Web3RiskScanRequest) -> Web3RiskScanResult:
        wallet = self._wallet(payload.wallet_id)
        user_id = payload.user_id or (wallet.user_id if wallet else None)
        if not user_id:
            raise Web3ReadOnlySafetyError("user_id is required when wallet_id is not provided")

        balances = self._import_balances(payload, wallet)
        allowances = self._import_allowances(payload, wallet)
        transfers = self._import_transfers(payload, wallet)
        protocol_positions = self._import_protocol_positions(payload, wallet)
        exchange_exposures = self._import_exchange_exposures(payload, user_id)
        stablecoin_exposures = self._calculate_stablecoin_exposures(payload, user_id, wallet, balances)
        alerts = self._evaluate_risks(
            payload=payload,
            user_id=user_id,
            wallet=wallet,
            allowances=allowances,
            transfers=transfers,
            protocol_positions=protocol_positions,
            exchange_exposures=exchange_exposures,
            stablecoin_exposures=stablecoin_exposures,
        )

        self._write_audit_log(
            action="web3.risk_scan.completed",
            entity_type="Wallet" if wallet else "Web3RiskScan",
            entity_id=wallet.id if wallet else user_id,
            payload_json={
                "user_id": user_id,
                "wallet_id": wallet.id if wallet else None,
                "alerts_created": len(alerts),
                "read_only": True,
                "transaction_building": False,
                "execution_performed": False,
            },
        )
        self.db.commit()
        for record in [*balances, *allowances, *transfers, *protocol_positions, *exchange_exposures, *stablecoin_exposures, *alerts]:
            self.db.refresh(record)
        return Web3RiskScanResult(
            wallet_id=wallet.id if wallet else None,
            alerts=alerts,
            balances=balances,
            allowances=allowances,
            transfers=transfers,
            protocol_positions=protocol_positions,
            exchange_exposures=exchange_exposures,
            stablecoin_exposures=stablecoin_exposures,
        )

    def list_wallets(self, user_id: str | None = None, limit: int = 100) -> list[Wallet]:
        query = select(Wallet).order_by(Wallet.created_at.desc(), Wallet.id).limit(limit)
        if user_id:
            query = select(Wallet).where(Wallet.user_id == user_id).order_by(Wallet.created_at.desc(), Wallet.id).limit(limit)
        return list(self.db.scalars(query).all())

    def deactivate_wallet(self, wallet: Wallet, user_id: str) -> None:
        if wallet.user_id != user_id:
            raise Web3ReadOnlySafetyError("wallet does not belong to user")
        wallet.is_active = False
        self._write_audit_log(
            action="web3.wallet.deactivated",
            entity_type="Wallet",
            entity_id=wallet.id,
            payload_json={"user_id": user_id, "address": wallet.address, "chain": wallet.chain},
        )
        self.db.commit()

    def resolve_alert(self, alert: OnchainRiskAlert, resolved: bool) -> OnchainRiskAlert:
        alert.resolved = resolved
        alert.resolved_at = utc_now() if resolved else None
        self._write_audit_log(
            action="web3.risk_alert.resolved" if resolved else "web3.risk_alert.reopened",
            entity_type="OnchainRiskAlert",
            entity_id=alert.id,
            payload_json={"resolved": resolved},
        )
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def _wallet(self, wallet_id: str | None) -> Wallet | None:
        if not wallet_id:
            return None
        wallet = self.db.get(Wallet, wallet_id)
        if not wallet:
            raise Web3ReadOnlySafetyError("wallet not found")
        return wallet

    def _import_balances(self, payload: Web3RiskScanRequest, wallet: Wallet | None) -> list[TokenBalance]:
        if not wallet:
            return []
        balances = [
            TokenBalance(
                wallet_id=wallet.id,
                chain=wallet.chain,
                token=item.token,
                symbol=item.symbol.upper(),
                token_address=item.token_address,
                balance=item.balance,
                usd_price=item.usd_price,
                usd_value=item.usd_value,
                source="risk_scan_read_only",
            )
            for item in payload.balances
        ]
        self.db.add_all(balances)
        self.db.flush()
        return balances

    def _import_allowances(self, payload: Web3RiskScanRequest, wallet: Wallet | None) -> list[TokenAllowance]:
        if not wallet:
            return []
        allowances = [
            TokenAllowance(
                wallet_id=wallet.id,
                chain=wallet.chain,
                token=item.token,
                symbol=item.symbol.upper(),
                token_address=item.token_address,
                spender=item.spender,
                amount=item.amount,
                usd_value=item.usd_value,
                risk_level="high" if item.usd_value >= payload.max_allowance_usd else "low",
                source="risk_scan_read_only",
            )
            for item in payload.allowances
        ]
        self.db.add_all(allowances)
        self.db.flush()
        return allowances

    def _import_transfers(self, payload: Web3RiskScanRequest, wallet: Wallet | None) -> list[WalletTransfer]:
        if not wallet:
            return []
        transfers = [
            WalletTransfer(
                wallet_id=wallet.id,
                chain=wallet.chain,
                tx_hash=item.tx_hash,
                from_address=item.from_address,
                to_address=item.to_address,
                token=item.token,
                symbol=item.symbol.upper(),
                amount=item.amount,
                usd_value=item.usd_value,
                direction=item.direction,
                is_known_contract=item.is_known_contract,
                timestamp=item.timestamp or utc_now(),
            )
            for item in payload.transfers
        ]
        self.db.add_all(transfers)
        self.db.flush()
        return transfers

    def _import_protocol_positions(self, payload: Web3RiskScanRequest, wallet: Wallet | None) -> list[ProtocolPosition]:
        if not wallet:
            return []
        positions = [
            ProtocolPosition(
                wallet_id=wallet.id,
                chain=wallet.chain,
                protocol_name=item.protocol_name,
                position_type=item.position_type,
                asset_symbol=item.asset_symbol.upper(),
                usd_value=item.usd_value,
                risk_json=item.risk_json,
            )
            for item in payload.protocol_positions
        ]
        self.db.add_all(positions)
        self.db.flush()
        return positions

    def _import_exchange_exposures(self, payload: Web3RiskScanRequest, user_id: str) -> list[ExchangeExposure]:
        exposures = [
            ExchangeExposure(
                user_id=user_id,
                exchange_name=item.exchange_name,
                asset_symbol=item.asset_symbol.upper(),
                usd_value=item.usd_value,
                exposure_pct=item.exposure_pct,
                source="risk_scan_read_only",
            )
            for item in payload.exchange_exposures
        ]
        self.db.add_all(exposures)
        self.db.flush()
        return exposures

    def _calculate_stablecoin_exposures(
        self,
        payload: Web3RiskScanRequest,
        user_id: str,
        wallet: Wallet | None,
        balances: list[TokenBalance],
    ) -> list[StablecoinExposure]:
        reference_prices = {item.symbol.upper(): item.reference_price for item in payload.balances if item.reference_price is not None}
        exposures = []
        for balance in balances:
            if balance.symbol.upper() not in STABLECOIN_SYMBOLS:
                continue
            reference_price = float(reference_prices.get(balance.symbol.upper()) or balance.usd_price or 1)
            exposures.append(
                StablecoinExposure(
                    user_id=user_id,
                    wallet_id=wallet.id if wallet else None,
                    chain=wallet.chain if wallet else balance.chain,
                    symbol=balance.symbol.upper(),
                    issuer=stablecoin_issuer(balance.symbol),
                    amount=balance.balance,
                    usd_value=balance.usd_value,
                    reference_price=reference_price,
                    depeg_risk_score=abs(reference_price - 1),
                )
            )
        self.db.add_all(exposures)
        self.db.flush()
        return exposures

    def _evaluate_risks(
        self,
        *,
        payload: Web3RiskScanRequest,
        user_id: str,
        wallet: Wallet | None,
        allowances: list[TokenAllowance],
        transfers: list[WalletTransfer],
        protocol_positions: list[ProtocolPosition],
        exchange_exposures: list[ExchangeExposure],
        stablecoin_exposures: list[StablecoinExposure],
    ) -> list[OnchainRiskAlert]:
        alerts: list[OnchainRiskAlert] = []
        for exposure in exchange_exposures:
            if self._to_float(exposure.exposure_pct) > payload.max_exchange_exposure_pct:
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=None,
                        alert_type="SINGLE_EXCHANGE_EXPOSURE_TOO_HIGH",
                        severity="high",
                        description=f"{exposure.exchange_name} exposure is above configured limit.",
                        evidence={"exchange_name": exposure.exchange_name, "exposure_pct": self._to_float(exposure.exposure_pct)},
                    )
                )
        for exposure in stablecoin_exposures:
            if self._to_float(exposure.depeg_risk_score) > payload.stablecoin_depeg_threshold:
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=wallet.id if wallet else exposure.wallet_id,
                        alert_type="STABLECOIN_DEPEG_RISK",
                        severity="high",
                        description=f"{exposure.symbol} reference price deviates from $1 peg.",
                        evidence={"symbol": exposure.symbol, "reference_price": self._to_float(exposure.reference_price)},
                    )
                )
        for allowance in allowances:
            if self._to_float(allowance.usd_value) >= payload.max_allowance_usd:
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=allowance.wallet_id,
                        alert_type="EXCESSIVE_TOKEN_ALLOWANCE",
                        severity="high",
                        description=f"{allowance.symbol} allowance to spender is above configured limit.",
                        evidence={"spender": allowance.spender, "usd_value": self._to_float(allowance.usd_value)},
                    )
                )
        for transfer in transfers:
            if not transfer.is_known_contract:
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=transfer.wallet_id,
                        alert_type="UNKNOWN_CONTRACT_INTERACTION",
                        severity="medium",
                        description="Wallet interacted with an unknown contract address.",
                        evidence={"tx_hash": transfer.tx_hash, "to_address": transfer.to_address},
                    )
                )
            if transfer.direction == "outgoing" and self._to_float(transfer.usd_value) >= payload.large_transfer_usd:
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=transfer.wallet_id,
                        alert_type="LARGE_OUTGOING_TRANSFER",
                        severity="high",
                        description="Large outgoing transfer detected.",
                        evidence={"tx_hash": transfer.tx_hash, "usd_value": self._to_float(transfer.usd_value)},
                    )
                )
        for position in protocol_positions:
            risk_json = position.risk_json or {}
            if self._to_float(risk_json.get("tvl_drop_pct", 0)) >= 0.3:
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=position.wallet_id,
                        alert_type="PROTOCOL_TVL_DROP_PLACEHOLDER",
                        severity="medium",
                        description=f"{position.protocol_name} TVL drop placeholder risk detected.",
                        evidence=risk_json,
                    )
                )
            if risk_json.get("liquidity_pool_risk"):
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=position.wallet_id,
                        alert_type="LIQUIDITY_POOL_RISK_PLACEHOLDER",
                        severity="medium",
                        description=f"{position.protocol_name} liquidity pool risk placeholder detected.",
                        evidence=risk_json,
                    )
                )
            if risk_json.get("bridge_exposure"):
                alerts.append(
                    self._alert(
                        user_id=user_id,
                        wallet_id=position.wallet_id,
                        alert_type="BRIDGE_EXPOSURE_PLACEHOLDER",
                        severity="medium",
                        description=f"{position.protocol_name} bridge exposure placeholder detected.",
                        evidence=risk_json,
                    )
                )
        self.db.add_all(alerts)
        self.db.flush()
        return alerts

    def _alert(
        self,
        *,
        user_id: str,
        wallet_id: str | None,
        alert_type: str,
        severity: str,
        description: str,
        evidence: dict[str, Any],
    ) -> OnchainRiskAlert:
        return OnchainRiskAlert(
            user_id=user_id,
            wallet_id=wallet_id,
            alert_type=alert_type,
            severity=severity,
            description=description,
            evidence_json=evidence,
            resolved=False,
        )

    def _validate_public_address(self, address: str) -> None:
        normalized = address.strip().lower()
        if any(forbidden in normalized for forbidden in ("seed ", "mnemonic", "private", "xprv")):
            raise Web3ReadOnlySafetyError("only public wallet addresses are allowed")
        if not (normalized.startswith("0x") and len(normalized) == 42):
            raise Web3ReadOnlySafetyError("wallet address must be an EVM public address")

    def _write_audit_log(self, *, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="web3-risk-read-only-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )

    def _to_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        return float(value)


def stablecoin_issuer(symbol: str) -> str | None:
    return {
        "USDC": "Circle",
        "USDT": "Tether",
        "DAI": "MakerDAO/Sky",
        "FDUSD": "First Digital",
        "PYUSD": "PayPal",
        "TUSD": "Techteryx",
        "USDE": "Ethena",
        "USDS": "Sky",
    }.get(symbol.upper())
