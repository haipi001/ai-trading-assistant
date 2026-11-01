from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import OnchainRiskAlert
from app.models import ExchangeExposure
from app.models import StablecoinExposure
from app.models import TokenAllowance
from app.models import TokenBalance
from app.models import Wallet
from app.models import WalletTransfer
from app.models import ProtocolPosition
from app.schemas import OnchainRiskAlertRead
from app.schemas import OnchainRiskAlertResolveRequest
from app.schemas import TokenAllowanceRead
from app.schemas import TokenBalanceRead
from app.schemas import WalletCreate
from app.schemas import WalletRead
from app.schemas import WalletTransferRead
from app.schemas import ProtocolPositionRead
from app.schemas import Web3RiskScanRequest
from app.schemas import Web3RiskScanResponse
from app.schemas import Web3WalletDetailRead
from app.adapters.evm_rpc_readonly import CHAIN_REGISTRY
from app.adapters.evm_rpc_readonly import EvmRpcError
from app.services.web3_risk import default_onchain_price_provider
from app.services.web3_risk import Web3ReadOnlySafetyError
from app.services.web3_risk import Web3RiskReadOnlyService

router = APIRouter(prefix="/web3", tags=["web3-risk"])


@router.get("/multi-chain-summary")
def get_multi_chain_summary(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    wallets = list(db.scalars(select(Wallet).where(Wallet.user_id == user_id, Wallet.is_active.is_(True))).all())
    wallet_ids = [wallet.id for wallet in wallets]
    balances = list(db.scalars(select(TokenBalance).where(TokenBalance.wallet_id.in_(wallet_ids))).all()) if wallet_ids else []
    allowances = list(db.scalars(select(TokenAllowance).where(TokenAllowance.wallet_id.in_(wallet_ids))).all()) if wallet_ids else []
    protocols = list(db.scalars(select(ProtocolPosition).where(ProtocolPosition.wallet_id.in_(wallet_ids))).all()) if wallet_ids else []
    chains: dict[str, dict] = {}
    for wallet in wallets:
        chains.setdefault(wallet.chain, {"chain": wallet.chain, "wallets": 0, "balance_usd": 0.0, "allowances": 0, "high_risk_allowances": 0, "protocol_exposure_usd": 0.0, "protocols": []})["wallets"] += 1
    for item in balances:
        chains.setdefault(item.chain, {"chain": item.chain, "wallets": 0, "balance_usd": 0.0, "allowances": 0, "high_risk_allowances": 0, "protocol_exposure_usd": 0.0, "protocols": []})["balance_usd"] += float(item.usd_value or 0)
    for item in allowances:
        bucket = chains.setdefault(item.chain, {"chain": item.chain, "wallets": 0, "balance_usd": 0.0, "allowances": 0, "high_risk_allowances": 0, "protocol_exposure_usd": 0.0, "protocols": []})
        bucket["allowances"] += 1
        bucket["high_risk_allowances"] += 1 if item.risk_level == "high" else 0
    for item in protocols:
        bucket = chains.setdefault(item.chain, {"chain": item.chain, "wallets": 0, "balance_usd": 0.0, "allowances": 0, "high_risk_allowances": 0, "protocol_exposure_usd": 0.0, "protocols": []})
        bucket["protocol_exposure_usd"] += float(item.usd_value or 0)
        if item.protocol_name not in bucket["protocols"]:
            bucket["protocols"].append(item.protocol_name)
    return {
        "user_id": user_id,
        "chains": [chains[key] for key in sorted(chains)],
        "total_balance_usd": sum(float(item.usd_value or 0) for item in balances),
        "total_protocol_exposure_usd": sum(float(item.usd_value or 0) for item in protocols),
        "read_only": True,
        "signing_available": False,
        "transaction_building": False,
        "execution_available": False,
    }


@router.get("/supported-chains")
def list_supported_chains() -> list[dict]:
    """Read-only EVM chains that on-chain refresh can query, each with its
    default public node. No signing or write capability on any of them."""
    return [
        {
            "chain_id": chain_id,
            "name": spec["name"],
            "native_symbol": spec["native_symbol"],
            "rpc_url": spec["rpc_url"],
            "read_only": True,
            "signing_available": False,
        }
        for chain_id, spec in sorted(CHAIN_REGISTRY.items())
    ]


@router.get("/risk-summary")
def get_web3_risk_summary(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    wallets = list(db.scalars(select(Wallet).where(Wallet.user_id == user_id, Wallet.is_active.is_(True))).all())
    wallet_ids = [wallet.id for wallet in wallets]
    exchanges = list(db.scalars(
        select(ExchangeExposure)
        .where(ExchangeExposure.user_id == user_id)
        .order_by(ExchangeExposure.usd_value.desc(), ExchangeExposure.id)
    ).all())
    stablecoins = list(db.scalars(
        select(StablecoinExposure)
        .where(StablecoinExposure.user_id == user_id)
        .order_by(StablecoinExposure.usd_value.desc(), StablecoinExposure.id)
    ).all())
    allowances = list(db.scalars(
        select(TokenAllowance)
        .where(TokenAllowance.wallet_id.in_(wallet_ids))
        .order_by(TokenAllowance.usd_value.desc(), TokenAllowance.id)
    ).all()) if wallet_ids else []
    total_exposure = sum(float(item.usd_value or 0) for item in exchanges) + sum(float(item.usd_value or 0) for item in stablecoins)
    return {
        "exchange": [
            {
                "name": item.exchange_name,
                "symbol": item.asset_symbol,
                "value": float(item.usd_value or 0),
                "allocationPct": normalized_exposure_pct(float(item.exposure_pct or 0)),
            }
            for item in exchanges
        ],
        "stablecoin": [
            {
                "symbol": item.symbol,
                "value": float(item.usd_value or 0),
                "allocationPct": (float(item.usd_value or 0) / total_exposure * 100) if total_exposure else 0,
                "depegRiskScore": float(item.depeg_risk_score or 0),
            }
            for item in stablecoins
        ],
        "allowances": [
            {
                "protocol": item.spender,
                "symbol": item.symbol,
                "value": float(item.usd_value or 0),
                "riskLevel": normalized_risk_level(item.risk_level),
            }
            for item in allowances
        ],
        "walletCount": len(wallets),
        "source": "read_only_web3_ledger",
        "signing_available": False,
        "execution_available": False,
    }


@router.post("/wallets", response_model=WalletRead, status_code=201)
def register_wallet(payload: WalletCreate, db: Session = Depends(get_db)) -> Wallet:
    try:
        return Web3RiskReadOnlyService(db).register_wallet(payload)
    except Web3ReadOnlySafetyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/wallets", response_model=list[WalletRead])
def list_wallets(
    user_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Wallet]:
    return Web3RiskReadOnlyService(db).list_wallets(user_id=user_id, limit=limit)


@router.delete("/wallets/{wallet_id}", status_code=204)
def remove_wallet(wallet_id: str, user_id: str, db: Session = Depends(get_db)) -> None:
    wallet = get_wallet_or_404(db, wallet_id)
    try:
        Web3RiskReadOnlyService(db).deactivate_wallet(wallet, user_id)
    except Web3ReadOnlySafetyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/wallets/{wallet_id}/refresh", response_model=Web3RiskScanResponse)
def refresh_wallet(wallet_id: str, db: Session = Depends(get_db)) -> Web3RiskScanResponse:
    wallet = get_wallet_or_404(db, wallet_id)
    result = Web3RiskReadOnlyService(db).refresh_wallet(wallet)
    return scan_response(result)


@router.post("/wallets/{wallet_id}/rpc-refresh", response_model=list[TokenBalanceRead], status_code=201)
def rpc_refresh_wallet(wallet_id: str, payload: dict | None = None, db: Session = Depends(get_db)) -> list[TokenBalance]:
    """Real read-only on-chain refresh via public JSON-RPC (eth_getBalance /
    ERC-20 balanceOf). No signing capability exists on this path."""
    wallet = get_wallet_or_404(db, wallet_id)
    body = payload or {}
    # Opt-in USD valuation from a public read-only price source. Defaults on;
    # symbols that can't be priced keep usd_value=0 (nothing is invented).
    attach_prices = body.get("attach_prices", True)
    price_provider = default_onchain_price_provider if attach_prices else None
    try:
        return Web3RiskReadOnlyService(db).rpc_refresh_wallet(
            wallet,
            rpc_url=body.get("rpc_url"),
            erc20_tokens=body.get("erc20_tokens") or [],
            allowances=body.get("allowances") or [],
            protocol_positions=body.get("protocol_positions") or [],
            price_provider=price_provider,
        )
    except (Web3ReadOnlySafetyError, EvmRpcError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/wallets/{wallet_id}/balances", response_model=list[TokenBalanceRead])
def list_wallet_balances(wallet_id: str, limit: int = 100, db: Session = Depends(get_db)) -> list[TokenBalance]:
    get_wallet_or_404(db, wallet_id)
    return list(
        db.scalars(
            select(TokenBalance)
            .where(TokenBalance.wallet_id == wallet_id)
            .order_by(TokenBalance.as_of.desc(), TokenBalance.id)
            .limit(limit)
        ).all()
    )


@router.get("/wallets/{wallet_id}/allowances", response_model=list[TokenAllowanceRead])
def list_wallet_allowances(wallet_id: str, limit: int = 100, db: Session = Depends(get_db)) -> list[TokenAllowance]:
    get_wallet_or_404(db, wallet_id)
    return list(
        db.scalars(
            select(TokenAllowance)
            .where(TokenAllowance.wallet_id == wallet_id)
            .order_by(TokenAllowance.as_of.desc(), TokenAllowance.id)
            .limit(limit)
        ).all()
    )


@router.get("/wallets/{wallet_id}/protocol-positions", response_model=list[ProtocolPositionRead])
def list_wallet_protocol_positions(wallet_id: str, limit: int = 100, db: Session = Depends(get_db)) -> list[ProtocolPosition]:
    get_wallet_or_404(db, wallet_id)
    return list(
        db.scalars(
            select(ProtocolPosition)
            .where(ProtocolPosition.wallet_id == wallet_id)
            .order_by(ProtocolPosition.as_of.desc(), ProtocolPosition.id)
            .limit(limit)
        ).all()
    )


@router.get("/wallets/{wallet_id}/transfers", response_model=list[WalletTransferRead])
def list_wallet_transfers(wallet_id: str, limit: int = 100, db: Session = Depends(get_db)) -> list[WalletTransfer]:
    get_wallet_or_404(db, wallet_id)
    return list(
        db.scalars(
            select(WalletTransfer)
            .where(WalletTransfer.wallet_id == wallet_id)
            .order_by(WalletTransfer.timestamp.desc(), WalletTransfer.id)
            .limit(limit)
        ).all()
    )


@router.get("/wallets/{wallet_id}/risk-alerts", response_model=list[OnchainRiskAlertRead])
def list_wallet_risk_alerts(
    wallet_id: str,
    unresolved_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[OnchainRiskAlert]:
    get_wallet_or_404(db, wallet_id)
    query = select(OnchainRiskAlert).where(OnchainRiskAlert.wallet_id == wallet_id)
    if unresolved_only:
        query = query.where(OnchainRiskAlert.resolved.is_(False))
    return list(db.scalars(query.order_by(OnchainRiskAlert.created_at.desc(), OnchainRiskAlert.id).limit(limit)).all())


@router.get("/wallets/{wallet_id}/detail", response_model=Web3WalletDetailRead)
def get_wallet_detail(wallet_id: str, db: Session = Depends(get_db)) -> Web3WalletDetailRead:
    wallet = get_wallet_or_404(db, wallet_id)
    return Web3WalletDetailRead(
        **WalletRead.model_validate(wallet).model_dump(),
        balances=list_wallet_balances(wallet_id, db=db),
        transfers=list_wallet_transfers(wallet_id, db=db),
        allowances=list_wallet_allowances(wallet_id, db=db),
        risk_alerts=list_wallet_risk_alerts(wallet_id, db=db),
    )


@router.get("/risk-alerts", response_model=list[OnchainRiskAlertRead])
def list_risk_alerts(
    severity: str | None = None,
    unresolved_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[OnchainRiskAlert]:
    query = select(OnchainRiskAlert)
    if severity:
        query = query.where(OnchainRiskAlert.severity == severity)
    if unresolved_only:
        query = query.where(OnchainRiskAlert.resolved.is_(False))
    return list(db.scalars(query.order_by(OnchainRiskAlert.created_at.desc(), OnchainRiskAlert.id).limit(limit)).all())


@router.post("/risk-alerts/{alert_id}/resolve", response_model=OnchainRiskAlertRead)
def resolve_risk_alert(
    alert_id: str,
    payload: OnchainRiskAlertResolveRequest,
    db: Session = Depends(get_db),
) -> OnchainRiskAlert:
    alert = db.get(OnchainRiskAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="risk alert not found")
    return Web3RiskReadOnlyService(db).resolve_alert(alert, payload.resolved)


@router.post("/risk-scan", response_model=Web3RiskScanResponse, status_code=201)
def run_web3_risk_scan(payload: Web3RiskScanRequest, db: Session = Depends(get_db)) -> Web3RiskScanResponse:
    try:
        result = Web3RiskReadOnlyService(db).scan(payload)
    except Web3ReadOnlySafetyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return scan_response(result)


def get_wallet_or_404(db: Session, wallet_id: str) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="wallet not found")
    return wallet


def scan_response(result) -> Web3RiskScanResponse:
    return Web3RiskScanResponse(
        wallet_id=result.wallet_id,
        alerts_created=len(result.alerts),
        balances_imported=len(result.balances),
        allowances_imported=len(result.allowances),
        transfers_imported=len(result.transfers),
        protocol_positions_imported=len(result.protocol_positions),
        exchange_exposures_imported=len(result.exchange_exposures),
        stablecoin_exposures=result.stablecoin_exposures,
        alerts=result.alerts,
        signing_available=False,
        execution_available=False,
    )


def normalized_exposure_pct(value: float) -> float:
    return value * 100 if abs(value) <= 1 else value


def normalized_risk_level(value: str | None) -> str:
    normalized = str(value or "low").lower()
    return normalized if normalized in {"low", "medium", "high"} else "medium"
