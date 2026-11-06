from app.core.auth import require_permission
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Account
from app.models import Asset
from app.models import AuditLog
from app.models import Candle
from app.models import DataSnapshot
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PortfolioSnapshot
from app.models import Position
from app.schemas import AccountCreate
from app.schemas import AccountRead
from app.schemas import AssetCreate
from app.schemas import AssetClassificationUpdate
from app.schemas import AssetRead
from app.schemas import AuditLogRead
from app.schemas import CandleRead
from app.schemas import DecisionNarrativeRead
from app.schemas import OrderDraftCreate
from app.schemas import OrderDraftRead
from app.schemas import OrderIntentCreate
from app.schemas import OrderIntentRead
from app.schemas import PortfolioSnapshotCreate
from app.schemas import PortfolioSnapshotRead
from app.schemas import PositionCreate
from app.schemas import PositionRead
from app.services.decision_gates import DecisionGateBlockedError
from app.services.decision_gates import DecisionGateService
from app.services.decision_narratives import DecisionNarrativeNotFoundError
from app.services.decision_narratives import DecisionNarrativeService
from app.services.risk import RiskCheckBlockedError
from app.services.risk import RiskCheckNotFoundError
from app.services.risk import RiskEngineService

router = APIRouter()


def write_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    payload_json: dict[str, Any],
    actor_type: str = "system",
    actor_id: str = "phase1-crud-api",
) -> AuditLog:
    audit_log = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload_json,
    )
    db.add(audit_log)
    return audit_log


def list_records(db: Session, model: type, limit: int) -> list:
    return list(db.scalars(select(model).order_by(model.id).limit(limit)).all())


@router.get("/assets", response_model=list[AssetRead], tags=["assets"])
def list_assets(limit: int = 100, db: Session = Depends(get_db)) -> list[Asset]:
    return list_records(db, Asset, limit)


@router.post("/assets", response_model=AssetRead, status_code=201, tags=["assets"])
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)) -> Asset:
    asset = Asset(**payload.model_dump())
    db.add(asset)
    db.flush()
    write_audit_log(db, action="asset.created", entity_type="Asset", entity_id=asset.id, payload_json=payload.model_dump())
    db.commit()
    db.refresh(asset)
    return asset


@router.patch("/assets/{asset_id}/classification", response_model=AssetRead, tags=["assets"])
def update_asset_classification(asset_id: str, payload: AssetClassificationUpdate, db: Session = Depends(get_db)) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    source = payload.classification_source.strip()
    if not source:
        raise HTTPException(status_code=422, detail="classification_source is required")
    if payload.classification_snapshot_id and db.get(DataSnapshot, payload.classification_snapshot_id) is None:
        raise HTTPException(status_code=422, detail="classification snapshot not found")
    if not source.lower().startswith("manual") and not payload.classification_snapshot_id:
        raise HTTPException(status_code=422, detail="non-manual classification requires a trusted source snapshot")
    if payload.classification_snapshot_id:
        from app.services.data_catalog import DataCatalogService
        from app.services.data_catalog import DataTrustGateError

        try:
            DataCatalogService(db).require_trusted_snapshot(payload.classification_snapshot_id, decision_scope="asset_classification")
        except DataTrustGateError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc), "trust_gate": exc.gate}) from exc
    asset.sector = clean_classification(payload.sector)
    asset.industry = clean_classification(payload.industry)
    asset.themes_json = clean_classification_list(payload.themes_json)
    asset.factor_tags_json = clean_classification_list(payload.factor_tags_json)
    asset.classification_source = source[:128]
    asset.classification_snapshot_id = payload.classification_snapshot_id
    db.add(asset)
    db.flush()
    write_audit_log(db, action="asset.classification_updated", entity_type="Asset", entity_id=asset.id, payload_json={"source": asset.classification_source, "snapshot_id": asset.classification_snapshot_id, "sector": asset.sector, "industry": asset.industry, "themes": asset.themes_json, "factor_tags": asset.factor_tags_json})
    db.commit()
    db.refresh(asset)
    return asset


def clean_classification(value: str | None) -> str | None:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized[:128] or None


def clean_classification_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for value in values if (item := clean_classification(value))))[:20]


@router.get("/accounts", response_model=list[AccountRead], tags=["accounts"])
def list_accounts(limit: int = 100, db: Session = Depends(get_db)) -> list[Account]:
    return list_records(db, Account, limit)


@router.post("/accounts", response_model=AccountRead, status_code=201, tags=["accounts"])
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> Account:
    account = Account(**payload.model_dump())
    db.add(account)
    db.flush()
    write_audit_log(
        db,
        action="account.created",
        entity_type="Account",
        entity_id=account.id,
        payload_json=payload.model_dump(),
    )
    db.commit()
    db.refresh(account)
    return account


@router.get("/positions", response_model=list[PositionRead], tags=["positions"])
def list_positions(limit: int = 100, db: Session = Depends(get_db)) -> list[Position]:
    return list_records(db, Position, limit)


@router.get("/candles", response_model=list[CandleRead], tags=["market-data"])
def list_candles(
    asset_id: str | None = None,
    timeframe: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> list[Candle]:
    query = select(Candle).order_by(Candle.timestamp.desc(), Candle.id.desc()).limit(limit)
    if asset_id or timeframe:
        query = select(Candle)
        if asset_id:
            query = query.where(Candle.asset_id == asset_id)
        if timeframe:
            query = query.where(Candle.timeframe == timeframe)
        query = query.order_by(Candle.timestamp.desc(), Candle.id.desc()).limit(limit)
    return list(db.scalars(query).all())


@router.post("/positions/import", response_model=PositionRead, status_code=201, tags=["positions"])
def import_position(payload: PositionCreate, db: Session = Depends(get_db)) -> Position:
    position = Position(**payload.model_dump())
    db.add(position)
    db.flush()
    write_audit_log(
        db,
        action="position.imported",
        entity_type="Position",
        entity_id=position.id,
        payload_json=payload.model_dump(),
    )
    db.commit()
    db.refresh(position)
    return position


@router.get("/portfolio/snapshots", response_model=list[PortfolioSnapshotRead], tags=["portfolio"])
def list_portfolio_snapshots(limit: int = 100, db: Session = Depends(get_db)) -> list[PortfolioSnapshot]:
    return list_records(db, PortfolioSnapshot, limit)


@router.post("/portfolio/snapshots", response_model=PortfolioSnapshotRead, status_code=201, tags=["portfolio"])
def create_portfolio_snapshot(payload: PortfolioSnapshotCreate, db: Session = Depends(get_db)) -> PortfolioSnapshot:
    snapshot = PortfolioSnapshot(**payload.model_dump())
    db.add(snapshot)
    db.flush()
    write_audit_log(
        db,
        action="portfolio_snapshot.created",
        entity_type="PortfolioSnapshot",
        entity_id=snapshot.id,
        payload_json=payload.model_dump(),
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.post("/orders/intents", response_model=OrderIntentRead, status_code=201, tags=["orders"], dependencies=[Depends(require_permission("proposal:create"))])
def create_order_intent(payload: OrderIntentCreate, db: Session = Depends(get_db)) -> OrderIntent:
    order_intent = OrderIntent(**payload.model_dump())
    db.add(order_intent)
    db.flush()
    write_audit_log(
        db,
        action="order_intent.created",
        entity_type="OrderIntent",
        entity_id=order_intent.id,
        payload_json=payload.model_dump(),
    )
    db.commit()
    db.refresh(order_intent)
    return order_intent


@router.get("/orders/intents/{order_intent_id}", response_model=OrderIntentRead, tags=["orders"], dependencies=[Depends(require_permission("read"))])
def get_order_intent(order_intent_id: str, db: Session = Depends(get_db)) -> OrderIntent:
    order_intent = db.get(OrderIntent, order_intent_id)
    if order_intent is None:
        raise HTTPException(status_code=404, detail="order intent not found")
    return order_intent


@router.get("/orders/drafts", response_model=list[OrderDraftRead], tags=["orders"], dependencies=[Depends(require_permission("read"))])
def list_order_drafts(limit: int = 100, db: Session = Depends(get_db)) -> list[OrderDraft]:
    return list_records(db, OrderDraft, limit)


@router.get("/orders/drafts/{order_draft_id}/decision-narrative", response_model=DecisionNarrativeRead, tags=["orders"], dependencies=[Depends(require_permission("read"))])
def get_order_draft_decision_narrative(order_draft_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return DecisionNarrativeService(db).get_order_draft_narrative(order_draft_id)
    except DecisionNarrativeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/orders/drafts/{order_draft_id}", response_model=OrderDraftRead, tags=["orders"], dependencies=[Depends(require_permission("read"))])
def get_order_draft(order_draft_id: str, db: Session = Depends(get_db)) -> OrderDraft:
    order_draft = db.get(OrderDraft, order_draft_id)
    if order_draft is None:
        raise HTTPException(status_code=404, detail="order draft not found")
    return order_draft


@router.post("/orders/drafts", response_model=OrderDraftRead, status_code=201, tags=["orders"], dependencies=[Depends(require_permission("proposal:create"))])
def create_order_draft(payload: OrderDraftCreate, db: Session = Depends(get_db)) -> OrderDraft:
    risk_service = RiskEngineService(db)
    try:
        risk_service.require_latest_risk_passed(payload.order_intent_id)
        decision_gate_results = DecisionGateService(db).require_all_gates_passed(payload.order_intent_id)
    except (RiskCheckBlockedError, RiskCheckNotFoundError, DecisionGateBlockedError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    order_draft = OrderDraft(
        **{
            **payload.model_dump(),
            "risk_status": "passed",
            "approval_status": "pending",
            "execution_status": "not_executable",
            "decision_gate_results": decision_gate_results,
            "behavior_status": "passed",
            "approval_policy": {"required": True, "source": "decision_gates"},
        }
    )
    db.add(order_draft)
    db.flush()
    write_audit_log(
        db,
        action="order_draft.created",
        entity_type="OrderDraft",
        entity_id=order_draft.id,
        payload_json=payload.model_dump(),
    )
    db.commit()
    db.refresh(order_draft)
    return order_draft


@router.get("/audit-logs", response_model=list[AuditLogRead], tags=["audit"])
def list_audit_logs(limit: int = 100, db: Session = Depends(get_db)) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id).limit(limit)).all())
