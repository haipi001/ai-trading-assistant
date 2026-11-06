"""Exact instrument matching; a ticker alone is never an asset identity."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import Asset


class AssetIdentityError(ValueError):
    pass


def asset_identity(*, symbol, asset_type, market, venue, currency, chain_id=None, contract_address=None):
    raw = dict(symbol=symbol, asset_type=asset_type, market=market, venue=venue, currency=currency)
    result = {key: str(value or '').strip().upper() for key, value in raw.items()}
    if not all(result.values()):
        raise AssetIdentityError('instrument identity requires symbol/type/market/venue/currency')
    result['asset_type'] = result['asset_type'].lower()
    # Chain/address aliases require a registry. Preserve exact opaque identifiers
    # rather than merging case-sensitive addresses across chains.
    result['chain_id'] = str(chain_id).strip() if chain_id is not None else None
    result['contract_address'] = str(contract_address).strip() if contract_address is not None else None
    if result['chain_id'] == '' or result['contract_address'] == '':
        raise AssetIdentityError('onchain instrument identifiers cannot be empty')
    if result['contract_address'] is not None and not result['chain_id']:
        raise AssetIdentityError('contract instrument identity requires chain')
    return result


def find_asset(db: Session, identity: dict) -> Asset | None:
    conditions = [func.upper(func.trim(getattr(Asset, key))) == str(identity[key]).upper()
                  for key in ('symbol', 'asset_type', 'market', 'venue', 'currency')]
    conditions += [getattr(Asset, key) == identity[key] for key in ('chain_id', 'contract_address')]
    matches = list(db.scalars(select(Asset).where(*conditions).limit(2)).all())
    if len(matches) > 1:
        raise AssetIdentityError('ambiguous instrument identity; resolve duplicate assets before import')
    return matches[0] if matches else None
