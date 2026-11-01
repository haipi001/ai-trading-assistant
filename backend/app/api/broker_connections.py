from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import LiveExecutionConfig
from app.schemas import BrokerConnectionCreate
from app.schemas import BrokerConnectionRead
from app.services.live_execution import LiveExecutionError
from app.services.live_execution import LiveExecutionNotFoundError
from app.services.live_execution import LiveExecutionService

router = APIRouter(prefix="/broker-connections", tags=["broker-connections"])


@router.get("", response_model=list[BrokerConnectionRead])
def list_broker_connections(limit: int = 100, db: Session = Depends(get_db)):
    configs = LiveExecutionService(db).list_configs(limit=limit)
    return [_to_broker_connection(config) for config in configs]


@router.post("", response_model=BrokerConnectionRead, status_code=201)
def create_broker_connection(payload: BrokerConnectionCreate, db: Session = Depends(get_db)):
    service = LiveExecutionService(db)
    try:
        config = service.create_config(
            user_id="default-user",
            exchange_type=payload.broker_type,
            api_key_ref=payload.api_key_ref,
            label=payload.label,
        )
    except LiveExecutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_broker_connection(config)


@router.delete("/{connection_id}", status_code=204)
def delete_broker_connection(connection_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        LiveExecutionService(db).disable_config(connection_id)
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


def _to_broker_connection(config: LiveExecutionConfig) -> dict:
    return {
        "id": config.id,
        "broker_type": config.exchange_type,
        "label": config.label,
        "api_key_ref": config.api_key_ref,
        "status": "active" if config.is_active else "inactive",
        "created_at": config.created_at,
    }
